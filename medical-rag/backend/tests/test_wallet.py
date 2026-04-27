# -*- coding: utf-8 -*-
"""
Test suite cho Wallet system:
  GET  /api/wallet
  GET  /api/wallet/topup-history
  POST /api/checkin/daily
  GET  /api/checkin/status
  POST /api/promo-codes/redeem
  + unit tests cho wallet_service.calculate_chat_cost

Import các model ở module level để Base.metadata nhận diện đủ bảng
trước khi test_engine fixture gọi create_all — conftest chỉ import
4 model cũ nên các wallet table sẽ bị bỏ qua nếu không có dòng này.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# Đăng ký tất cả wallet models vào Base.metadata
from app.db.models.wallet import Wallet  # noqa: F401
from app.db.models.point_transaction import PointTransaction  # noqa: F401
from app.db.models.daily_checkin import DailyCheckin  # noqa: F401
from app.db.models.promo_code import PromoCode, PromoCodeRedemption  # noqa: F401
from app.db.models.chat_usage import ChatUsage  # noqa: F401

from tests.conftest import create_test_user, get_auth_headers
from app.services import wallet_service

pytestmark = pytest.mark.asyncio


# ─────────────────────────────────────────────────────────────────────────────
# Wallet Balance
# ─────────────────────────────────────────────────────────────────────────────

class TestWalletBalance:
    async def test_get_balance_new_user(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """User mới có số dư 0."""
        user = await create_test_user(test_db, email="newwallet@test.com")
        headers = get_auth_headers(str(user.id))

        res = await client.get("/api/wallet", headers=headers)

        assert res.status_code == 200
        assert res.json()["balance"] == 0

    async def test_credit_increases_balance(self, test_db: AsyncSession):
        """credit_points() tăng balance đúng số."""
        user = await create_test_user(test_db, email="credit@test.com")

        wallet = await wallet_service.credit_points(
            test_db, user.id, 100, "ADMIN_BONUS",
            description="Test credit"
        )

        assert wallet.balance == 100

    async def test_deduct_decreases_balance(self, test_db: AsyncSession):
        """deduct_points() giảm balance đúng số."""
        user = await create_test_user(test_db, email="deduct@test.com")
        await wallet_service.credit_points(test_db, user.id, 100, "ADMIN_BONUS")

        wallet = await wallet_service.deduct_points(
            test_db, user.id, 30, "CHAT"
        )

        assert wallet.balance == 70

    async def test_deduct_insufficient_balance_raises_402(
        self, test_db: AsyncSession
    ):
        """Trừ quá số dư → HTTPException 402."""
        from fastapi import HTTPException

        user = await create_test_user(test_db, email="insuf@test.com")
        await wallet_service.credit_points(test_db, user.id, 10, "ADMIN_BONUS")

        with pytest.raises(HTTPException) as exc:
            await wallet_service.deduct_points(test_db, user.id, 100, "CHAT")

        assert exc.value.status_code == 402

    async def test_balance_never_goes_negative(self, test_db: AsyncSession):
        """Trừ khi số dư 0 → HTTPException 402 (service guard, không phải DB)."""
        from fastapi import HTTPException

        user = await create_test_user(test_db, email="neg@test.com")

        with pytest.raises(HTTPException) as exc:
            await wallet_service.deduct_points(test_db, user.id, 50, "CHAT")

        assert exc.value.status_code == 402

    async def test_credit_creates_transaction_record(
        self, test_db: AsyncSession
    ):
        """credit_points() ghi PointTransaction với type=CREDIT."""
        from sqlalchemy import select

        user = await create_test_user(test_db, email="tx_credit@test.com")
        await wallet_service.credit_points(
            test_db, user.id, 50, "DAILY_CHECKIN"
        )

        result = await test_db.execute(
            select(PointTransaction).where(
                PointTransaction.user_id == user.id
            )
        )
        txs = result.scalars().all()

        assert len(txs) == 1
        assert txs[0].type == "CREDIT"
        assert txs[0].points == 50
        assert txs[0].source == "DAILY_CHECKIN"

    async def test_deduct_creates_debit_transaction(
        self, test_db: AsyncSession
    ):
        """deduct_points() ghi PointTransaction với type=DEBIT."""
        from sqlalchemy import select

        user = await create_test_user(test_db, email="tx_debit@test.com")
        await wallet_service.credit_points(test_db, user.id, 100, "ADMIN_BONUS")
        await wallet_service.deduct_points(test_db, user.id, 40, "CHAT")

        result = await test_db.execute(
            select(PointTransaction).where(
                PointTransaction.user_id == user.id,
                PointTransaction.type == "DEBIT"
            )
        )
        txs = result.scalars().all()

        assert len(txs) == 1
        assert txs[0].points == 40
        assert txs[0].balance_before == 100
        assert txs[0].balance_after == 60


# ─────────────────────────────────────────────────────────────────────────────
# Daily Checkin
# ─────────────────────────────────────────────────────────────────────────────

class TestDailyCheckin:
    async def test_checkin_success(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Điểm danh lần đầu thành công, nhận 50 điểm."""
        user = await create_test_user(test_db, email="checkin@test.com")
        headers = get_auth_headers(str(user.id))

        res = await client.post("/api/checkin/daily", headers=headers)

        assert res.status_code == 200
        data = res.json()
        assert data["rewarded_points"] == 50
        assert data["balance"] == 50
        assert data["success"] is True

    async def test_checkin_twice_same_day_fails(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Điểm danh 2 lần cùng ngày → 409."""
        user = await create_test_user(test_db, email="dup_checkin@test.com")
        headers = get_auth_headers(str(user.id))

        await client.post("/api/checkin/daily", headers=headers)
        res = await client.post("/api/checkin/daily", headers=headers)

        assert res.status_code == 409

    async def test_checkin_status_before_checkin(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Status checked_today = false trước khi điểm danh."""
        user = await create_test_user(test_db, email="status_before@test.com")
        headers = get_auth_headers(str(user.id))

        res = await client.get("/api/checkin/status", headers=headers)

        assert res.status_code == 200
        data = res.json()
        assert data["checked_today"] is False
        assert data["reward_points"] == 50

    async def test_checkin_status_after_checkin(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Status checked_today = true sau khi điểm danh."""
        user = await create_test_user(test_db, email="status@test.com")
        headers = get_auth_headers(str(user.id))

        await client.post("/api/checkin/daily", headers=headers)
        res = await client.get("/api/checkin/status", headers=headers)

        assert res.status_code == 200
        assert res.json()["checked_today"] is True

    async def test_checkin_unauthenticated(self, client: AsyncClient):
        """Không có token → 401."""
        res = await client.post("/api/checkin/daily")
        assert res.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Promo Codes
# ─────────────────────────────────────────────────────────────────────────────

class TestPromoCode:
    async def test_redeem_valid_code(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Đổi mã hợp lệ nhận điểm."""
        promo = PromoCode(code="TEST100", points=100, max_usage=10)
        test_db.add(promo)
        await test_db.commit()

        user = await create_test_user(test_db, email="promo@test.com")
        headers = get_auth_headers(str(user.id))

        res = await client.post(
            "/api/promo-codes/redeem",
            json={"code": "TEST100"},
            headers=headers,
        )

        assert res.status_code == 200
        data = res.json()
        assert data["points_received"] == 100
        assert data["balance"] == 100

    async def test_redeem_code_case_insensitive(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Mã không phân biệt hoa/thường nhờ upper().strip() trong service."""
        promo = PromoCode(code="UPPER", points=50, max_usage=10)
        test_db.add(promo)
        await test_db.commit()

        user = await create_test_user(test_db, email="case@test.com")
        headers = get_auth_headers(str(user.id))

        res = await client.post(
            "/api/promo-codes/redeem",
            json={"code": "upper"},  # lowercase → service sẽ upper()
            headers=headers,
        )

        assert res.status_code == 200
        assert res.json()["points_received"] == 50

    async def test_redeem_same_code_twice_fails(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Dùng 1 mã 2 lần → 409."""
        promo = PromoCode(code="ONCE", points=50, max_usage=99)
        test_db.add(promo)
        await test_db.commit()

        user = await create_test_user(test_db, email="once@test.com")
        headers = get_auth_headers(str(user.id))

        await client.post(
            "/api/promo-codes/redeem", json={"code": "ONCE"}, headers=headers
        )
        res = await client.post(
            "/api/promo-codes/redeem", json={"code": "ONCE"}, headers=headers
        )

        assert res.status_code == 409

    async def test_redeem_invalid_code(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Mã không tồn tại → 404."""
        user = await create_test_user(test_db, email="invalid@test.com")
        headers = get_auth_headers(str(user.id))

        res = await client.post(
            "/api/promo-codes/redeem",
            json={"code": "NOTEXIST"},
            headers=headers,
        )

        assert res.status_code == 404

    async def test_redeem_maxed_out_code(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Mã đã hết lượt (used_count >= max_usage) → 410."""
        promo = PromoCode(code="USED", points=50, max_usage=1, used_count=1)
        test_db.add(promo)
        await test_db.commit()

        user = await create_test_user(test_db, email="maxed@test.com")
        headers = get_auth_headers(str(user.id))

        res = await client.post(
            "/api/promo-codes/redeem",
            json={"code": "USED"},
            headers=headers,
        )

        assert res.status_code == 410

    async def test_redeem_increments_used_count(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Sau khi đổi mã, used_count tăng lên 1."""
        from sqlalchemy import select

        promo = PromoCode(code="COUNTER", points=10, max_usage=99)
        test_db.add(promo)
        await test_db.commit()

        user = await create_test_user(test_db, email="counter@test.com")
        headers = get_auth_headers(str(user.id))

        await client.post(
            "/api/promo-codes/redeem",
            json={"code": "COUNTER"},
            headers=headers,
        )

        await test_db.refresh(promo)
        assert promo.used_count == 1

    async def test_topup_history_shows_credit_only(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """GET /api/wallet/topup-history chỉ trả CREDIT, không có DEBIT."""
        user = await create_test_user(test_db, email="hist@test.com")
        headers = get_auth_headers(str(user.id))

        await wallet_service.credit_points(
            test_db, user.id, 100, "ADMIN_BONUS"
        )
        await wallet_service.deduct_points(
            test_db, user.id, 10, "CHAT"
        )

        res = await client.get("/api/wallet/topup-history", headers=headers)

        assert res.status_code == 200
        txs = res.json()
        assert len(txs) == 1
        assert all(tx["type"] == "CREDIT" for tx in txs)

    async def test_topup_history_empty_for_new_user(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """User chưa có giao dịch → lịch sử rỗng."""
        user = await create_test_user(test_db, email="empty_hist@test.com")
        headers = get_auth_headers(str(user.id))

        res = await client.get("/api/wallet/topup-history", headers=headers)

        assert res.status_code == 200
        assert res.json() == []


# ─────────────────────────────────────────────────────────────────────────────
# calculate_chat_cost — pure unit tests (không cần DB)
# ─────────────────────────────────────────────────────────────────────────────

class TestCalculateChatCost:
    def test_minimum_1_point(self):
        """Dù chat ngắn (ít token) vẫn tốn tối thiểu 1 điểm."""
        _, _, points = wallet_service.calculate_chat_cost(10, 10)
        assert points >= 1

    def test_zero_tokens_still_1_point(self):
        """0 token (fallback khi Gemini không trả usage) → 1 điểm."""
        _, _, points = wallet_service.calculate_chat_cost(0, 0)
        assert points == 1

    def test_longer_chat_costs_more(self):
        """Chat với nhiều token hơn → điểm cao hơn hoặc bằng."""
        _, _, short = wallet_service.calculate_chat_cost(100, 50)
        _, _, long_ = wallet_service.calculate_chat_cost(5000, 2000)
        assert long_ >= short

    def test_returns_three_values(self):
        """Hàm luôn trả tuple (cost_usd, cost_vnd, charged_points)."""
        result = wallet_service.calculate_chat_cost(1000, 500)
        assert len(result) == 3
        cost_usd, cost_vnd, charged_points = result
        assert isinstance(cost_usd, float)
        assert isinstance(cost_vnd, int)
        assert isinstance(charged_points, int)

    def test_cost_usd_proportional_to_tokens(self):
        """Chi phí USD tỷ lệ thuận với số token."""
        cost_usd_small, _, _ = wallet_service.calculate_chat_cost(1000, 0)
        cost_usd_large, _, _ = wallet_service.calculate_chat_cost(2000, 0)
        assert cost_usd_large == pytest.approx(cost_usd_small * 2, rel=1e-6)
