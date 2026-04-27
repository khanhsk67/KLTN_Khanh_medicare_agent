# -*- coding: utf-8 -*-
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, decode_token, hash_password, verify_password
from app.db.models.chat_session import ChatSession
from app.db.models.user import User
from app.models.schemas import TokenResponse, UserCreate, UserProfile, UserResponse


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
        await db.flush()  # get user.id without committing
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

        access_token = create_access_token(data={"sub": str(user.id)})

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

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
