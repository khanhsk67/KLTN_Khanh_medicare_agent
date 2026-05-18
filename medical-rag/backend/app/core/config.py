# -*- coding: utf-8 -*-
from functools import lru_cache
from pathlib import Path

from pydantic import ConfigDict
from pydantic_settings import BaseSettings

# Absolute path to .env — robust regardless of CWD.
# __file__ = backend/app/core/config.py
# parents[3] = medical-rag/  (where .env lives)
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    # OpenAI
    OPENAI_API_KEY: str
    LLM_MODEL: str = "gpt-5.4-mini"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int = 768  # text-embedding-3-small hỗ trợ dimension tùy chỉnh

    # PostgreSQL
    POSTGRES_URL: str

    # Qdrant
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION_NAME: str = "medical_docs"
    # 2 collection để A/B test RAG (clean = preprocessed JSONL, raw = PDF thô)
    QDRANT_COLLECTION_CLEAN: str = "medical_docs_clean"
    QDRANT_COLLECTION_RAW: str = "medical_docs_raw"

    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15  # Giảm từ 60 → 15 phút
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # App
    APP_NAME: str = "Medical RAG"
    DEBUG: bool = False

    # Weather API
    WEATHER_API_KEY: str = ""
    WEATHER_API_URL: str = "https://api.weatherapi.com/v1/current.json"
    WEATHER_CACHE_SECONDS: int = 300

    # ── Wallet & Points ─────────────────────────
    POINT_VALUE_VND: int = 100
    DAILY_CHECKIN_REWARD: int = 50
    MIN_POINTS_TO_CHAT: int = 20

    # ── OpenAI gpt-4o-mini Pricing ─────────────────
    # ⚠️ Cập nhật theo giá thực tại platform.openai.com/docs/pricing
    OPENAI_INPUT_PRICE_USD: float = 0.15    # per 1M tokens (placeholder)
    OPENAI_OUTPUT_PRICE_USD: float = 0.60   # per 1M tokens (placeholder)
    USD_TO_VND_RATE: int = 25000

    def resolve_collection(self, alias: str | None) -> str:
        """
        Map alias từ API query param → tên collection thật trong Qdrant.
        - alias='clean'   → medical_docs_clean
        - alias='raw'     → medical_docs_raw
        - alias='default' → QDRANT_COLLECTION_NAME mặc định
        - alias=None      → QDRANT_COLLECTION_NAME mặc định
        Raise ValueError nếu alias không hợp lệ.
        """
        if not alias:
            return self.QDRANT_COLLECTION_NAME
        alias = alias.lower().strip()
        mapping = {
            "clean": self.QDRANT_COLLECTION_CLEAN,
            "raw": self.QDRANT_COLLECTION_RAW,
            "default": self.QDRANT_COLLECTION_NAME,
        }
        if alias not in mapping:
            raise ValueError(
                f"Invalid collection alias '{alias}'. "
                f"Chọn 1 trong: {list(mapping.keys())}"
            )
        return mapping[alias]

    model_config = ConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
