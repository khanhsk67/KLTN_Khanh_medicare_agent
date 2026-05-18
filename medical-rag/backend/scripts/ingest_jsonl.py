# -*- coding: utf-8 -*-
"""
Ingest JSONL chunks (đã preprocess) vào Qdrant với OpenAI embedding.

Khác với ingest_pdf.py:
- Đọc từ file JSONL (đã clean + có metadata) thay vì PDF thô
- Payload Qdrant giàu metadata: chapter, disease, page_number → cho phép filter khi search
- Dedup bằng SHA-256 content hash

Cách dùng:
    cd medical-rag/backend
    python scripts/ingest_jsonl.py \
        --input data/processed/derma_chunks.jsonl \
        --collection medical_docs \
        --recreate
"""
import argparse
import json
import os
import sys
import time

# Add backend/ to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from tqdm import tqdm

from app.core.config import settings


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BATCH_SIZE = 50            # OpenAI cho phép embed batch (sẽ gọi từng item ở v1, có thể optimize)
SLEEP_PER_EMBED = 0.05     # ngủ ngắn giữa các request để tránh burst rate limit
MAX_RETRIES = 5
RETRY_SLEEP_DEFAULT = 30.0


def _parse_retry_delay(err: Exception) -> float:
    """Extract retry-after từ OpenAI error message (nếu có)."""
    import re
    msg = str(err)
    m = re.search(r"retry after ([0-9.]+)", msg, re.IGNORECASE)
    if m:
        return float(m.group(1)) + 1.0
    m = re.search(r"(\d+)\s*ms", msg)
    if m:
        return float(m.group(1)) / 1000.0 + 1.0
    return RETRY_SLEEP_DEFAULT


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------
def embed_with_retry(client: OpenAI, text: str, model: str, dimensions: int) -> list[float]:
    """Embed 1 text với retry khi gặp 429/rate limit."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.embeddings.create(
                model=model,
                input=text,
                dimensions=dimensions,
            )
            time.sleep(SLEEP_PER_EMBED)
            return resp.data[0].embedding
        except Exception as e:
            msg = str(e).lower()
            is_rate_limit = "429" in msg or "rate" in msg or "quota" in msg
            if is_rate_limit and attempt < MAX_RETRIES:
                wait = _parse_retry_delay(e)
                tqdm.write(
                    f"  Rate limit — chờ {wait:.1f}s (lần {attempt}/{MAX_RETRIES})"
                )
                time.sleep(wait)
            else:
                raise
    return []  # unreachable


# ---------------------------------------------------------------------------
# Qdrant helpers
# ---------------------------------------------------------------------------
def ensure_collection(
    client: QdrantClient,
    collection_name: str,
    dimensions: int,
    recreate: bool = False,
) -> None:
    """Tạo collection nếu chưa có. Nếu --recreate thì xoá rồi tạo mới."""
    existing = {c.name for c in client.get_collections().collections}
    if collection_name in existing:
        if recreate:
            print(f"[Qdrant] Xoá collection cũ: {collection_name}")
            client.delete_collection(collection_name)
        else:
            print(f"[Qdrant] Dùng collection có sẵn: {collection_name}")
            return

    print(f"[Qdrant] Tạo collection mới: {collection_name} (size={dimensions})")
    client.create_collection(
        collection_name=collection_name,
        vectors_config=qmodels.VectorParams(
            size=dimensions,
            distance=qmodels.Distance.COSINE,
        ),
    )


def get_existing_ids(client: QdrantClient, collection_name: str) -> set[str]:
    """Lấy tất cả point ID đang có trong collection (để dedup)."""
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
# Main
# ---------------------------------------------------------------------------
def ingest(
    input_path: str,
    collection_name: str,
    recreate: bool,
    limit: int = 0,
) -> None:
    if not os.path.isfile(input_path):
        print(f"ERROR: không tìm thấy file {input_path}")
        sys.exit(1)

    # Init clients
    openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    qclient = QdrantClient(url=settings.QDRANT_URL)

    ensure_collection(
        qclient,
        collection_name,
        settings.EMBEDDING_DIMENSIONS,
        recreate=recreate,
    )

    # Dedup
    existing_ids = set() if recreate else get_existing_ids(qclient, collection_name)
    print(f"[Qdrant] Points đang có: {len(existing_ids)}")

    # Đọc JSONL
    with open(input_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    print(f"[Input] Đọc {len(lines)} chunks từ {input_path}")

    batch: list[qmodels.PointStruct] = []
    total_upserted = 0
    total_skipped = 0

    for idx, line in enumerate(tqdm(lines, desc="Embedding+Upsert", unit="chunk")):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            tqdm.write(f"  Line {idx+1} JSON lỗi: {e}")
            continue

        chunk_id = obj["id"]

        if chunk_id in existing_ids:
            total_skipped += 1
            continue

        if limit and total_upserted >= limit:
            tqdm.write(f"\n  Đạt limit {limit} — dừng.")
            break

        # Embed
        try:
            vector = embed_with_retry(
                openai_client,
                obj["content"],
                settings.EMBEDDING_MODEL,
                settings.EMBEDDING_DIMENSIONS,
            )
        except Exception as e:
            tqdm.write(f"  Embed lỗi chunk {chunk_id}: {e}")
            continue

        # Payload đầy đủ metadata
        payload = {
            "content": obj["content"],
            "source_file": obj.get("source_file", ""),
            "page_number": obj.get("page_number", 0),
            "chunk_index": obj.get("chunk_index", idx),
            "chapter": obj.get("chapter", ""),
            "disease": obj.get("disease", ""),
        }

        batch.append(
            qmodels.PointStruct(
                id=chunk_id,
                vector=vector,
                payload=payload,
            )
        )
        existing_ids.add(chunk_id)

        # Flush mỗi BATCH_SIZE
        if len(batch) >= BATCH_SIZE:
            qclient.upsert(collection_name=collection_name, points=batch)
            total_upserted += len(batch)
            batch = []

    # Flush nốt batch cuối
    if batch:
        qclient.upsert(collection_name=collection_name, points=batch)
        total_upserted += len(batch)

    print(f"\n✅ Hoàn tất. Upserted: {total_upserted} | Skipped (dedup): {total_skipped}")
    print(f"   Collection: {collection_name}")
    print(f"   Dashboard: {settings.QDRANT_URL}/dashboard")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest JSONL chunks → Qdrant")
    parser.add_argument(
        "--input",
        default="data/processed/derma_chunks.jsonl",
        help="File JSONL đầu vào",
    )
    parser.add_argument(
        "--collection",
        default=settings.QDRANT_COLLECTION_NAME,
        help=f"Tên collection (mặc định: {settings.QDRANT_COLLECTION_NAME})",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Xoá collection cũ rồi tạo lại (nên dùng lần đầu sau khi đổi embedding)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Số chunks tối đa cần embed (0 = không giới hạn)",
    )
    args = parser.parse_args()

    ingest(
        input_path=args.input,
        collection_name=args.collection,
        recreate=args.recreate,
        limit=args.limit,
    )
