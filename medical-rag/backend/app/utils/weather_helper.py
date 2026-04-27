# -*- coding: utf-8 -*-
"""
Helper: map thời tiết → nguy cơ bệnh.
Tách riêng để dễ test và mở rộng rule sau này.
"""
from dataclasses import dataclass


@dataclass
class WeatherData:
    temp_c: float
    humidity: int
    condition: str
    city: str = "Hanoi"


def map_weather_to_health_risks(data: WeatherData) -> list[str]:
    """
    Rule mapping thời tiết → danh sách bệnh nguy cơ cao.

    Rules (theo thứ tự ưu tiên, có thể match nhiều rule):
    - temp < 20 AND humidity > 80  → Cảm cúm, Viêm họng, Viêm phế quản
    - temp > 35                    → Sốc nhiệt, Mất nước
    - temp > 30 AND humidity > 70  → Sốt xuất huyết, Mất nước, Rôm sảy
    - humidity > 85                → Nấm da, Dị ứng
    - Mặc định                     → Bình thường
    """
    risks: list[str] = []

    # Lạnh + ẩm → bệnh đường hô hấp
    if data.temp_c < 20 and data.humidity > 80:
        risks.extend(["Cảm cúm", "Viêm họng", "Viêm phế quản"])

    # Nóng cực đoan → sốc nhiệt
    if data.temp_c > 35:
        risks.extend(["Sốc nhiệt", "Mất nước"])

    # Nóng + ẩm → muỗi và mất nước
    elif data.temp_c > 30 and data.humidity > 70:
        risks.extend(["Sốt xuất huyết", "Mất nước", "Rôm sảy"])

    # Độ ẩm cao → nấm và dị ứng
    if data.humidity > 85 and not risks:
        risks.extend(["Nấm da", "Dị ứng"])

    # Không có nguy cơ đặc biệt
    if not risks:
        risks.append("Bình thường")

    return list(dict.fromkeys(risks))  # Dedup giữ thứ tự


def get_risk_level(risks: list[str]) -> str:
    """Đánh giá mức độ nguy cơ tổng thể."""
    high_risk = {"Sốc nhiệt", "Sốt xuất huyết", "Viêm phế quản"}
    if any(r in high_risk for r in risks):
        return "cao"
    if risks == ["Bình thường"]:
        return "thấp"
    return "trung bình"
