# -*- coding: utf-8 -*-
import asyncio
import time
from typing import List
import logging
logger = logging.getLogger(__name__)

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.core.config import settings
from app.models.schemas import SourceChunk


class QdrantService:
    def __init__(self) -> None:
        self.client = QdrantClient(url=settings.QDRANT_URL)
        self.collection_name = settings.QDRANT_COLLECTION_NAME
        self.dimensions = settings.EMBEDDING_DIMENSIONS  # 768
        self.openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)

    # ------------------------------------------------------------------
    # Collection management
    # ------------------------------------------------------------------
    def create_collection_if_not_exists(self) -> None:
        existing = {c.name for c in self.client.get_collections().collections}
        if self.collection_name in existing:
            return
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=qmodels.VectorParams(
                size=self.dimensions,
                distance=qmodels.Distance.COSINE,
            ),
        )

    # ------------------------------------------------------------------
    # Embedding
    # ------------------------------------------------------------------
    async def embed_text(self, text: str) -> List[float]:
        loop = asyncio.get_event_loop()
        # openai SDK is sync — run in executor to avoid blocking event loop
        result = await loop.run_in_executor(
            None,
            lambda: self.openai_client.embeddings.create(
                model=settings.EMBEDDING_MODEL,
                input=text,
                dimensions=settings.EMBEDDING_DIMENSIONS,
            ),
        )
        return result.data[0].embedding

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    async def search(
        self,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.65,
        collection_name: str | None = None,
    ) -> List[SourceChunk]:
        # Cho phép override collection per-request (A/B test giữa clean/raw)
        collection = collection_name or self.collection_name
        logger.info(
            "[Qdrant] Search config | url=%s | collection=%s | top_k=%d | score_threshold=%.2f",
            settings.QDRANT_URL, collection, top_k, score_threshold,
        )
        logger.info("Đây là query trước khi làm gì đó: query=%s", query)
        query_vector = await self.embed_text(query)
        logger.info("đây là query sau khi embed: %s", query_vector[:10])
        try:
            count_results = self.client.count(
                collection_name=collection,
                exact=True,
            )
            logger.info(
                "[Qdrant] Collection point count | collection=%s | points=%d",
                collection,
                count_results.count,
            )

            response = self.client.query_points(
                collection_name=collection,
                query=query_vector,
                limit=top_k,
                with_payload=True,
                score_threshold = score_threshold,
            )

        except Exception:
            logger.exception("[Qdrant] Error during search")
            raise
            
        results = response.points

        chunks: List[SourceChunk] = []
        for hit in results:
            payload = hit.payload or {}
            chunks.append(
                SourceChunk(
                    chunk_id=str(hit.id),
                    content=payload.get("content", ""),
                    source_file=payload.get("source_file", ""),
                    page_number=payload.get("page_number"),
                    relevance_score=round(hit.score, 4),
                )
            )
        return chunks

    # ------------------------------------------------------------------
    # Upsert
    # ------------------------------------------------------------------
    async def upsert_chunks(self, chunks: List[dict]) -> bool:
        """
        chunks: list of dicts with keys:
            id (str), content (str), source_file (str),
            page_number (int), chunk_index (int)
        """
        if not chunks:
            return True

        points: List[qmodels.PointStruct] = []
        for chunk in chunks:
            vector = await self.embed_text(chunk["content"])
            points.append(
                qmodels.PointStruct(
                    id=chunk["id"],
                    vector=vector,
                    payload={
                        "content": chunk["content"],
                        "source_file": chunk["source_file"],
                        "page_number": chunk["page_number"],
                        "chunk_index": chunk["chunk_index"],
                    },
                )
            )

        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
        )
        return True


# Singleton — import và dùng trực tiếp
qdrant_service = QdrantService()
