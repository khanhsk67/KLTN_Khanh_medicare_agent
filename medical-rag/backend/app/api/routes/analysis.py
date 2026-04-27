# -*- coding: utf-8 -*-
"""
Analysis Routes — thống kê và phân tích sức khỏe người dùng.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.models.schemas import AnalysisResponse, DetailedStats, HealthDashboard, HealthTimelineItem, TimelineEvent
from app.services import analysis_service

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


# ---------------------------------------------------------------------------
# GET /api/analysis/summary?period_days=30
# ---------------------------------------------------------------------------

@router.get("/summary", response_model=AnalysisResponse)
async def analysis_summary(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    period_days: int = Query(30, ge=1, le=365),
) -> AnalysisResponse:
    """
    Trả về bản phân tích y tế mới nhất của user trong khoảng period_days ngày.
    404 nếu chưa có dữ liệu.
    """
    result = await analysis_service.get_user_analysis(db, current_user.id, period_days)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No analysis data found for this period",
        )
    return result


# ---------------------------------------------------------------------------
# GET /api/analysis/timeline
# ---------------------------------------------------------------------------

@router.get("/timeline", response_model=list[TimelineEvent])
async def health_timeline(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[TimelineEvent]:
    """Trả về timeline số sessions và messages theo từng ngày (toàn bộ lịch sử)."""
    return await analysis_service.get_health_timeline(db, current_user.id)


# ---------------------------------------------------------------------------
# GET /api/analysis/statistics
# ---------------------------------------------------------------------------

@router.get("/statistics", response_model=DetailedStats)
async def statistics(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    period_days: int = Query(30, ge=1, le=365),
) -> DetailedStats:
    """
    Thống kê chi tiết: tổng sessions/messages/records, phân phối severity/urgency,
    top symptoms/conditions và timeline.
    """
    return await analysis_service.get_statistics(db, current_user.id, period_days)


# ---------------------------------------------------------------------------
# GET /api/analysis/dashboard?days=30
# ---------------------------------------------------------------------------

@router.get("/dashboard", response_model=HealthDashboard)
async def dashboard(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    days: int = Query(30, ge=1, le=365),
) -> HealthDashboard:
    """
    Dashboard tổng quan sức khỏe: sessions, messages, top symptoms,
    phân phối severity và tần suất tư vấn theo ngày.
    """
    return await analysis_service.get_dashboard(db, current_user.id, days)


# ---------------------------------------------------------------------------
# GET /api/analysis/health-timeline?days=30
# ---------------------------------------------------------------------------

@router.get("/health-timeline", response_model=list[HealthTimelineItem])
async def health_timeline_items(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    days: int = Query(30, ge=1, le=365),
) -> list[HealthTimelineItem]:
    """
    Danh sách các sự kiện sức khỏe (từ TreatmentRecord) trong khoảng days ngày,
    mỗi item gồm triệu chứng chính, chuyên khoa, mức độ và session liên quan.
    """
    return await analysis_service.get_health_timeline_items(db, current_user.id, days)
