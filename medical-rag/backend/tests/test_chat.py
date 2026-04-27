# -*- coding: utf-8 -*-
"""
Test suite cho Chat endpoints.

Endpoint thực tế trong codebase:
  GET  /api/chat/sessions/new   — Tạo session trống, trả {"session_id": "..."}
  POST /api/chat/stream         — SSE streaming chat (mock run_medical_graph)

Session list / delete dùng history router:
  GET    /api/history/sessions           — Paginated list
  GET    /api/history/sessions/{id}      — Detail với messages
  DELETE /api/history/sessions/{id}      — Xóa session
"""
import json
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import ChatResponse
from tests.conftest import create_test_session, create_test_user, get_auth_headers

pytestmark = pytest.mark.asyncio


# ── Helper: tạo ChatResponse mock ────────────────────────────────────────────

def _make_mock_response(content: str = "Đây là phản hồi mock từ AI") -> ChatResponse:
    return ChatResponse(
        session_id=uuid.uuid4(),
        message_id=uuid.uuid4(),
        content=content,
        sources=[],
        urgency_level="routine",
        created_at=datetime.utcnow(),
    )


# ═════════════════════════════════════════════════════════════════════════════
# TestNewSession — GET /api/chat/sessions/new
# ═════════════════════════════════════════════════════════════════════════════


