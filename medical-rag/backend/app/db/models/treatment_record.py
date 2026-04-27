# -*- coding: utf-8 -*-
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TreatmentRecord(Base):
    __tablename__ = "treatment_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    symptoms: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    possible_conditions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False  # "mild" | "moderate" | "severe"
    )
    body_parts: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    recommended_specialty: Mapped[str | None] = mapped_column(String(255), nullable=True)
    urgency: Mapped[str] = mapped_column(
        String(50), nullable=False, default="routine"
    )
    record_date: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=func.current_date()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="treatment_records")
    session: Mapped["ChatSession"] = relationship(
        "ChatSession", back_populates="treatment_record"
    )
