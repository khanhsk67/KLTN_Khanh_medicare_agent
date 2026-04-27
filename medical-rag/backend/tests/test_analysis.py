# -*- coding: utf-8 -*-
"""
Test suite cho Analysis endpoints.

Endpoint thực tế:
  GET /api/analysis/summary?period_days=N     → AnalysisResponse (single record) | 404
  GET /api/analysis/statistics?period_days=N  → DetailedStats (aggregates)
  GET /api/analysis/timeline                  → list[TimelineEvent]

Lưu ý:
  - /summary trả 404 nếu user chưa có TreatmentRecord trong kỳ
  - /statistics luôn trả 200, ngay cả khi không có dữ liệu (count = 0)
  - Param là "period_days", KHÔNG phải "days"
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import create_test_session, create_test_user, get_auth_headers

pytestmark = pytest.mark.asyncio


# ═════════════════════════════════════════════════════════════════════════════
# TestSummary — GET /api/analysis/summary
# ═════════════════════════════════════════════════════════════════════════════


class TestSummary:
    async def test_summary_no_data_returns_404(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """
        User chưa có TreatmentRecord → analysis_service.get_user_analysis trả None
        → route raise 404.
        """
        user = await create_test_user(test_db, email="nodata_s@example.com")
        headers = get_auth_headers(str(user.id))

        res = await client.get(
            "/api/analysis/summary",
            params={"period_days": 30},
            headers=headers,
        )
        assert res.status_code == 404

    async def test_summary_unauthenticated(self, client: AsyncClient):
        """Không có token → 401."""
        res = await client.get(
            "/api/analysis/summary",
            params={"period_days": 30},
        )
        assert res.status_code == 401

    async def test_summary_period_days_validation(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """period_days=0 hoặc >365 → 422 (ge=1, le=365)."""
        user = await create_test_user(test_db, email="pdval@example.com")
        headers = get_auth_headers(str(user.id))

        for invalid_days in [0, 366, -1]:
            res = await client.get(
                "/api/analysis/summary",
                params={"period_days": invalid_days},
                headers=headers,
            )
            assert res.status_code == 422, f"Expected 422 for period_days={invalid_days}"

    async def test_summary_default_period(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Không truyền period_days → dùng default=30, trả 404 (không có dữ liệu)."""
        user = await create_test_user(test_db, email="default_p@example.com")
        headers = get_auth_headers(str(user.id))

        res = await client.get("/api/analysis/summary", headers=headers)
        # Default period_days=30, không có data → 404 (không phải 500)
        assert res.status_code == 404


# ═════════════════════════════════════════════════════════════════════════════
# TestStatistics — GET /api/analysis/statistics
# ═════════════════════════════════════════════════════════════════════════════


class TestStatistics:
    async def test_statistics_no_data_returns_zeros(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """
        User chưa có sessions → statistics trả zeros, không crash.
        DetailedStats: total_sessions=0, total_messages=0, top_symptoms=[], timeline=[]
        """
        user = await create_test_user(test_db, email="nodata@example.com")
        headers = get_auth_headers(str(user.id))

        res = await client.get(
            "/api/analysis/statistics",
            params={"period_days": 30},
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["total_sessions"] == 0
        assert data["total_messages"] == 0
        assert data["total_treatment_records"] == 0
        assert isinstance(data["top_symptoms"], list)
        assert isinstance(data["top_conditions"], list)
        assert isinstance(data["timeline"], list)
        assert isinstance(data["severity_distribution"], dict)
        assert isinstance(data["urgency_distribution"], dict)

    async def test_statistics_with_sessions(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """User có sessions → total_sessions phản ánh đúng số session đã tạo."""
        user = await create_test_user(test_db, email="withdata@example.com")
        await create_test_session(test_db, user.id, "Phiên 1")
        await create_test_session(test_db, user.id, "Phiên 2")
        headers = get_auth_headers(str(user.id))

        res = await client.get(
            "/api/analysis/statistics",
            params={"period_days": 30},
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["total_sessions"] == 2

    async def test_statistics_different_periods(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Lọc theo nhiều giá trị period_days → tất cả trả 200."""
        user = await create_test_user(test_db, email="period@example.com")
        headers = get_auth_headers(str(user.id))

        for days in [7, 30, 90, 365]:
            res = await client.get(
                "/api/analysis/statistics",
                params={"period_days": days},
                headers=headers,
            )
            assert res.status_code == 200, f"Failed for period_days={days}"

    async def test_statistics_isolation(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """User A không thấy dữ liệu của User B trong statistics."""
        user_a = await create_test_user(test_db, email="isolate_a@example.com")
        user_b = await create_test_user(test_db, email="isolate_b@example.com")
        # Tạo sessions cho user B
        await create_test_session(test_db, user_b.id, "Session B")
        await create_test_session(test_db, user_b.id, "Session B 2")

        headers_a = get_auth_headers(str(user_a.id))
        res = await client.get(
            "/api/analysis/statistics",
            params={"period_days": 30},
            headers=headers_a,
        )
        assert res.status_code == 200
        # User A không thấy sessions của B
        assert res.json()["total_sessions"] == 0

    async def test_statistics_unauthenticated(self, client: AsyncClient):
        """Không có token → 401."""
        res = await client.get(
            "/api/analysis/statistics",
            params={"period_days": 30},
        )
        assert res.status_code == 401

    async def test_statistics_period_days_validation(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """period_days ngoài phạm vi → 422."""
        user = await create_test_user(test_db, email="statval@example.com")
        headers = get_auth_headers(str(user.id))

        res = await client.get(
            "/api/analysis/statistics",
            params={"period_days": 0},
            headers=headers,
        )
        assert res.status_code == 422


# ═════════════════════════════════════════════════════════════════════════════
# TestTimeline — GET /api/analysis/timeline
# ═════════════════════════════════════════════════════════════════════════════


class TestTimeline:
    async def test_timeline_empty_for_new_user(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """User không có sessions → timeline là list rỗng."""
        user = await create_test_user(test_db, email="timeline_empty@example.com")
        headers = get_auth_headers(str(user.id))

        res = await client.get("/api/analysis/timeline", headers=headers)
        assert res.status_code == 200
        assert res.json() == []

    async def test_timeline_with_sessions(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """User có sessions → timeline có ít nhất 1 entry."""
        user = await create_test_user(test_db, email="timeline_data@example.com")
        await create_test_session(test_db, user.id, "Phiên hôm nay")
        headers = get_auth_headers(str(user.id))

        res = await client.get("/api/analysis/timeline", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert len(data) >= 1
        # Mỗi entry phải có date và session_count
        for event in data:
            assert "date" in event
            assert "session_count" in event
            assert "message_count" in event

    async def test_timeline_unauthenticated(self, client: AsyncClient):
        """Không có token → 401."""
        res = await client.get("/api/analysis/timeline")
        assert res.status_code == 401

    async def test_timeline_isolation(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Timeline chỉ chứa dữ liệu của chính user."""
        user_a = await create_test_user(test_db, email="tl_a@example.com")
        user_b = await create_test_user(test_db, email="tl_b@example.com")
        await create_test_session(test_db, user_b.id, "Session B")

        headers_a = get_auth_headers(str(user_a.id))
        res = await client.get("/api/analysis/timeline", headers=headers_a)

        assert res.status_code == 200
        # User A chưa có sessions → timeline rỗng
        assert res.json() == []
