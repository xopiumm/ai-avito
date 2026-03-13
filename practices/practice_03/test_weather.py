"""
Тесты для GET /weather/{city}

Покрытие:
  Unit:
    - normalize_city: trim, collapse spaces
    - parse_owm_response: правильно маппит поля OWM → WeatherResponse
  Integration (httpx + respx mock, Redis замокан):
    - 200 happy path
    - 200 cache hit (OWM не вызывается)
    - 404 несуществующий город
    - 400 пустое название
    - 503 нет API-ключа
    - 502 OWM недоступен (сетевая ошибка)
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from main import app, normalize_city, parse_owm_response
from models import WeatherResponse

# ── Фикстура: OWM_API_KEY задан ────────────────────────────────────────────────
OWM_KEY = "test_api_key_123"

OWM_HELSINKI = {
    "name": "Helsinki",
    "sys": {"country": "FI"},
    "main": {
        "temp": 2.5,
        "feels_like": -0.8,
        "humidity": 80,
    },
    "weather": [{"description": "облачно с прояснениями"}],
    "wind": {"speed": 4.2},
}


# ── Синхронный клиент (без поднятия Redis) ──────────────────────────────────────

@pytest.fixture()
def client(monkeypatch):
    """TestClient с заглушкой Redis (ping raises → redis_client=None)."""
    monkeypatch.setenv("OWM_API_KEY", OWM_KEY)

    # Глобальный redis_client → None (Redis недоступен)
    import main as main_module
    main_module.redis_client = None

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ══════════════════════════════════════════════════════════════════════════════
# Unit-тесты
# ══════════════════════════════════════════════════════════════════════════════

class TestNormalizeCity:
    def test_trims_leading_trailing(self):
        assert normalize_city("  Helsinki  ") == "Helsinki"

    def test_collapses_internal_spaces(self):
        assert normalize_city("New   York") == "New York"

    def test_empty_after_strip(self):
        assert normalize_city("   ") == ""

    def test_no_change_needed(self):
        assert normalize_city("Oslo") == "Oslo"

    def test_unicode_preserved(self):
        assert normalize_city("  São Paulo  ") == "São Paulo"


class TestParseOwmResponse:
    def test_fields_mapped_correctly(self):
        result = parse_owm_response(OWM_HELSINKI)
        assert result.city == "Helsinki"
        assert result.country == "FI"
        assert result.temperature_celsius == 2.5
        assert result.feels_like_celsius == -0.8
        assert result.humidity_percent == 80
        assert result.description == "облачно с прояснениями"
        assert result.wind_speed_mps == 4.2
        assert result.cached is False

    def test_cached_flag_propagated(self):
        result = parse_owm_response(OWM_HELSINKI, cached=True)
        assert result.cached is True


# ══════════════════════════════════════════════════════════════════════════════
# Integration-тесты (respx мокает HTTP, Redis=None)
# ══════════════════════════════════════════════════════════════════════════════

class TestGetWeatherEndpoint:

    @respx.mock
    def test_happy_path_200(self, client):
        """GET /weather/Helsinki → 200 + корректные поля."""
        respx.get("https://api.openweathermap.org/data/2.5/weather").mock(
            return_value=httpx.Response(200, json=OWM_HELSINKI)
        )

        resp = client.get("/weather/Helsinki")
        assert resp.status_code == 200
        body = resp.json()
        assert body["city"] == "Helsinki"
        assert body["country"] == "FI"
        assert body["temperature_celsius"] == 2.5
        assert body["humidity_percent"] == 80
        assert body["cached"] is False

    @respx.mock
    def test_city_not_found_404(self, client):
        """GET /weather/NoSuchCity_12345 → 404."""
        respx.get("https://api.openweathermap.org/data/2.5/weather").mock(
            return_value=httpx.Response(404, json={"message": "city not found"})
        )

        resp = client.get("/weather/NoSuchCity_12345")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_empty_city_400(self, client):
        """GET /weather/%20%20%20 (только пробелы после decode) → 400."""
        import main as main_module
        # Напрямую вызываем через TestClient, имитируем нормализованно-пустой город
        with patch.object(main_module, "normalize_city", return_value=""):
            resp = client.get("/weather/   ")
            assert resp.status_code == 400

    def test_no_api_key_503(self, monkeypatch):
        """GET /weather/Helsinki без OWM_API_KEY → 503."""
        import main as main_module
        main_module.redis_client = None

        monkeypatch.setenv("OWM_API_KEY", "")
        import importlib
        # OWM_API_KEY читается при старте через os.getenv — патчим на уровне модуля
        with patch.object(main_module, "OWM_API_KEY", ""):
            with TestClient(app, raise_server_exceptions=False) as c:
                resp = c.get("/weather/Helsinki")
        assert resp.status_code == 503

    @respx.mock
    def test_owm_network_error_502(self, client):
        """GET /weather/Helsinki при сетевой ошибке OWM → 502."""
        respx.get("https://api.openweathermap.org/data/2.5/weather").mock(
            side_effect=httpx.ConnectError("connection refused")
        )

        resp = client.get("/weather/Helsinki")
        assert resp.status_code == 502

    @respx.mock
    def test_city_with_spaces_normalized(self, client):
        """GET /weather/New%20%20York → OWM получает 'New York'."""
        owm_new_york = dict(OWM_HELSINKI)
        owm_new_york["name"] = "New York"
        owm_new_york["sys"] = {"country": "US"}

        route = respx.get("https://api.openweathermap.org/data/2.5/weather").mock(
            return_value=httpx.Response(200, json=owm_new_york)
        )

        resp = client.get("/weather/New  York")
        assert resp.status_code == 200
        # проверяем, что в запрос к OWM ушёл нормализованный city
        assert route.called
        sent_city = route.calls[0].request.url.params["q"]
        assert sent_city == "New York"

    @respx.mock
    def test_cache_hit_skips_owm(self, client):
        """При наличии кэша OWM не должен вызываться."""
        owm_route = respx.get(
            "https://api.openweathermap.org/data/2.5/weather"
        ).mock(return_value=httpx.Response(200, json=OWM_HELSINKI))

        import main as main_module

        cached_payload = json.dumps(OWM_HELSINKI)

        async def fake_get(key):
            if key == "weather:helsinki":
                return cached_payload
            return None

        mock_redis = MagicMock()
        mock_redis.get = fake_get

        original = main_module.redis_client
        main_module.redis_client = mock_redis
        try:
            resp = client.get("/weather/Helsinki")
        finally:
            main_module.redis_client = original

        assert resp.status_code == 200
        assert resp.json()["cached"] is True
        assert not owm_route.called

    @respx.mock
    def test_response_schema_valid(self, client):
        """Ответ соответствует схеме WeatherResponse."""
        respx.get("https://api.openweathermap.org/data/2.5/weather").mock(
            return_value=httpx.Response(200, json=OWM_HELSINKI)
        )

        resp = client.get("/weather/Helsinki")
        assert resp.status_code == 200
        # Pydantic-валидация — не должна падать
        model = WeatherResponse(**resp.json())
        assert model.city == "Helsinki"
