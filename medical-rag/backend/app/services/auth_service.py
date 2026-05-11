# -*- coding: utf-8 -*-
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.db.models.refresh_token import RefreshToken
from app.db.models.user import User
from app.models.schemas import TokenResponse, UserCreate, UserProfile


class AuthService:

    # ------------------------------------------------------------------
    # Register
    # ------------------------------------------------------------------
    @staticmethod
    async def register(db: AsyncSession, user_create: UserCreate) -> User:
        # Check duplicate email
        result = await db.execute(select(User).where(User.email == user_create.email))
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

        user = User(
            id=uuid.uuid4(),
            email=user_create.email,
            password_hash=hash_password(user_create.password),
            full_name=user_create.full_name,
            nickname=user_create.nickname,
            is_active=True,
        )
        db.add(user)
        await db.flush()
        return user

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------
    @staticmethod
    async def login(db: AsyncSession, email: str, password: str) -> TokenResponse:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user or not verify_password(password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is disabled",
            )

        # Tạo access token
        access_token = create_access_token(data={"sub": str(user.id)})

        # Tạo refresh token
        refresh_token, jti = create_refresh_token(str(user.id))

        # Lưu refresh token vào database
        token_hash = hash_token(refresh_token)
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        db_refresh_token = RefreshToken(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            is_revoked=False,
        )
        db.add(db_refresh_token)
        await db.flush()

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    # ------------------------------------------------------------------
    # Refresh Access Token
    # ------------------------------------------------------------------
    @staticmethod
    async def refresh_access_token(db: AsyncSession, refresh_token: str) -> TokenResponse:
        # Decode refresh token
        payload = decode_token(refresh_token)

        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )

        user_id = payload.get("sub")
        jti = payload.get("jti")

        if not user_id or not jti:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )

        # Kiểm tra token trong database
        token_hash = hash_token(refresh_token)
        result = await db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.is_revoked == False,
            )
        )
        db_token = result.scalar_one_or_none()

        if not db_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token not found or revoked",
            )

        # Kiểm tra expiry. SQLite có thể trả naive datetime nên coerce về UTC-aware.
        expires_at = db_token.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token expired",
            )

        # Kiểm tra user
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
            )

        # Revoke old refresh token (rotation)
        db_token.is_revoked = True
        db_token.revoked_at = datetime.now(timezone.utc)

        # Tạo tokens mới
        new_access_token = create_access_token(data={"sub": str(user.id)})
        new_refresh_token, new_jti = create_refresh_token(str(user.id))

        # Lưu refresh token mới
        new_token_hash = hash_token(new_refresh_token)
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        new_db_token = RefreshToken(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=new_token_hash,
            expires_at=expires_at,
            is_revoked=False,
        )
        db.add(new_db_token)
        await db.flush()

        return TokenResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    # ------------------------------------------------------------------
    # Logout (Revoke refresh token)
    # ------------------------------------------------------------------
    @staticmethod
    async def logout(db: AsyncSession, user_id: str, refresh_token: str | None = None) -> None:
        """
        Revoke refresh token khi logout.
        Nếu không có refresh_token, revoke tất cả tokens của user.
        """
        if refresh_token:
            # Revoke token cụ thể
            token_hash = hash_token(refresh_token)
            result = await db.execute(
                select(RefreshToken).where(
                    RefreshToken.token_hash == token_hash,
                    RefreshToken.user_id == user_id,
                    RefreshToken.is_revoked == False,
                )
            )
            db_token = result.scalar_one_or_none()
            if db_token:
                db_token.is_revoked = True
                db_token.revoked_at = datetime.now(timezone.utc)
        else:
            # Revoke tất cả tokens của user
            result = await db.execute(
                select(RefreshToken).where(
                    RefreshToken.user_id == user_id,
                    RefreshToken.is_revoked == False,
                )
            )
            tokens = result.scalars().all()
            for token in tokens:
                token.is_revoked = True
                token.revoked_at = datetime.now(timezone.utc)

        await db.flush()

    # ------------------------------------------------------------------
    # Get profile
    # ------------------------------------------------------------------
    @staticmethod
    async def get_profile(db: AsyncSession, user_id: str) -> UserProfile:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        return UserProfile.model_validate(user)
