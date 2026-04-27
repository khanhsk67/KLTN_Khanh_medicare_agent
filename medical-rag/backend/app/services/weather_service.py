# -*- coding: utf-8 -*-
"""
Service: gọi WeatherAPI và cache kết quả.
Dùng httpx.AsyncClient (chuẩn async FastAPI) — KHÔNG dùng axios/requests.
"""
import time
import httpx
from fastapi import HTTPException, status
from app.core.config import settings
from app.utils.weather_helper import WeatherData


# Simple in-memory cache — tránh spam WeatherAPI
_cache: dict = {}
_cache_time: dict = {}


async def fetch_hanoi_weather() -> WeatherData:
    """
    Fetch thời tiết Hà Nội từ WeatherAPI.
    Cache kết quả WEATHER_CACHE_SECONDS giây.
    """
    cache_key = "hanoi_weather"
    now = time.time()

    # Trả cache nếu còn hạn
    if (
        cache_key in _cache
        and now - _cache_time.get(cache_key, 0) < settings.WEATHER_CACHE_SECONDS
    ):
        return _cache[cache_key]

    if not settings.WEATHER_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WEATHER_API_KEY chưa được cấu hình trong .env"
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                settings.WEATHER_API_URL,
                params={
                    "key": settings.WEATHER_API_KEY,
                    "q": "Hanoi",
                    "lang": "vi"
                }
            )
            response.raise_for_status()

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="WeatherAPI timeout — thử lại sau"
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"WeatherAPI lỗi: {e.response.status_code}"
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Không thể kết nối WeatherAPI: {str(e)}"
        )

    try:
        raw = response.json()
        weather = WeatherData(
            temp_c=raw["current"]["temp_c"],
            humidity=raw["current"]["humidity"],
            condition=raw["current"]["condition"]["text"],
            city=raw["location"]["name"]
        )
    except (KeyError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"WeatherAPI trả về dữ liệu không hợp lệ: {str(e)}"
        )

    # Lưu cache
    _cache[cache_key] = weather
    _cache_time[cache_key] = now

    return weather
