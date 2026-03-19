"""
Тесты для POST /subscribe.

Покрытие:
  Unit:
    - SubscriptionRequest: валидный email и город
    - SubscriptionRequest: невалидный email → ValidationError
    - SubscriptionRequest: пустой город → ValidationError
  Integration (respx mock, Redis=None):
    - 201 happy path: создаётся подписка, возвращается погода
    - 409 дублирующая подписка (тот же email+city)
    - 404 несуществующий город (OWM возвращает 404)
    - 422 невалидный email (Pydantic отклоняет тело запроса)
    - 503 OWM_API_KEY не задан
    - 502 сетевая ошибка OWM
    - Нормализация города в запросе к OWM
"""

from unittest.mock import patch

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from pydantic import ValidationError

import main as main_module
from main import app
from models import SubscriptionRequest, SubscriptionResponse

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


@pytest.fixture(autouse=True)
def clear_subscriptions():
    """Сбрасывает in-memory хранилища перед каждым тестом."""
    main_module._subscriptions.clear()
    main_module._subscription_ids.clear()
    yield
    main_module._subscriptions.clear()
    main_module._subscription_ids.clear()


@pytest.fixture()
def client(monkeypatch):
    """TestClient с заглушкой Redis и заданным OWM_API_KEY."""
    monkeypatch.setenv("OWM_API_KEY", OWM_KEY)
    main_module.redis_client = None

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ══════════════════════════════════════════════════════════════════════════════
# Unit-тесты — валидация SubscriptionRequest
# ══════════════════════════════════════════════════════════════════════════════

class TestSubscriptionRequestModel:
    def test_valid_payload(self):
        req = SubscriptionRequest(email="user@example.com", city="Helsinki")
        assert req.email == "user@example.com"
        assert req.city == "Helsinki"

    def test_email_stripped(self):
        req = SubscriptionRequest(email="  user@example.com  ", city="Oslo")
        assert req.email == "user@example.com"

    def test_city_stripped(self):
        req = SubscriptionRequest(email="a@b.cc", city="  Oslo  ")
        assert req.city == "Oslo"

    def test_invalid_email_raises(self):
        with pytest.raises(ValidationError):
            SubscriptionRequest(email="not-an-email", city="Helsinki")

    def test_empty_email_raises(self):
        with pytest.raises(ValidationError):
            SubscriptionRequest(email="", city="Helsinki")

    def test_empty_city_raises(self):
        with pytest.raises(ValidationError):
            SubscriptionRequest(email="user@example.com", city="   ")

    def test_email_no_domain_raises(self):
        with pytest.raises(ValidationError):
            SubscriptionRequest(email="user@", city="Helsinki")


# ══════════════════════════════════════════════════════════════════════════════
# Integration-тесты
# ══════════════════════════════════════════════════════════════════════════════

