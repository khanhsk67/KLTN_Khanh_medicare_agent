# -*- coding: utf-8 -*-
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.services import wallet_service

router = APIRouter(prefix="/wallet", tags=["Wallet"])


class WalletResponse(BaseModel):
    balance: int
    message: str = "OK"


class TransactionResponse(BaseModel):
    id: str
    type: str
    source: str
    points: int
    balance_before: int
    balance_after: int
    description: str | None
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("", response_model=WalletResponse)
async def get_wallet(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Lấy số dư hiện tại."""
    balance = await wallet_service.get_balance(db, current_user.id)
    return WalletResponse(balance=balance)


@router.get("/topup-history", response_model=list[TransactionResponse])
async def get_topup_history(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Lịch sử nạp điểm (chỉ CREDIT transactions)."""
    txs = await wallet_service.get_topup_history(db, current_user.id)
    return [
        TransactionResponse(
            id=str(tx.id),
            type=tx.type,
            source=tx.source,
            points=tx.points,
            balance_before=tx.balance_before,
            balance_after=tx.balance_after,
            description=tx.description,
            created_at=tx.created_at,
        )
        for tx in txs
    ]
