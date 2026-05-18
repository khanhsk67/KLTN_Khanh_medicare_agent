# -*- coding: utf-8 -*-
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, func, text  # noqa: F401
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(20), nullable=False  # "user" | "assistant"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Danh sách data URL ảnh (hỗ trợ nhiều ảnh / turn). JSONB array of strings.
    image_urls: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    # Cache kết quả phân tích Vision cho ảnh của message này (Phase 2).
    # Cấu trúc: list[dict] — mỗi ảnh một dict {findings, severity, urgency, summary, ...}
    image_analysis: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, nullable=True
    )
    sources: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    urgency_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Relationships
    session: Mapped["ChatSession"] = relationship(
        "ChatSession", back_populates="messages"
    )
