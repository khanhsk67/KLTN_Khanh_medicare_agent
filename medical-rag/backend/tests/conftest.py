# -*- coding: utf-8 -*-
"""
Test configuration — SQLite in-memory, JWT helper, factory functions.

Thứ tự QUAN TRỌNG khi module này được load:
  1. Mock asyncpg trước mọi thứ (session.py tạo asyncpg engine ở module level)
  2. Set env vars trước khi pydantic-settings khởi tạo Settings()
  3. Import các module của app
"""
import os
import sys
from unittest.mock import MagicMock

# ── 1. Mock asyncpg TRƯỚC KHI import app ─────────────────────────────────────
# app/db/session.py gọi create_async_engine(postgresql+asyncpg://...) ở module
# level, điều này trigger import asyncpg ngay lập tức. Vì tests dùng SQLite
# (override get_db), asyncpg không bao giờ được gọi thật → mock là an toàn.
if "asyncpg" not in sys.modules:
    _asyncpg_mock = MagicMock()
    sys.modules["asyncpg"] = _asyncpg_mock
    sys.modules["asyncpg.connection"] = MagicMock()
    sys.modules["asyncpg.pool"] = MagicMock()
    sys.modules["asyncpg.exceptions"] = MagicMock()

# ── 2. Env vars TRƯỚC KHI pydantic-settings load Settings() ──────────────────
os.environ.setdefault(
    "POSTGRES_URL", "postgresql+asyncpg://test:test@localhost/testdb"
)
os.environ.setdefault("OPENAI_API_KEY", "test-api-key-not-real")
os.environ.setdefault(
    "JWT_SECRET_KEY", "test-jwt-secret-key-for-testing-only-minimum-32-chars!"
)

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.expression import TextClause

from app.db.base import Base

# Import tất cả models để Base.metadata biết về chúng
from app.db.models.user import User
from app.db.models.chat_session import ChatSession
from app.db.models.chat_message import ChatMessage
from app.db.models.treatment_record import TreatmentRecord
# Wallet system models — cần thiết để create_all tạo đủ bảng
from app.db.models.wallet import Wallet  # noqa: F401
from app.db.models.point_transaction import PointTransaction  # noqa: F401
from app.db.models.daily_checkin import DailyCheckin  # noqa: F401
from app.db.models.promo_code import PromoCode, PromoCodeRedemption  # noqa: F401
from app.db.models.chat_usage import ChatUsage  # noqa: F401
from app.db.models.refresh_token import RefreshToken  # noqa: F401
from app.db.session import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
)
from main import app

# ── SQLite compatibility ──────────────────────────────────────────────────────
# Hai vấn đề khi dùng SQLite thay PostgreSQL:
#
#  1. gen_random_uuid() — hàm riêng PostgreSQL, không có trong SQLite.
#     Giải pháp: bỏ server_default; Python-side default=uuid.uuid4 vẫn hoạt động.
#
#  2. JSONB — kiểu riêng PostgreSQL, SQLite không render được.
#     Giải pháp: thay bằng sqlalchemy.JSON (lưu dưới dạng TEXT trong SQLite).
#
# Thao tác chỉnh sửa metadata một lần khi conftest được load — an toàn vì
# đây là test env, không ảnh hưởng đến production engine.

import uuid as _uuid_mod
from sqlalchemy import JSON as _JSON
from sqlalchemy.dialects.postgresql import JSONB as _JSONB
from sqlalchemy.sql.sqltypes import Uuid as _UuidType

# Fix 3: Uuid.bind_processor không coerce str → uuid.UUID trong SQLAlchemy 2.0.
# bind_processor trực tiếp gọi value.hex, crash khi value là string.
# auth_service.py và security.py truyền str từ JWT payload vào WHERE clause.
# Monkey-patch cấp class (postgresql.UUID kế thừa từ Uuid, không override).
_orig_uuid_bp = _UuidType.bind_processor

