import json
import logging
import os
import re
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

import httpx
import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException

from models import (
    ErrorResponse,
    SubscriptionListItem,
    SubscriptionRequest,
    SubscriptionResponse,
    WeatherResponse,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── конфигурация ──────────────────────────────────────────────────────────────
OWM_API_KEY = os.getenv("OWM_API_KEY", "")
OWM_BASE_URL = "https://api.openweathermap.org/data/2.5/weather"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
CACHE_TTL = 600  # секунд

# ── Redis-клиент (опциональный: если недоступен — работаем без кэша) ──────────
redis_client: Optional[aioredis.Redis] = None

# ── In-memory хранилище подписок (ключ: "email:city") ────────────────────────
# В production следует заменить на PostgreSQL.
_subscriptions: dict[str, dict] = {}
# Обратный индекс: subscription_id → ключ в _subscriptions
_subscription_ids: dict[str, str] = {}


@asynccontextmanager
async def lifespan(application: FastAPI):
    global redis_client
    try:
        redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
        await redis_client.ping()
        logger.info("Redis доступен: %s", REDIS_URL)
    except Exception as exc:
        logger.warning("Redis недоступен (%s), кэширование отключено", exc)
        redis_client = None

    yield

    if redis_client:
        await redis_client.aclose()


app = FastAPI(
    title="WeatherService API",
    description="REST API для получения данных о погоде и управления подписками",
    version="1.0.0",
    lifespan=lifespan,
)


# ── вспомогательные функции ────────────────────────────────────────────────────

def normalize_city(city: str) -> str:
    """Убирает лишние пробелы, схлопывает внутренние."""
    city = city.strip()
    city = re.sub(r"\s+", " ", city)
    return city


async def get_cached_weather(city_key: str) -> Optional[dict]:
    if redis_client is None:
        return None
    try:
        raw = await redis_client.get(f"weather:{city_key}")
        if raw:
            logger.info("Cache HIT: %s", city_key)
            return json.loads(raw)
    except Exception as exc:
        logger.warning("Redis get error: %s", exc)
    return None


async def set_cached_weather(city_key: str, data: dict) -> None:
    if redis_client is None:
        return
    try:
        await redis_client.setex(f"weather:{city_key}", CACHE_TTL, json.dumps(data))
        logger.info("Cache SET: %s (TTL=%ds)", city_key, CACHE_TTL)
    except Exception as exc:
        logger.warning("Redis set error: %s", exc)


async def fetch_weather_from_owm(city: str) -> dict:
    """Запрашивает погоду у OpenWeatherMap. Выбрасывает HTTPException при ошибках."""
    if not OWM_API_KEY:
        raise HTTPException(status_code=503, detail="OWM_API_KEY not configured")

    params = {
        "q": city,
        "appid": OWM_API_KEY,
        "units": "metric",
        "lang": "ru",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(OWM_BASE_URL, params=params)
        except httpx.RequestError as exc:
            logger.error("OWM request error: %s", exc)
            raise HTTPException(status_code=502, detail="Weather provider unreachable")

    if response.status_code == 404:
        raise HTTPException(status_code=404, detail=f"City '{city}' not found")
    if response.status_code == 401:
        raise HTTPException(status_code=503, detail="Invalid OWM API key")
    if response.status_code != 200:
        logger.error("OWM unexpected status %d: %s", response.status_code, response.text)
        raise HTTPException(status_code=502, detail="Unexpected error from weather provider")

    return response.json()


def parse_owm_response(raw: dict, cached: bool = False) -> WeatherResponse:
    return WeatherResponse(
        city=raw["name"],
        country=raw["sys"]["country"],
        temperature_celsius=raw["main"]["temp"],
        feels_like_celsius=raw["main"]["feels_like"],
        humidity_percent=raw["main"]["humidity"],
        description=raw["weather"][0]["description"],
        wind_speed_mps=raw["wind"]["speed"],
        cached=cached,
    )


# ── эндпоинты ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get(
    "/weather/{city}",
    response_model=WeatherResponse,
    responses={
        200: {"description": "Данные о погоде"},
        400: {"model": ErrorResponse, "description": "Некорректное название города"},
        404: {"model": ErrorResponse, "description": "Город не найден"},
        502: {"model": ErrorResponse, "description": "Ошибка внешнего провайдера"},
        503: {"model": ErrorResponse, "description": "Сервис недоступен"},
    },
    summary="Получить текущую погоду по названию города",
)
async def get_weather(city: str) -> WeatherResponse:
    """
    Возвращает текущую погоду для указанного города.

    - Нормализует название (trim + collapse spaces).
    - Проверяет кэш Redis (TTL=600 s).
    - При cache miss запрашивает OpenWeatherMap и кэширует результат.
    """
    city_normalized = normalize_city(city)

    if not city_normalized:
        raise HTTPException(status_code=400, detail="City name cannot be empty")

    cache_key = city_normalized.lower()

    cached_data = await get_cached_weather(cache_key)
    if cached_data:
        return parse_owm_response(cached_data, cached=True)

    raw = await fetch_weather_from_owm(city_normalized)
    await set_cached_weather(cache_key, raw)

    logger.info("Weather fetched from OWM for city='%s'", city_normalized)
    return parse_owm_response(raw, cached=False)


@app.post(
    "/subscribe",
    response_model=SubscriptionResponse,
    status_code=201,
    responses={
        201: {"description": "Подписка успешно создана"},
        400: {"model": ErrorResponse, "description": "Некорректные данные (невалидный email / пустой город / город не найден)"},
        409: {"model": ErrorResponse, "description": "Подписка уже существует"},
        502: {"model": ErrorResponse, "description": "Ошибка внешнего провайдера"},
        503: {"model": ErrorResponse, "description": "Сервис недоступен"},
    },
    summary="Подписаться на утреннюю сводку погоды",
)
async def subscribe(body: SubscriptionRequest) -> SubscriptionResponse:
    """
    Создаёт подписку на ежедневную утреннюю сводку погоды.

    - Валидирует email и название города (Pydantic).
    - Нормализует город и проверяет его существование через OWM.
    - Возвращает 409, если подписка email+city уже существует.
    - Сохраняет подписку в памяти и возвращает текущую погоду.
    """
    city_normalized = normalize_city(body.city)
    email = body.email

    if not city_normalized:
        raise HTTPException(status_code=400, detail="City name cannot be empty")

    subscription_key = f"{email}:{city_normalized.lower()}"
    if subscription_key in _subscriptions:
        raise HTTPException(
            status_code=409,
            detail=f"Subscription for '{email}' and city '{city_normalized}' already exists",
        )

    # Проверяем существование города и получаем погоду
    raw = await fetch_weather_from_owm(city_normalized)

    sub_id = str(uuid.uuid4())
    _subscriptions[subscription_key] = {
        "email": email,
        "city": city_normalized,
        "id": sub_id,
        "notification_time": "morning",
        "status": "pending",
    }
    _subscription_ids[sub_id] = subscription_key
    logger.info(
        "New subscription: id='%s', email='%s', city='%s'",
        sub_id, email, city_normalized,
    )

    weather = parse_owm_response(raw)
    return SubscriptionResponse(
        subscription_id=sub_id,
        email=email,
        city=weather.city,
        country=weather.country,
        temperature_celsius=weather.temperature_celsius,
        feels_like_celsius=weather.feels_like_celsius,
        humidity_percent=weather.humidity_percent,
        description=weather.description,
        wind_speed_mps=weather.wind_speed_mps,
        message=f"Subscribed successfully. You will receive daily weather updates for {weather.city}.",
    )


@app.get(
    "/subscriptions",
    response_model=list[SubscriptionListItem],
    responses={
        200: {"description": "Список подписок"},
    },
    summary="Получить список подписок",
)
async def get_subscriptions(
    email: Optional[str] = None,
    city: Optional[str] = None,
    status: Optional[str] = None,
) -> list[SubscriptionListItem]:
    """Возвращает список подписок с опциональной фильтрацией."""
    city_normalized = normalize_city(city).lower() if city is not None else None

    rows = []
    for sub in _subscriptions.values():
        sub_email = sub["email"]
        sub_city = sub["city"]
        sub_status = sub.get("status", "pending")

        if email is not None and sub_email != email:
            continue
        if city_normalized is not None and sub_city.lower() != city_normalized:
            continue
        if status is not None and sub_status != status:
            continue

        rows.append(
            SubscriptionListItem(
                subscription_id=sub["id"],
                email=sub_email,
                city=sub_city,
                notification_time=sub.get("notification_time", "morning"),
                status=sub_status,
            )
        )

    rows.sort(key=lambda item: (item.email, item.city, item.subscription_id))
    return rows


@app.delete(
    "/subscribe/{subscription_id}",
    status_code=200,
    responses={
        200: {"description": "Подписка успешно удалена"},
        404: {"model": ErrorResponse, "description": "Подписка не найдена"},
    },
    summary="Удалить подписку по ID",
)
async def delete_subscription(subscription_id: str) -> dict:
    """
    Удаляет подписку по уникальному идентификатору.

    - Возвращает 404, если подписка с указанным ID не существует.
    - Возвращает 200 с сообщением при успешном удалении.
    """
    subscription_key = _subscription_ids.get(subscription_id)
    if subscription_key is None:
        raise HTTPException(
            status_code=404,
            detail=f"Subscription '{subscription_id}' not found",
        )

    subscription = _subscriptions.pop(subscription_key)
    del _subscription_ids[subscription_id]
    logger.info(
        "Subscription deleted: id='%s', email='%s', city='%s'",
        subscription_id,
        subscription["email"],
        subscription["city"],
    )

    return {
        "message": (
            f"Subscription for '{subscription['email']}' and city"
            f" '{subscription['city']}' has been deleted."
        )
    }
