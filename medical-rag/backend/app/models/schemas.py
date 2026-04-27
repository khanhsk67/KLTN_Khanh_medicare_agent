# -*- coding: utf-8 -*-
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------------------------------------------------------------------------
# Auth schemas
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    nickname: str | None = Field(default=None, max_length=100)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    nickname: str | None
    is_active: bool
    created_at: datetime


class UserProfile(UserResponse):
    pass


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


# ---------------------------------------------------------------------------
# Chat schemas
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    session_id: uuid.UUID | None = None
    message: str = Field(min_length=1, max_length=4096)
    image_base64: str | None = None  # base64 encoded image


class SourceChunk(BaseModel):
    content: str
    source_file: str
    page_number: int | None = None
    relevance_score: float | None = None


class ChatResponse(BaseModel):
    session_id: uuid.UUID
    message_id: uuid.UUID
    content: str
    role: Literal["assistant"] = "assistant"
    sources: list[SourceChunk] = []
    urgency_level: str | None = None
    created_at: datetime
    points_charged: int = 0
    balance_remaining: int = 0


class StreamEvent(BaseModel):
    event: Literal["token", "sources", "done", "error"]
    data: str | list[SourceChunk] | None = None


# ---------------------------------------------------------------------------
# Session / Message schemas
# ---------------------------------------------------------------------------

class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    image_url: str | None = None
    sources: Any | None = None
    urgency_level: str | None = None
    created_at: datetime


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    title: str | None = None
    summary: str | None = None
    created_at: datetime
    updated_at: datetime


class SessionWithMessages(SessionResponse):
    messages: list[MessageResponse] = []


class PaginatedSessions(BaseModel):
    items: list[SessionResponse]
    total: int
    page: int
    page_size: int
    pages: int


# ---------------------------------------------------------------------------
# Analysis / Stats schemas
# ---------------------------------------------------------------------------

class TimelineEvent(BaseModel):
    date: date
    session_count: int
    message_count: int


class HealthTimelineItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    date: date
    main_symptom: str
    specialty: str | None = None
    severity: Literal["mild", "moderate", "severe"]
    session_id: uuid.UUID


class TopSymptom(BaseModel):
    name: str
    count: int


class SeverityDistribution(BaseModel):
    severe: int
    moderate: int
    mild: int


class ConsultationFrequency(BaseModel):
    date: str
    count: int


class HealthDashboard(BaseModel):
    period_days: int
    total_sessions: int
    total_messages: int
    avg_messages_per_session: float
    top_symptoms: list[TopSymptom]
    severity_distribution: SeverityDistribution
    consultation_frequency: list[ConsultationFrequency]
    ai_insight: str | None = None


class DetailedStats(BaseModel):
    total_sessions: int
    total_messages: int
    total_treatment_records: int
    severity_distribution: dict[str, int]  # {"mild": 3, "moderate": 5, "severe": 1}
    urgency_distribution: dict[str, int]
    top_symptoms: list[str]
    top_conditions: list[str]
    timeline: list[TimelineEvent]


class AnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    session_id: uuid.UUID
    symptoms: list[str]
    possible_conditions: list[str]
    severity: Literal["mild", "moderate", "severe"]
    body_parts: list[str] | None = None
    recommended_specialty: str | None = None
    urgency: str
    record_date: date
    created_at: datetime


# ---------------------------------------------------------------------------
# LangGraph AgentState
# ---------------------------------------------------------------------------

class AgentState(TypedDict, total=False):
    # Input
    user_id: str
    session_id: str
    user_message: str
    image_base64: str | None
    image_mime_type: str | None

    # Vision
    image_analysis_result: dict[str, Any] | None

    # RAG
    retrieved_chunks: list[SourceChunk]
    rag_context: str

    # Agent routing
    agent_type: Literal["chatbot", "rule_medical", "image_medical", "treatment_analysis"]
    requires_image_analysis: bool
    requires_treatment_analysis: bool

    # Output
    response: str
    message_id: str | None
    sources: list[SourceChunk]
    urgency_level: str | None
    treatment_data: dict[str, Any] | None

    # Control
    error: str | None
    iterations: int
