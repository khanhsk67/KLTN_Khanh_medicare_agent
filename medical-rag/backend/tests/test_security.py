# -*- coding: utf-8 -*-
"""
Unit tests cho app.core.security — không cần DB hay HTTP client.

Lưu ý: create_access_token(data: dict, ...) nhận DICT với key "sub",
KHÔNG phải str trực tiếp. Ví dụ: create_access_token({"sub": "user-123"})
"""
import pytest
from fastapi import HTTPException

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


# ═════════════════════════════════════════════════════════════════════════════
# TestPasswordHashing
# ═════════════════════════════════════════════════════════════════════════════


class TestPasswordHashing:
    def test_hash_is_different_from_plain(self):
        """Hash bcrypt khác với plain text."""
        hashed = hash_password("MyPassword123")
        assert hashed != "MyPassword123"
        assert len(hashed) > 20  # bcrypt hash dài

    def test_verify_correct_password(self):
        """verify_password trả True với đúng mật khẩu."""
        hashed = hash_password("CorrectPass")
        assert verify_password("CorrectPass", hashed) is True

    def test_verify_wrong_password(self):
        """verify_password trả False với sai mật khẩu."""
        hashed = hash_password("CorrectPass")
        assert verify_password("WrongPass", hashed) is False

    def test_same_password_different_hash(self):
        """bcrypt tạo salt khác nhau → cùng plain text cho hash khác nhau."""
        h1 = hash_password("SamePass")
        h2 = hash_password("SamePass")
        assert h1 != h2  # salt khác nhau mỗi lần

    def test_verify_empty_password(self):
        """Mật khẩu rỗng vẫn có thể hash và verify."""
        hashed = hash_password("")
        assert verify_password("", hashed) is True
        assert verify_password("notempty", hashed) is False

    def test_verify_with_unicode(self):
        """Mật khẩu Unicode (tiếng Việt) hash/verify đúng."""
        pw = "Mật_khẩu_123!@#"
        hashed = hash_password(pw)
        assert verify_password(pw, hashed) is True
        assert verify_password("WrongPass", hashed) is False


# ═════════════════════════════════════════════════════════════════════════════
# TestJWTToken
# ═════════════════════════════════════════════════════════════════════════════


class TestJWTToken:
    def test_access_token_decode(self):
        """
        create_access_token({"sub": ...}) → JWT payload chứa sub và type="access".
        QUAN TRỌNG: Truyền dict, không phải str.
        """
        token = create_access_token({"sub": "user-123"})
        payload = decode_token(token)
        assert payload["sub"] == "user-123"
        assert payload["type"] == "access"

    def test_refresh_token_decode(self):
        """create_refresh_token(user_id: str) → (token, jti); payload chứa sub, jti, type="refresh"."""
        token, jti = create_refresh_token("user-456")
        payload = decode_token(token)
        assert payload["sub"] == "user-456"
        assert payload["type"] == "refresh"
        assert payload["jti"] == jti

    def test_invalid_token_raises_401(self):
        """Token không hợp lệ → decode_token raises HTTPException 401."""
        with pytest.raises(HTTPException) as exc_info:
            decode_token("invalid.token.string")
        assert exc_info.value.status_code == 401

    def test_garbage_token_raises_401(self):
        """Token rác hoàn toàn → 401."""
        with pytest.raises(HTTPException) as exc_info:
            decode_token("not-even-a-jwt")
        assert exc_info.value.status_code == 401

    def test_access_token_type_is_access(self):
        """Access token có type="access", KHÔNG phải "refresh"."""
        token = create_access_token({"sub": "test-user"})
        payload = decode_token(token)
        assert payload["type"] == "access"
        assert payload["type"] != "refresh"

    def test_refresh_token_type_is_refresh(self):
        """Refresh token có type="refresh", KHÔNG phải "access"."""
        token, _ = create_refresh_token("test-user")
        payload = decode_token(token)
        assert payload["type"] == "refresh"
        assert payload["type"] != "access"

    def test_access_token_preserves_extra_claims(self):
        """Claims thêm trong dict được bảo tồn trong payload."""
        token = create_access_token({"sub": "user-789", "role": "admin"})
        payload = decode_token(token)
        assert payload["sub"] == "user-789"
        assert payload.get("role") == "admin"

    def test_access_and_refresh_tokens_are_different(self):
        """Cùng user_id → access token và refresh token là hai chuỗi khác nhau."""
        user_id = "same-user-id"
        access = create_access_token({"sub": user_id})
        refresh, _ = create_refresh_token(user_id)
        assert access != refresh

    def test_token_has_exp_claim(self):
        """JWT phải có claim 'exp' (expiration time)."""
        token = create_access_token({"sub": "test"})
        payload = decode_token(token)
        assert "exp" in payload

    def test_two_access_tokens_different_due_to_time(self):
        """
        Hai access token tạo lần lượt có thể giống nhau nếu tạo trong cùng giây.
        Test này chỉ kiểm tra cả hai đều decode được (không test uniqueness).
        """
        t1 = create_access_token({"sub": "u1"})
        t2 = create_access_token({"sub": "u1"})
        # Cả hai phải decode được mà không lỗi
        p1 = decode_token(t1)
        p2 = decode_token(t2)
        assert p1["sub"] == "u1"
        assert p2["sub"] == "u1"
