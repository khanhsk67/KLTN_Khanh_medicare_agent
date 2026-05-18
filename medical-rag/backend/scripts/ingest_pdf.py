# -*- coding: utf-8 -*-
"""
Ingest PDF documents into Qdrant vector DB.

Usage:
    python scripts/ingest_pdf.py --folder data/pdfs
    python scripts/ingest_pdf.py --folder data/pdfs --collection medical_docs
"""

import argparse
import hashlib
import os
import sys
import time

# Add backend/ to sys.path so app.* imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from tqdm import tqdm

from app.core.config import settings

_openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CHUNK_SIZE = 1800
CHUNK_OVERLAP = 200
BATCH_SIZE = 50
SCORE_THRESHOLD = 0.65
SLEEP_PER_EMBED = 0.05         # OpenAI tier 1 cho phép ~3000 RPM → 0.05s là an toàn
SLEEP_BETWEEN_BATCHES = 0.0
RETRY_SLEEP_DEFAULT = 30.0
MAX_RETRIES = 5             


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def hash_content(text: str) -> str:
    """SHA-256 hash of content — used as point ID for dedup."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def _parse_retry_delay(err: Exception) -> float:
    """Extract retry_delay seconds from ResourceExhausted error, fallback to default."""
    msg = str(err)
    import re
    m = re.search(r"retry in ([0-9.]+)s", msg)
    if m:
        return float(m.group(1)) + 2.0
    # Try to find 'seconds: N' in the proto dump
    m = re.search(r"seconds:\s*(\d+)", msg)
    if m:
        return float(m.group(1)) + 2.0
    return RETRY_SLEEP_DEFAULT


def embed_with_retry(text: str, model: str) -> list[float]:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = _openai_client.embeddings.create(
                model=model,
                input=text,
                dimensions=settings.EMBEDDING_DIMENSIONS,
            )
            time.sleep(SLEEP_PER_EMBED)
            return result.data[0].embedding
        except Exception as e:
            if "429" in str(e) or "rate_limit" in str(e).lower() or "quota" in str(e).lower():
                wait = _parse_retry_delay(e)
                if attempt < MAX_RETRIES:
                    tqdm.write(f"  Rate limit — sleeping {wait:.1f}s (attempt {attempt}/{MAX_RETRIES})")
                    time.sleep(wait)
                else:
                    raise
            else:
                raise
    return []  # unreachable


def get_existing_ids(client: QdrantClient, collection_name: str) -> set[str]:
    """Scroll through all point IDs to detect duplicates."""
    ids: set[str] = set()
    offset = None
    while True:
        result, offset = client.scroll(
            collection_name=collection_name,
            limit=1000,
            offset=offset,
            with_payload=False,
            with_vectors=False,
        )
        for point in result:
            ids.add(str(point.id))
        if offset is None:
            break
    return ids


# ---------------------------------------------------------------------------
# Main ingest logic
# ---------------------------------------------------------------------------
def ingest(folder: str, collection_name: str, limit: int = 0) -> None:
    """
    limit: max number of NEW chunks to embed per run (0 = unlimited).
           Use this to stay within the 1000 req/day free-tier quota.
           Re-run the next day — already-embedded chunks are skipped via dedup.
    """
    # Init
    client = QdrantClient(url=settings.QDRANT_URL)

    # Ensure collection exists
    existing_collections = {c.name for c in client.get_collections().collections}
    if collection_name not in existing_collections:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=qmodels.VectorParams(
                size=768,
                distance=qmodels.Distance.COSINE,
            ),
        )
        print(f"Created collection: {collection_name}")
    else:
        print(f"Using existing collection: {collection_name}")

    # Load existing IDs for dedup
    existing_ids = get_existing_ids(client, collection_name)
    print(f"Existing points in collection: {len(existing_ids)}")

    # Find all PDFs
    pdf_files = [
        os.path.join(root, f)
        for root, _, files in os.walk(folder)
        for f in files
        if f.lower().endswith(".pdf")
    ]

    if not pdf_files:
        print(f"No PDF files found in: {folder}")
        return

    print(f"Found {len(pdf_files)} PDF file(s)")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ".", " ", ""],
    )

    total_upserted = 0
    total_skipped = 0

    for pdf_path in tqdm(pdf_files, desc="PDFs", unit="file"):
        pdf_name = os.path.basename(pdf_path)
        try:
            loader = PyPDFLoader(pdf_path)
            pages = loader.load()
        except Exception as e:
            tqdm.write(f"  ERROR loading {pdf_name}: {e}")
            continue

        # Split into chunks
        chunks = splitter.split_documents(pages)
        if not chunks:
            tqdm.write(f"  No chunks extracted from {pdf_name}, skipping")
            continue

        tqdm.write(f"  {pdf_name}: {len(pages)} pages → {len(chunks)} chunks")

        # Process in batches
        batch: list[qmodels.PointStruct] = []
        for idx, chunk in enumerate(tqdm(chunks, desc=f"  Chunks", leave=False, unit="chunk")):
            content = chunk.page_content.strip()
            if not content:
                continue

            point_id = hash_content(content)

            # Dedup
            if point_id in existing_ids:
                total_skipped += 1
                continue

            # Daily quota guard
            if limit and total_upserted >= limit:
                tqdm.write(f"\n  Daily limit of {limit} reached — stopping.")
                tqdm.write("  Re-run tomorrow; already-embedded chunks will be skipped automatically.")
                if batch:
                    client.upsert(collection_name=collection_name, points=batch)
                    total_upserted += len(batch)
                print(f"\nPartial ingest. Upserted: {total_upserted} | Skipped (dedup): {total_skipped}")
                return

            vector = embed_with_retry(content, settings.EMBEDDING_MODEL)

            batch.append(
                qmodels.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "content": content,
                        "source_file": pdf_name,
                        "page_number": chunk.metadata.get("page", 0) + 1,
                        "chunk_index": idx,
                    },
                )
            )
            existing_ids.add(point_id)

            # Upsert batch
            if len(batch) >= BATCH_SIZE:
                client.upsert(collection_name=collection_name, points=batch)
                total_upserted += len(batch)
                batch = []
                time.sleep(SLEEP_BETWEEN_BATCHES)

        # Flush remaining
        if batch:
            client.upsert(collection_name=collection_name, points=batch)
            total_upserted += len(batch)
            time.sleep(SLEEP_BETWEEN_BATCHES)

    print(f"\nDone. Upserted: {total_upserted} | Skipped (dedup): {total_skipped}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest PDFs into Qdrant")
    parser.add_argument(
        "--folder",
        required=True,
        help="Path to folder containing PDF files",
    )
    parser.add_argument(
        "--collection",
        default=settings.QDRANT_COLLECTION_NAME,
        help=f"Qdrant collection name (default: {settings.QDRANT_COLLECTION_NAME})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max NEW chunks to embed per run (0 = unlimited). Use 950 to stay under 1000/day quota.",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.folder):
        print(f"ERROR: folder not found: {args.folder}")
        sys.exit(1)

    ingest(folder=args.folder, collection_name=args.collection, limit=args.limit)