class TestPostSubscribe:

    @respx.mock
    def test_happy_path_201(self, client):
        """POST /subscribe с валидными данными → 201 + поля ответа."""
        respx.get("https://api.openweathermap.org/data/2.5/weather").mock(
            return_value=httpx.Response(200, json=OWM_HELSINKI)
        )

        resp = client.post(
            "/subscribe",
            json={"email": "user@example.com", "city": "Helsinki"},
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == "user@example.com"
        assert body["city"] == "Helsinki"
        assert body["country"] == "FI"
        assert body["temperature_celsius"] == 2.5
        assert body["humidity_percent"] == 80
        assert "message" in body
        assert "Helsinki" in body["message"]

    @respx.mock
    def test_happy_path_response_schema(self, client):
        """Ответ соответствует схеме SubscriptionResponse."""
        respx.get("https://api.openweathermap.org/data/2.5/weather").mock(
            return_value=httpx.Response(200, json=OWM_HELSINKI)
        )

        resp = client.post(
            "/subscribe",
            json={"email": "schema@example.com", "city": "Helsinki"},
        )

        assert resp.status_code == 201
        model = SubscriptionResponse(**resp.json())
        assert model.email == "schema@example.com"

    @respx.mock
    def test_duplicate_subscription_409(self, client):
        """Повторная подписка того же email+city → 409."""
        respx.get("https://api.openweathermap.org/data/2.5/weather").mock(
            return_value=httpx.Response(200, json=OWM_HELSINKI)
        )

        client.post("/subscribe", json={"email": "dup@example.com", "city": "Helsinki"})
        resp = client.post(
            "/subscribe",
            json={"email": "dup@example.com", "city": "Helsinki"},
        )

        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]

    @respx.mock
    def test_city_not_found_404(self, client):
        """POST /subscribe с несуществующим городом → 404."""
        respx.get("https://api.openweathermap.org/data/2.5/weather").mock(
            return_value=httpx.Response(404, json={"message": "city not found"})
        )

        resp = client.post(
            "/subscribe",
            json={"email": "user@example.com", "city": "NoSuchCity_99999"},
        )

        assert resp.status_code == 404

    def test_invalid_email_422(self, client):
        """POST /subscribe с неправильным email → 422 (Pydantic)."""
        resp = client.post(
            "/subscribe",
            json={"email": "not-an-email", "city": "Helsinki"},
        )
        assert resp.status_code == 422

    def test_empty_city_422(self, client):
        """POST /subscribe с пустым городом → 422 (Pydantic)."""
        resp = client.post(
            "/subscribe",
            json={"email": "user@example.com", "city": "   "},
        )
        assert resp.status_code == 422

    def test_missing_fields_422(self, client):
        """POST /subscribe без обязательных полей → 422."""
        resp = client.post("/subscribe", json={"email": "user@example.com"})
        assert resp.status_code == 422

    def test_no_api_key_503(self, client):
        """POST /subscribe без OWM_API_KEY → 503."""
        with patch.object(main_module, "OWM_API_KEY", ""):
            resp = client.post(
                "/subscribe",
                json={"email": "user@example.com", "city": "Helsinki"},
            )
        assert resp.status_code == 503

    @respx.mock
    def test_owm_network_error_502(self, client):
        """POST /subscribe при сетевой ошибке OWM → 502."""
        respx.get("https://api.openweathermap.org/data/2.5/weather").mock(
            side_effect=httpx.ConnectError("connection refused")
        )

        resp = client.post(
            "/subscribe",
            json={"email": "user@example.com", "city": "Helsinki"},
        )

        assert resp.status_code == 502

    @respx.mock
    def test_city_normalized_in_owm_request(self, client):
        """Города с лишними пробелами нормализуются перед запросом к OWM."""
        owm_ny = dict(OWM_HELSINKI)
        owm_ny["name"] = "New York"
        owm_ny["sys"] = {"country": "US"}

        route = respx.get("https://api.openweathermap.org/data/2.5/weather").mock(
            return_value=httpx.Response(200, json=owm_ny)
        )

        resp = client.post(
            "/subscribe",
            json={"email": "user@example.com", "city": "New   York"},
        )

        assert resp.status_code == 201
        assert route.called
        sent_city = route.calls[0].request.url.params["q"]
        assert sent_city == "New York"

    @respx.mock
    def test_different_cities_same_email_allowed(self, client):
        """Один email может подписаться на разные города."""
        respx.get("https://api.openweathermap.org/data/2.5/weather").mock(
            return_value=httpx.Response(200, json=OWM_HELSINKI)
        )

        resp1 = client.post(
            "/subscribe",
            json={"email": "multi@example.com", "city": "Helsinki"},
        )
        resp2 = client.post(
            "/subscribe",
            json={"email": "multi@example.com", "city": "Oslo"},
        )

        assert resp1.status_code == 201
        assert resp2.status_code == 201

    @respx.mock
    def test_same_city_different_emails_allowed(self, client):
        """Разные email могут подписаться на один город."""
        respx.get("https://api.openweathermap.org/data/2.5/weather").mock(
            return_value=httpx.Response(200, json=OWM_HELSINKI)
        )

        resp1 = client.post(
            "/subscribe",
            json={"email": "first@example.com", "city": "Helsinki"},
        )
        resp2 = client.post(
            "/subscribe",
            json={"email": "second@example.com", "city": "Helsinki"},
        )

        assert resp1.status_code == 201
        assert resp2.status_code == 201

    @respx.mock
    def test_subscription_stored_in_memory(self, client):
        """После успешной подписки запись появляется в _subscriptions."""
        respx.get("https://api.openweathermap.org/data/2.5/weather").mock(
            return_value=httpx.Response(200, json=OWM_HELSINKI)
        )

        client.post(
            "/subscribe",
            json={"email": "store@example.com", "city": "Helsinki"},
        )

        assert "store@example.com:helsinki" in main_module._subscriptions


