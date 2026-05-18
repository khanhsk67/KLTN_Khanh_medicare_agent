# -*- coding: utf-8 -*-
"""
Debug script — test trực tiếp embed query + search cả 2 collection.
Bỏ qua mọi tầng API/Auth để cô lập vấn đề.

Cách dùng:
    python scripts/test_search.py "bệnh chốc điều trị thế nào"
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI
from qdrant_client import QdrantClient

from app.core.config import settings


def main(query: str):
    print(f"\n=== Query: {query!r} ===\n")
    print(f"OPENAI_API_KEY: {'OK ('+settings.OPENAI_API_KEY[:10]+'...)' if settings.OPENAI_API_KEY else 'MISSING'}")
    print(f"EMBEDDING_MODEL: {settings.EMBEDDING_MODEL}")
    print(f"EMBEDDING_DIMENSIONS: {settings.EMBEDDING_DIMENSIONS}")
    print(f"QDRANT_URL: {settings.QDRANT_URL}")
    print()

    # 1. Embed query
    oai = OpenAI(api_key=settings.OPENAI_API_KEY)
    try:
        resp = oai.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=query,
            dimensions=settings.EMBEDDING_DIMENSIONS,
        )
        vec = resp.data[0].embedding
        print(f"[OK] Embed thành công. Length={len(vec)} | First 5={vec[:5]}")
    except Exception as e:
        print(f"[FAIL] Embed lỗi: {e}")
        return

    qdrant = QdrantClient(url=settings.QDRANT_URL)

    # 2. Search ở từng collection với score_threshold KHÁC NHAU
    collections_to_test = ["medical_docs_clean", "medical_docs_raw"]

    for coll in collections_to_test:
        print(f"\n{'='*60}")
        print(f"Collection: {coll}")
        print(f"{'='*60}")

        # Test với threshold cao và thấp để xem score thực tế
        for threshold in [0.0, 0.3, 0.5, 0.7]:
            try:
                res = qdrant.query_points(
                    collection_name=coll,
                    query=vec,
                    limit=5,
                    with_payload=True,
                    score_threshold=threshold,
                )
                points = res.points
                print(f"\n  score_threshold={threshold} → {len(points)} kết quả")
                if points:
                    for i, p in enumerate(points[:3], 1):
                        payload = p.payload or {}
                        content = payload.get("content", "")[:100].replace("\n", " ")
                        disease = payload.get("disease", "")
                        print(f"    {i}. score={p.score:.4f} | disease={disease!r}")
                        print(f"       {content}...")
            except Exception as e:
                print(f"  Search lỗi: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "query",
        nargs="?",
        default="bệnh chốc điều trị thế nào",
        help="Câu hỏi để test",
    )
    args = parser.parse_args()
    main(args.query)