def _sqlite_safe_uuid_bind_processor(self, dialect):
    proc = _orig_uuid_bp(self, dialect)
    if proc is None:
        return None
    def _safe_process(value):
        if value is not None and not isinstance(value, _uuid_mod.UUID):
            try:
                value = _uuid_mod.UUID(str(value))
            except (ValueError, AttributeError):
                return value
        return proc(value)
    return _safe_process

_UuidType.bind_processor = _sqlite_safe_uuid_bind_processor

for _table in Base.metadata.sorted_tables:
    for _col in _table.columns:
        # Fix 1: strip gen_random_uuid() server_default
        # SQLite không có hàm này; Python-side default=uuid.uuid4 đủ dùng.
        if _col.server_default is not None and hasattr(_col.server_default, "arg"):
            if isinstance(_col.server_default.arg, TextClause):
                if "gen_random_uuid" in str(_col.server_default.arg):
                    _col.server_default = None

        # Fix 2: JSONB → JSON
        # JSONB là kiểu PostgreSQL-specific; JSON lưu dưới dạng TEXT trong SQLite.
        if isinstance(_col.type, _JSONB):
            _col.type = _JSON()

# ── SQLite in-memory engine ───────────────────────────────────────────────────
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Fresh in-memory SQLite DB cho mỗi test function."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_db(test_engine):
    """AsyncSession trỏ vào SQLite in-memory DB."""
    TestSession = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with TestSession() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def client(test_db):
    """
    httpx.AsyncClient với DB đã override.
    Lifespan chạy bình thường — Qdrant lỗi sẽ bị bắt và log warning (non-fatal).
    """

    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ── Mock fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def mock_openai():
    """Mock openai.OpenAI client để không gọi API thật."""
    fake_message = MagicMock(content="Đây là phản hồi mock từ OpenAI.")
    fake_choice = MagicMock(
        message=fake_message,
        delta=MagicMock(content="Đây là phản hồi mock từ OpenAI."),
    )
    fake_usage = MagicMock(prompt_tokens=10, completion_tokens=20)
    fake_response = MagicMock(choices=[fake_choice], usage=fake_usage)

    with patch("openai.OpenAI") as mock_cls:
        instance = MagicMock()
        instance.chat.completions.create = MagicMock(return_value=fake_response)
        # Embedding mock
        fake_embedding = MagicMock(data=[MagicMock(embedding=[0.0] * 768)])
        instance.embeddings.create = MagicMock(return_value=fake_embedding)
        mock_cls.return_value = instance
        yield mock_cls


@pytest.fixture
def mock_qdrant():
    """Mock qdrant_service singleton để không cần vector DB thật."""
    with patch("app.services.vector_store.qdrant_service") as mock_svc:
        mock_svc.search = AsyncMock(return_value=[])
        mock_svc.embed_text = AsyncMock(return_value=[0.0] * 768)
        mock_svc.upsert_chunks = AsyncMock(return_value=True)
        yield mock_svc


# ── Factory functions ─────────────────────────────────────────────────────────


async def create_test_user(
    db: AsyncSession,
    email: str = "test@example.com",
    password: str = "TestPass123",
    full_name: str = "Test User",
) -> User:
    """Tạo và commit một User vào test DB."""
    user_obj = User(
        email=email,
        full_name=full_name,
        password_hash=hash_password(password),
        is_active=True,
    )
    db.add(user_obj)
    await db.commit()
    await db.refresh(user_obj)
    return user_obj


async def create_test_session(
    db: AsyncSession,
    user_id,
    title: str = "Phiên test",
) -> ChatSession:
    """Tạo và commit một ChatSession vào test DB."""
    session = ChatSession(
        user_id=user_id,
        title=title,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


def get_auth_headers(user_id: str) -> dict:
    """Tạo Authorization header với JWT access token hợp lệ."""
    token = create_access_token({"sub": user_id})
    return {"Authorization": f"Bearer {token}"}
