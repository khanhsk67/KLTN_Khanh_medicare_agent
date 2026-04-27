# -*- coding: utf-8 -*-
"""
Test suite cho Auth endpoints:
  POST /api/auth/register
  POST /api/auth/login
  GET  /api/auth/me
  POST /api/auth/refresh
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from tests.conftest import create_test_user, get_auth_headers

pytestmark = pytest.mark.asyncio


class TestRegister:
    async def test_register_success(self, client: AsyncClient):
        """Đăng ký thành công với thông tin hợp lệ → 201."""
        res = await client.post(
            "/api/auth/register",
            json={
                "email": "newuser@example.com",
                "full_name": "Nguyen Van A",
                "password": "SecurePass123",
            },
        )
        assert res.status_code == 201
        data = res.json()
        assert data["email"] == "newuser@example.com"
        assert data["full_name"] == "Nguyen Van A"
        assert "password_hash" not in data  # Không được lộ hash
        assert "id" in data

    async def test_register_duplicate_email(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Email đã tồn tại → 400 (auth_service raises HTTP_400_BAD_REQUEST)."""
        await create_test_user(test_db, email="dup@example.com")

        res = await client.post(
            "/api/auth/register",
            json={
                "email": "dup@example.com",
                "full_name": "Nguyen Van B",
                "password": "SecurePass123",
            },
        )
        assert res.status_code == 400
        assert "Email" in res.json()["detail"] or "email" in res.json()["detail"].lower()

    async def test_register_invalid_email(self, client: AsyncClient):
        """Email không hợp lệ → 422 (Pydantic EmailStr validation)."""
        res = await client.post(
            "/api/auth/register",
            json={
                "email": "not-an-email",
                "full_name": "Test User",
                "password": "SecurePass123",
            },
        )
        assert res.status_code == 422

    async def test_register_password_too_short(self, client: AsyncClient):
        """Mật khẩu < 8 ký tự → 422 (Field min_length=8)."""
        res = await client.post(
            "/api/auth/register",
            json={
                "email": "test@example.com",
                "full_name": "Test User",
                "password": "123",
            },
        )
        assert res.status_code == 422

    async def test_register_name_too_short(self, client: AsyncClient):
        """Họ tên rỗng (min_length=1) → 422."""
        res = await client.post(
            "/api/auth/register",
            json={
                "email": "test@example.com",
                "full_name": "",
                "password": "SecurePass123",
            },
        )
        assert res.status_code == 422

    async def test_register_missing_required_fields(self, client: AsyncClient):
        """Thiếu required fields → 422."""
        res = await client.post(
            "/api/auth/register",
            json={"email": "test@example.com"},  # Thiếu full_name và password
        )
        assert res.status_code == 422


class TestLogin:
    async def test_login_success(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Đăng nhập thành công → 200 với access_token + refresh_token."""
        await create_test_user(
            test_db,
            email="login@example.com",
            password="MyPassword123",
        )
        res = await client.post(
            "/api/auth/login",
            json={"email": "login@example.com", "password": "MyPassword123"},
        )
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert "expires_in" in data

    async def test_login_wrong_password(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Sai mật khẩu → 401."""
        await create_test_user(test_db, email="user@example.com")
        res = await client.post(
            "/api/auth/login",
            json={"email": "user@example.com", "password": "WrongPassword"},
        )
        assert res.status_code == 401

    async def test_login_nonexistent_email(self, client: AsyncClient):
        """Email không tồn tại → 401."""
        res = await client.post(
            "/api/auth/login",
            json={"email": "nobody@example.com", "password": "AnyPassword123"},
        )
        assert res.status_code == 401

    async def test_login_returns_json_not_formdata(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Endpoint nhận JSON body — gửi FormData phải fail (401 hoặc 422)."""
        await create_test_user(test_db, email="json@example.com")
        # Gửi form data thay vì JSON → FastAPI không parse được UserLogin
        res = await client.post(
            "/api/auth/login",
            data={"email": "json@example.com", "password": "TestPass123"},
        )
        assert res.status_code in [401, 422]

    async def test_login_inactive_user_returns_403(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """User bị vô hiệu hóa (is_active=False) → 403."""
        from app.db.models.user import User
        from app.core.security import hash_password

        inactive = User(
            email="inactive@example.com",
            full_name="Inactive User",
            password_hash=hash_password("MyPassword123"),
            is_active=False,
        )
        test_db.add(inactive)
        await test_db.commit()

        res = await client.post(
            "/api/auth/login",
            json={"email": "inactive@example.com", "password": "MyPassword123"},
        )
        assert res.status_code == 403


class TestProfile:
    async def test_get_profile_authenticated(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """User đã đăng nhập lấy được profile đầy đủ."""
        user = await create_test_user(test_db, email="me@example.com")
        headers = get_auth_headers(str(user.id))

        res = await client.get("/api/auth/me", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["email"] == "me@example.com"
        assert "password_hash" not in data
        assert "id" in data
        assert "full_name" in data

    async def test_get_profile_unauthenticated(self, client: AsyncClient):
        """Không có token → 401."""
        res = await client.get("/api/auth/me")
        assert res.status_code == 401

    async def test_get_profile_invalid_token(self, client: AsyncClient):
        """Token giả → 401."""
        res = await client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer fake.token.here"},
        )
        assert res.status_code == 401

    async def test_get_profile_expired_token_format(self, client: AsyncClient):
        """Bearer header thiếu giá trị → 401 hoặc 403."""
        res = await client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer "},
        )
        assert res.status_code in [401, 403]


class TestRefreshToken:
    async def test_refresh_token_success(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """Refresh token hợp lệ → 200 với access_token mới."""
        from app.core.security import create_refresh_token

        user = await create_test_user(test_db)
        refresh_token = create_refresh_token(str(user.id))

        res = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert "refresh_token" in data

    async def test_refresh_with_access_token_fails(
        self, client: AsyncClient, test_db: AsyncSession
    ):
        """
        Dùng access token để refresh phải thất bại → 401.
        create_access_token nhận dict {"sub": ...}, KHÔNG phải str trực tiếp.
        """
        user = await create_test_user(test_db)
        # Tạo access token (type="access") — auth_service kiểm tra type=="refresh"
        access_token = create_access_token({"sub": str(user.id)})

        res = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": access_token},
        )
        assert res.status_code == 401

    async def test_refresh_with_invalid_token(self, client: AsyncClient):
        """Token không hợp lệ → 401."""
        res = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": "invalid.token.here"},
        )
        assert res.status_code == 401
