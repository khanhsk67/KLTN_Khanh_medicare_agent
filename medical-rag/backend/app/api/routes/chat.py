# -*- coding: utf-8 -*-
"""
Chat Routes — SSE streaming endpoint và session management.
"""
import asyncio
import json
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import run_medical_graph
from app.core.security import get_current_user
from app.db.models.chat_session import ChatSession
from app.db.models.user import User
from app.db.session import get_db
from app.models.schemas import ChatRequest
from app.services import wallet_service
from app.services.chat_service import _save_chat_usage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Kích thước mỗi chunk khi phân tách response để gửi SSE token events
_STREAM_CHUNK_SIZE = 30


# ---------------------------------------------------------------------------
# POST /api/chat/stream — SSE streaming
# ---------------------------------------------------------------------------

@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    """
    Chat với AI, trả về SSE stream.

    Events:
    - start:  {"type":"start","urgency":"routine","session_id":"..."}
    - token:  {"type":"token","content":"..."}
    - done:   {"type":"done","session_id":"...","sources":[...],"confidence":"high","urgency":"..."}
    - error:  {"type":"error","content":"..."}
    """
    # Kiểm tra điểm tối thiểu trước khi chat
    await wallet_service.check_minimum_balance(db, current_user.id)

    # Dùng session_id được cung cấp hoặc tạo UUID tạm để gửi trong start event
    preview_session_id = str(request.session_id) if request.session_id else str(uuid.uuid4())

    async def event_generator():
        # --- Start event ---
        start_payload = json.dumps({
            "type": "start",
            "urgency": "routine",
            "session_id": preview_session_id,
        }, ensure_ascii=False)
        yield f"data: {start_payload}\n\n"

        try:
            # Chạy toàn bộ LangGraph pipeline
            chat_response = await run_medical_graph(request, current_user, db)

            # Billing: tính và trừ điểm theo token usage thật
            charged_points = 0
            balance_remaining = 0
            try:
                usage_id = uuid.uuid4()
                charged_points, balance_remaining = await _save_chat_usage(
                    db=db,
                    user_id=current_user.id,
                    session_id=chat_response.session_id,
                    response=chat_response,
                    usage_id=usage_id,
                )
                # Commit ngay — không dựa vào get_db cleanup sau khi stream kết thúc
                await db.commit()
            except Exception as billing_exc:
                logger.warning("Billing lỗi (non-critical): %s", billing_exc)
                try:
                    await db.rollback()
                except Exception:
                    pass

            # --- Token events: chia response thành chunks ---
            content = chat_response.content or ""
            for i in range(0, len(content), _STREAM_CHUNK_SIZE):
                chunk = content[i: i + _STREAM_CHUNK_SIZE]
                token_payload = json.dumps(
                    {"type": "token", "content": chunk},
                    ensure_ascii=False,
                )
                yield f"data: {token_payload}\n\n"
                await asyncio.sleep(0.01)

            # --- Done event ---
            sources_data = [s.model_dump() for s in (chat_response.sources or [])]
            confidence = (
                "high" if len(sources_data) >= 3
                else "medium" if sources_data
                else "low"
            )
            done_payload = json.dumps(
                {
                    "type": "done",
                    "session_id": str(chat_response.session_id),
                    "sources": sources_data,
                    "confidence": confidence,
                    "urgency_level": chat_response.urgency_level or "routine",
                    "points_charged": charged_points,
                    "balance_remaining": balance_remaining,
                },
                ensure_ascii=False,
            )
            yield f"data: {done_payload}\n\n"

        except Exception as exc:
            logger.exception("SSE stream error: %s", exc)
            error_payload = json.dumps(
                {"type": "error", "content": "Có lỗi xảy ra, vui lòng thử lại."},
                ensure_ascii=False,
            )
            yield f"data: {error_payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# GET /api/chat/sessions/new — tạo session trống
# ---------------------------------------------------------------------------

@router.get("/sessions/new")
async def new_session(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Tạo một ChatSession trống mới và trả về session_id."""
    session = ChatSession(user_id=current_user.id, title="Cuộc tư vấn mới")
    db.add(session)
    await db.flush()
    return {"session_id": str(session.id)}
