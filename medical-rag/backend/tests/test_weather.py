# -*- coding: utf-8 -*-
import pytest
from unittest.mock import AsyncMock, patch
from app.utils.weather_helper import WeatherData, map_weather_to_health_risks, get_risk_level


class TestWeatherHelper:
    def test_cold_humid_returns_respiratory_risks(self):
        data = WeatherData(temp_c=15, humidity=85, condition="Mưa phùn")
        risks = map_weather_to_health_risks(data)
        assert "Cảm cúm" in risks
        assert "Viêm họng" in risks

    def test_hot_humid_returns_dengue_risk(self):
        data = WeatherData(temp_c=33, humidity=75, condition="Nắng nóng")
        risks = map_weather_to_health_risks(data)
        assert "Sốt xuất huyết" in risks
        assert "Mất nước" in risks

    def test_extreme_heat_returns_heatstroke(self):
        data = WeatherData(temp_c=38, humidity=60, condition="Nắng gắt")
        risks = map_weather_to_health_risks(data)
        assert "Sốc nhiệt" in risks

    def test_normal_weather_returns_binh_thuong(self):
        data = WeatherData(temp_c=25, humidity=60, condition="Quang mây")
        risks = map_weather_to_health_risks(data)
        assert risks == ["Bình thường"]

    def test_no_duplicate_risks(self):
        data = WeatherData(temp_c=33, humidity=75, condition="Nắng")
        risks = map_weather_to_health_risks(data)
        assert len(risks) == len(set(risks))

    def test_risk_level_cao(self):
        assert get_risk_level(["Sốt xuất huyết"]) == "cao"

    def test_risk_level_thap(self):
        assert get_risk_level(["Bình thường"]) == "thấp"


class TestWeatherEndpoint:
    @pytest.mark.asyncio
    async def test_get_hanoi_weather_success(self, client, test_db):
        from tests.conftest import create_test_user, get_auth_headers
        user = await create_test_user(test_db, email="weather@example.com")
        headers = get_auth_headers(str(user.id))

        mock_weather_data = {
            "location": {"name": "Hanoi"},
            "current": {
                "temp_c": 28.0,
                "humidity": 75,
                "condition": {"text": "Partly cloudy"}
            }
        }

        with patch("app.services.weather_service.httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.json.return_value = mock_weather_data
            mock_response.raise_for_status = AsyncMock()
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            res = await client.get("/api/health-risk/hanoi", headers=headers)

        assert res.status_code == 200
        data = res.json()
        assert data["city"] == "Hanoi"
        assert "temperature" in data
        assert "risk_diseases" in data
        assert isinstance(data["risk_diseases"], list)

    @pytest.mark.asyncio
    async def test_public_endpoint_no_auth(self, client):
        mock_weather_data = {
            "location": {"name": "Hanoi"},
            "current": {
                "temp_c": 25.0,
                "humidity": 65,
                "condition": {"text": "Clear"}
            }
        }
        with patch("app.services.weather_service.httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.json.return_value = mock_weather_data
            mock_response.raise_for_status = AsyncMock()
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            res = await client.get("/api/health-risk/hanoi/public")

        assert res.status_code == 200
