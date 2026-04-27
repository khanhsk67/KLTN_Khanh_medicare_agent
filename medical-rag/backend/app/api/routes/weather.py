# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.core.security import get_current_user
from app.db.models.user import User
from app.services.weather_service import fetch_hanoi_weather
from app.utils.weather_helper import map_weather_to_health_risks, get_risk_level

router = APIRouter(prefix="/health-risk", tags=["Weather & Health Risk"])


class HealthRiskResponse(BaseModel):
    city: str
    temperature: float
    humidity: int
    condition: str
    risk_level: str          # "thấp" | "trung bình" | "cao"
    risk_diseases: list[str]
    advice: str
    cached: bool = False


def _build_advice(risk_level: str, risks: list[str]) -> str:
    """Tạo lời khuyên ngắn gọn dựa trên mức nguy cơ."""
    if risk_level == "cao":
        return (
            "Nguy cơ cao — hãy uống đủ nước, tránh ra ngoài giờ cao điểm "
            "và theo dõi sức khỏe thường xuyên."
        )
    if risk_level == "trung bình":
        return (
            "Thời tiết có thể ảnh hưởng sức khỏe — "
            "giữ ấm hoặc mát tùy điều kiện, tăng cường vitamin C."
        )
    return "Thời tiết thuận lợi — duy trì lối sống lành mạnh."


@router.get(
    "/hanoi",
    response_model=HealthRiskResponse,
    summary="Cảnh báo nguy cơ bệnh theo thời tiết Hà Nội"
)
async def get_hanoi_health_risk(
    current_user: User = Depends(get_current_user)
):
    """
    Lấy thời tiết Hà Nội hiện tại và đánh giá nguy cơ bệnh.
    Yêu cầu đăng nhập — kết quả được cache 5 phút.
    """
    weather = await fetch_hanoi_weather()
    risks = map_weather_to_health_risks(weather)
    risk_level = get_risk_level(risks)

    return HealthRiskResponse(
        city=weather.city,
        temperature=weather.temp_c,
        humidity=weather.humidity,
        condition=weather.condition,
        risk_level=risk_level,
        risk_diseases=risks,
        advice=_build_advice(risk_level, risks)
    )


@router.get(
    "/hanoi/public",
    response_model=HealthRiskResponse,
    summary="Cảnh báo thời tiết (public — không cần đăng nhập)"
)
async def get_hanoi_health_risk_public():
    """
    Endpoint public — không cần JWT.
    Dùng cho trang landing page hoặc widget embed.
    """
    weather = await fetch_hanoi_weather()
    risks = map_weather_to_health_risks(weather)
    risk_level = get_risk_level(risks)

    return HealthRiskResponse(
        city=weather.city,
        temperature=weather.temp_c,
        humidity=weather.humidity,
        condition=weather.condition,
        risk_level=risk_level,
        risk_diseases=risks,
        advice=_build_advice(risk_level, risks)
    )
