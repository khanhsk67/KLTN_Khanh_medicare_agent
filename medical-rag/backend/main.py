# -*- coding: utf-8 -*-
"""
Medical RAG — FastAPI application entry point.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.core.limiter import limiter
from sqlalchemy import text

from app.api.routes.analysis import router as analysis_router
from app.api.routes.auth import router as auth_router
from app.api.routes.chat import router as chat_router
from app.api.routes.checkin import router as checkin_router
from app.api.routes.history import router as history_router
from app.api.routes.promo import router as promo_router
from app.api.routes.wallet import router as wallet_router
from app.api.routes.weather import router as weather_router
from app.core.config import settings
from app.db.session import AsyncSessionLocal, engine
from app.services.promo_service import seed_promo_codes
from app.services.vector_store import qdrant_service

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up %s...", settings.APP_NAME)

    # Khởi tạo Qdrant collection
    try:
        qdrant_service.create_collection_if_not_exists()
        logger.info("Qdrant collection ready: %s", settings.QDRANT_COLLECTION_NAME)
    except Exception as exc:
        logger.warning("Qdrant init failed (non-fatal): %s", exc)

    # Seed promo codes mặc định
    try:
        async with AsyncSessionLocal() as db:
            await seed_promo_codes(db)
        logger.info("Promo codes seeded")
    except Exception as exc:
        logger.warning("Promo seed failed (non-fatal): %s", exc)

    yield  # ← app đang chạy

    # Cleanup
    await engine.dispose()
    logger.info("%s shut down", settings.APP_NAME)


# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — cho phép Angular dev server (port 4000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4000", "http://127.0.0.1:4000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(404)
async def not_found_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": "Resource not found"},
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled server error: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(history_router)
app.include_router(analysis_router)
app.include_router(weather_router, prefix="/api")
app.include_router(wallet_router,  prefix="/api")
app.include_router(checkin_router, prefix="/api")
app.include_router(promo_router,   prefix="/api")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/api/health", tags=["system"])
async def health_check() -> dict:
    """Kiểm tra trạng thái PostgreSQL, Qdrant và Gemini API."""
    checks: dict[str, str] = {}

    # PostgreSQL
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:
        logger.error("PostgreSQL health check failed: %s", exc)
        checks["postgres"] = f"error: {exc}"

    # Qdrant
    try:
        qdrant_service.client.get_collections()
        checks["qdrant"] = "ok"
    except Exception as exc:
        logger.error("Qdrant health check failed: %s", exc)
        checks["qdrant"] = f"error: {exc}"

    # OpenAI API — kiểm tra key có cấu hình không
    try:
        if not settings.OPENAI_API_KEY:
            checks["openai"] = "error: OPENAI_API_KEY not set"
        else:
            checks["openai"] = "ok"
    except Exception as exc:
        logger.error("OpenAI health check failed: %s", exc)
        checks["openai"] = f"error: {exc}"

    all_ok = all(v == "ok" for v in checks.values())
    return {
        "status": "healthy" if all_ok else "degraded",
        "checks": checks,
        "app": settings.APP_NAME,
        "version": "1.0.0",
    }


@app.get("/", tags=["system"])
async def root() -> dict:
    return {"message": f"{settings.APP_NAME} is running"}
