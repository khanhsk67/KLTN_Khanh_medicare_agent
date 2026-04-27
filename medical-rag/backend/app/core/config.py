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
    # Google Gemini
    GOOGLE_API_KEY: str
    LLM_MODEL: str = "gemini-2.0-flash"
    EMBEDDING_MODEL: str = "models/gemini-embedding-001"
    EMBEDDING_DIMENSIONS: int = 768

    # PostgreSQL
    POSTGRES_URL: str

    # Qdrant
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION_NAME: str = "medical_docs"

    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
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

    # ── Gemini 2.5 Flash Pricing ─────────────────
    # Nguồn: ai.google.dev/pricing
    GEMINI_INPUT_PRICE_USD: float = 0.075   # per 1M tokens
    GEMINI_OUTPUT_PRICE_USD: float = 0.30   # per 1M tokens
    USD_TO_VND_RATE: int = 25000

    model_config = ConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