class TestGetSubscriptions:

    def test_get_subscriptions_empty_list(self, client):
        """GET /subscriptions без данных возвращает пустой список."""
        resp = client.get("/subscriptions")

        assert resp.status_code == 200
        assert resp.json() == []

    @respx.mock
    def test_get_subscriptions_returns_created_items(self, client):
        """GET /subscriptions возвращает созданные подписки."""
        respx.get("https://api.openweathermap.org/data/2.5/weather").mock(
            return_value=httpx.Response(200, json=OWM_HELSINKI)
        )

        create_resp = client.post(
            "/subscribe",
            json={"email": "list@example.com", "city": "Helsinki"},
        )
        subscription_id = create_resp.json()["subscription_id"]

        resp = client.get("/subscriptions")

        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0] == {
            "subscription_id": subscription_id,
            "email": "list@example.com",
            "city": "Helsinki",
            "notification_time": "morning",
            "status": "pending",
        }

    @respx.mock
    def test_get_subscriptions_filter_by_email(self, client):
        """GET /subscriptions?email=... фильтрует по email."""
        respx.get("https://api.openweathermap.org/data/2.5/weather").mock(
            return_value=httpx.Response(200, json=OWM_HELSINKI)
        )

        client.post(
            "/subscribe",
            json={"email": "first@example.com", "city": "Helsinki"},
        )
        client.post(
            "/subscribe",
            json={"email": "second@example.com", "city": "Oslo"},
        )

        resp = client.get("/subscriptions", params={"email": "second@example.com"})

        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["email"] == "second@example.com"

    @respx.mock
    def test_get_subscriptions_filter_by_city_normalized(self, client):
        """Фильтр city учитывает нормализацию пробелов и регистр."""
        respx.get("https://api.openweathermap.org/data/2.5/weather").mock(
            return_value=httpx.Response(200, json=OWM_HELSINKI)
        )

        client.post(
            "/subscribe",
            json={"email": "city@example.com", "city": "New   York"},
        )

        resp = client.get("/subscriptions", params={"city": "  new york  "})

        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["city"] == "New York"


# ══════════════════════════════════════════════════════════════════════════════
# Тесты DELETE /subscribe/{id}
# ══════════════════════════════════════════════════════════════════════════════

class TestDeleteSubscribe:

    @respx.mock
    def test_delete_existing_subscription_200(self, client):
        """DELETE /subscribe/{id} с существующим ID → 200 + message."""
        respx.get("https://api.openweathermap.org/data/2.5/weather").mock(
            return_value=httpx.Response(200, json=OWM_HELSINKI)
        )

        post_resp = client.post(
            "/subscribe",
            json={"email": "del@example.com", "city": "Helsinki"},
        )
        assert post_resp.status_code == 201
        sub_id = post_resp.json()["subscription_id"]

        delete_resp = client.delete(f"/subscribe/{sub_id}")

        assert delete_resp.status_code == 200
        body = delete_resp.json()
        assert "message" in body
        assert "del@example.com" in body["message"]

    def test_delete_nonexistent_id_404(self, client):
        """DELETE /subscribe/{id} с несуществующим ID → 404."""
        resp = client.delete("/subscribe/00000000-0000-0000-0000-000000000000")

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @respx.mock
    def test_delete_removes_from_store(self, client):
        """После DELETE подписка удаляется из in-memory хранилища."""
        respx.get("https://api.openweathermap.org/data/2.5/weather").mock(
            return_value=httpx.Response(200, json=OWM_HELSINKI)
        )

        post_resp = client.post(
            "/subscribe",
            json={"email": "gone@example.com", "city": "Helsinki"},
        )
        sub_id = post_resp.json()["subscription_id"]

        client.delete(f"/subscribe/{sub_id}")

        assert "gone@example.com:helsinki" not in main_module._subscriptions
        assert sub_id not in main_module._subscription_ids

    @respx.mock
    def test_delete_twice_second_is_404(self, client):
        """Повторный DELETE того же ID → 404."""
        respx.get("https://api.openweathermap.org/data/2.5/weather").mock(
            return_value=httpx.Response(200, json=OWM_HELSINKI)
        )

        post_resp = client.post(
            "/subscribe",
            json={"email": "twice@example.com", "city": "Helsinki"},
        )
        sub_id = post_resp.json()["subscription_id"]

        client.delete(f"/subscribe/{sub_id}")
        resp = client.delete(f"/subscribe/{sub_id}")

        assert resp.status_code == 404

    @respx.mock
    def test_delete_then_resubscribe_allowed(self, client):
        """После DELETE можно снова подписаться на тот же email+city → 201."""
        respx.get("https://api.openweathermap.org/data/2.5/weather").mock(
            return_value=httpx.Response(200, json=OWM_HELSINKI)
        )

        post_resp = client.post(
            "/subscribe",
            json={"email": "resub@example.com", "city": "Helsinki"},
        )
        sub_id = post_resp.json()["subscription_id"]
        client.delete(f"/subscribe/{sub_id}")

        resp2 = client.post(
            "/subscribe",
            json={"email": "resub@example.com", "city": "Helsinki"},
        )

        assert resp2.status_code == 201

    @respx.mock
    def test_post_returns_subscription_id(self, client):
        """POST /subscribe возвращает поле subscription_id."""
        respx.get("https://api.openweathermap.org/data/2.5/weather").mock(
            return_value=httpx.Response(200, json=OWM_HELSINKI)
        )

        resp = client.post(
            "/subscribe",
            json={"email": "idcheck@example.com", "city": "Helsinki"},
        )

        assert resp.status_code == 201
        body = resp.json()
        assert "subscription_id" in body
        assert body["subscription_id"]  # непустое значение
