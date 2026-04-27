# -*- coding: utf-8 -*-
import uuid as _uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.services import promo_service, wallet_service

router = APIRouter(prefix="/promo-codes", tags=["Promo Codes"])


class RedeemRequest(BaseModel):
    code: str


@router.post("/redeem")
async def redeem_code(
    body: RedeemRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Đổi mã promo lấy điểm.
    Mỗi user chỉ dùng mỗi mã 1 lần.
    """
    return await promo_service.redeem_promo_code(
        db, current_user.id, body.code
    )


@router.post("/admin/add-points", tags=["Admin"])
async def admin_add_points(
    user_id: str,
    points: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    reason: str = "Admin thưởng điểm",
):
    """
    Admin cộng điểm thủ công cho user.
    TODO: Thêm role check sau khi có phân quyền.
    """
    wallet = await wallet_service.credit_points(
        db=db,
        user_id=_uuid.UUID(user_id),
        points=points,
        source="ADMIN_BONUS",
        description=reason,
    )
    return {
        "success": True,
        "points_added": points,
        "new_balance": wallet.balance,
    }