class TestNewSession:
    async def test_new_session_returns_session_id(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """GET /api/chat/sessions/new tạo ChatSession và trả về session_id."""
        user = await create_test_user(test_db, email="new@example.com")
        headers = get_auth_headers(str(user.id))

        res = await client.get("/api/chat/sessions/new", headers=headers)

        assert res.status_code == 200
        data = res.json()
        assert "session_id" in data
        # session_id phải là UUID hợp lệ
        uuid.UUID(data["session_id"])  # Raises ValueError nếu không hợp lệ

    async def test_new_session_unauthenticated(self, client: AsyncClient):
        """Không có token → 401."""
        res = await client.get("/api/chat/sessions/new")
        assert res.status_code == 401

    async def test_new_session_creates_unique_ids(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Mỗi lần gọi tạo ra session_id khác nhau."""
        user = await create_test_user(test_db, email="unique@example.com")
        headers = get_auth_headers(str(user.id))

        res1 = await client.get("/api/chat/sessions/new", headers=headers)
        res2 = await client.get("/api/chat/sessions/new", headers=headers)

        assert res1.status_code == 200
        assert res2.status_code == 200
        assert res1.json()["session_id"] != res2.json()["session_id"]


# ═════════════════════════════════════════════════════════════════════════════
# TestListSessions — GET /api/history/sessions
# ═════════════════════════════════════════════════════════════════════════════


class TestListSessions:
    async def test_list_sessions_returns_paginated(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """GET /api/history/sessions trả PaginatedSessions."""
        user = await create_test_user(test_db, email="sessions@example.com")
        await create_test_session(test_db, user.id, "Phiên 1")
        await create_test_session(test_db, user.id, "Phiên 2")
        headers = get_auth_headers(str(user.id))

        res = await client.get("/api/history/sessions", headers=headers)

        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        assert "page" in data
        assert "page_size" in data

    async def test_list_sessions_empty_for_new_user(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """User mới chưa có session → total=0, items=[]."""
        user = await create_test_user(test_db, email="empty@example.com")
        headers = get_auth_headers(str(user.id))

        res = await client.get("/api/history/sessions", headers=headers)

        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 0
        assert data["items"] == []

    async def test_cannot_see_other_user_sessions(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """User A không thấy session của User B."""
        user_a = await create_test_user(test_db, email="a@example.com")
        user_b = await create_test_user(test_db, email="b@example.com")
        await create_test_session(test_db, user_b.id, "Session của B")
        headers_a = get_auth_headers(str(user_a.id))

        res = await client.get("/api/history/sessions", headers=headers_a)

        assert res.status_code == 200
        assert res.json()["total"] == 0

    async def test_list_sessions_unauthenticated(self, client: AsyncClient):
        """Không có token → 401."""
        res = await client.get("/api/history/sessions")
        assert res.status_code == 401

    async def test_list_sessions_pagination(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Tham số page và page_size hoạt động đúng."""
        user = await create_test_user(test_db, email="page@example.com")
        for i in range(5):
            await create_test_session(test_db, user.id, f"Phiên {i + 1}")
        headers = get_auth_headers(str(user.id))

        res = await client.get(
            "/api/history/sessions",
            params={"page": 1, "page_size": 3},
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 5
        assert len(data["items"]) == 3


# ═════════════════════════════════════════════════════════════════════════════
# TestChatStream — POST /api/chat/stream
# ═════════════════════════════════════════════════════════════════════════════


class TestChatStream:
    async def test_stream_returns_sse_events(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """POST /api/chat/stream trả text/event-stream với start + done events."""
        user = await create_test_user(test_db, email="stream@example.com")
        headers = get_auth_headers(str(user.id))
        mock_response = _make_mock_response("Hãy uống nhiều nước và nghỉ ngơi.")

        with patch(
            "app.api.routes.chat.run_medical_graph",
            new=AsyncMock(return_value=mock_response),
        ):
            res = await client.post(
                "/api/chat/stream",
                json={"message": "Tôi bị đau đầu từ sáng đến giờ"},
                headers=headers,
            )

        assert res.status_code == 200
        assert "text/event-stream" in res.headers["content-type"]

        body = res.text
        # Phải có start event và done event
        assert '"type":"start"' in body or '"type": "start"' in body
        assert '"type":"done"' in body or '"type": "done"' in body

    async def test_stream_events_contain_content(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Token events chứa nội dung phản hồi."""
        user = await create_test_user(test_db, email="content@example.com")
        headers = get_auth_headers(str(user.id))
        mock_response = _make_mock_response("Bạn nên đến gặp bác sĩ.")

        with patch(
            "app.api.routes.chat.run_medical_graph",
            new=AsyncMock(return_value=mock_response),
        ):
            res = await client.post(
                "/api/chat/stream",
                json={"message": "Triệu chứng của tôi là gì?"},
                headers=headers,
            )

        assert res.status_code == 200
        body = res.text
        # Nội dung mock phải xuất hiện trong token events
        assert "Bạn nên đến gặp bác sĩ." in body

    async def test_stream_with_existing_session(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Gửi message kèm session_id hợp lệ của chính user."""
        user = await create_test_user(test_db, email="withsession@example.com")
        session = await create_test_session(test_db, user.id, "Phiên có sẵn")
        headers = get_auth_headers(str(user.id))
        mock_response = _make_mock_response()
        mock_response.session_id = session.id  # Gán lại để khớp với session

        with patch(
            "app.api.routes.chat.run_medical_graph",
            new=AsyncMock(return_value=mock_response),
        ):
            res = await client.post(
                "/api/chat/stream",
                json={
                    "session_id": str(session.id),
                    "message": "Tiếp tục tư vấn",
                },
                headers=headers,
            )

        assert res.status_code == 200

    async def test_stream_with_image(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """POST /api/chat/stream với image_base64 — mock xử lý ảnh."""
        import base64

        user = await create_test_user(test_db, email="img@example.com")
        headers = get_auth_headers(str(user.id))

        # PNG 1×1 pixel tối giản để test
        fake_image_b64 = base64.b64encode(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
            b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
            b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        ).decode()

        mock_response = _make_mock_response("Ảnh cho thấy vết thương nhẹ.")

        with patch(
            "app.api.routes.chat.run_medical_graph",
            new=AsyncMock(return_value=mock_response),
        ):
            res = await client.post(
                "/api/chat/stream",
                json={
                    "message": "Đây là vết thương của tôi",
                    "image_base64": fake_image_b64,
                },
                headers=headers,
            )

        assert res.status_code == 200
        body = res.text
        assert '"type":"start"' in body or '"type": "start"' in body

    async def test_stream_unauthenticated(self, client: AsyncClient):
        """Không có token → 401."""
        res = await client.post(
            "/api/chat/stream",
            json={"message": "Tôi bị đau đầu"},
        )
        assert res.status_code == 401

    async def test_stream_empty_message_rejected(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Tin nhắn rỗng (min_length=1) → 422."""
        user = await create_test_user(test_db, email="emptymsg@example.com")
        headers = get_auth_headers(str(user.id))

        res = await client.post(
            "/api/chat/stream",
            json={"message": ""},
            headers=headers,
        )
        assert res.status_code == 422

    async def test_stream_message_too_long_rejected(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Tin nhắn > 4096 ký tự → 422 (max_length=4096)."""
        user = await create_test_user(test_db, email="toolong@example.com")
        headers = get_auth_headers(str(user.id))

        res = await client.post(
            "/api/chat/stream",
            json={"message": "x" * 4097},
            headers=headers,
        )
        assert res.status_code == 422

    async def test_stream_done_event_has_session_id(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Done event phải chứa session_id hợp lệ."""
        user = await create_test_user(test_db, email="doneevent@example.com")
        headers = get_auth_headers(str(user.id))
        expected_session_id = str(uuid.uuid4())
        mock_response = _make_mock_response()
        mock_response.session_id = uuid.UUID(expected_session_id)

        with patch(
            "app.api.routes.chat.run_medical_graph",
            new=AsyncMock(return_value=mock_response),
        ):
            res = await client.post(
                "/api/chat/stream",
                json={"message": "Test message"},
                headers=headers,
            )

        assert res.status_code == 200
        # Parse SSE events để tìm done event
        done_event = None
        for line in res.text.split("\n"):
            if line.startswith("data: "):
                try:
                    payload = json.loads(line[6:])
                    if payload.get("type") == "done":
                        done_event = payload
                        break
                except json.JSONDecodeError:
                    continue

        assert done_event is not None
        assert "session_id" in done_event
        assert done_event["session_id"] == expected_session_id


# ═════════════════════════════════════════════════════════════════════════════
# TestSessionDetail — GET /api/history/sessions/{id}
# ═════════════════════════════════════════════════════════════════════════════


class TestSessionDetail:
    async def test_get_own_session_detail(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Lấy chi tiết session của chính mình → 200."""
        user = await create_test_user(test_db, email="detail@example.com")
        session = await create_test_session(test_db, user.id, "Phiên chi tiết")
        headers = get_auth_headers(str(user.id))

        res = await client.get(
            f"/api/history/sessions/{session.id}",
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == str(session.id)
        assert data["title"] == "Phiên chi tiết"
        assert "messages" in data

    async def test_cannot_access_other_user_session(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """User A không xem được session của User B → 404."""
        owner = await create_test_user(test_db, email="owner_d@example.com")
        other = await create_test_user(test_db, email="other_d@example.com")
        session = await create_test_session(test_db, owner.id)
        headers_other = get_auth_headers(str(other.id))

        res = await client.get(
            f"/api/history/sessions/{session.id}",
            headers=headers_other,
        )
        assert res.status_code == 404

    async def test_get_nonexistent_session(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Session không tồn tại → 404."""
        user = await create_test_user(test_db, email="noexist@example.com")
        headers = get_auth_headers(str(user.id))

        res = await client.get(
            f"/api/history/sessions/{uuid.uuid4()}",
            headers=headers,
        )
        assert res.status_code == 404


# ═════════════════════════════════════════════════════════════════════════════
# TestDeleteSession — DELETE /api/history/sessions/{id}
# ═════════════════════════════════════════════════════════════════════════════


class TestDeleteSession:
    async def test_delete_own_session(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Xóa session của chính mình → 204 No Content."""
        user = await create_test_user(test_db, email="del@example.com")
        session = await create_test_session(test_db, user.id, "Sẽ bị xóa")
        headers = get_auth_headers(str(user.id))

        res = await client.delete(
            f"/api/history/sessions/{session.id}",
            headers=headers,
        )
        assert res.status_code == 204

    async def test_cannot_delete_other_user_session(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """User B không thể xóa session của User A → 404."""
        owner = await create_test_user(test_db, email="owner2@example.com")
        attacker = await create_test_user(test_db, email="att@example.com")
        session = await create_test_session(test_db, owner.id)
        headers_attacker = get_auth_headers(str(attacker.id))

        res = await client.delete(
            f"/api/history/sessions/{session.id}",
            headers=headers_attacker,
        )
        # history_service queries WHERE id=? AND user_id=? → not found → 404
        assert res.status_code == 404

    async def test_delete_nonexistent_session(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Xóa session không tồn tại → 404."""
        user = await create_test_user(test_db, email="del2@example.com")
        headers = get_auth_headers(str(user.id))

        res = await client.delete(
            f"/api/history/sessions/{uuid.uuid4()}",
            headers=headers,
        )
        assert res.status_code == 404

    async def test_delete_unauthenticated(self, client: AsyncClient):
        """Không có token → 401."""
        res = await client.delete(f"/api/history/sessions/{uuid.uuid4()}")
        assert res.status_code == 401


# ═════════════════════════════════════════════════════════════════════════════
# TestHistorySearch — GET /api/history/search
# ═════════════════════════════════════════════════════════════════════════════


class TestHistorySearch:
    async def test_search_finds_matching_session(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Tìm kiếm theo từ khóa trong title."""
        user = await create_test_user(test_db, email="search@example.com")
        await create_test_session(test_db, user.id, "Tư vấn đau đầu")
        await create_test_session(test_db, user.id, "Kiểm tra huyết áp")
        headers = get_auth_headers(str(user.id))

        res = await client.get(
            "/api/history/search",
            params={"q": "đau đầu"},
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert "đau đầu" in data[0]["title"].lower()

    async def test_search_empty_result(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Tìm kiếm không có kết quả → 200 với list rỗng."""
        user = await create_test_user(test_db, email="nosearch@example.com")
        await create_test_session(test_db, user.id, "Tư vấn bình thường")
        headers = get_auth_headers(str(user.id))

        res = await client.get(
            "/api/history/search",
            params={"q": "từ khóa không tồn tại xyz"},
            headers=headers,
        )
        assert res.status_code == 200
        assert res.json() == []

    async def test_search_requires_query(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Thiếu tham số q → 422."""
        user = await create_test_user(test_db, email="noparam@example.com")
        headers = get_auth_headers(str(user.id))

        res = await client.get("/api/history/search", headers=headers)
        assert res.status_code == 422
