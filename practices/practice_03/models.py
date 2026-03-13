import re

from pydantic import BaseModel, field_validator


class WeatherResponse(BaseModel):
    city: str
    country: str
    temperature_celsius: float
    feels_like_celsius: float
    humidity_percent: int
    description: str
    wind_speed_mps: float
    cached: bool = False


class ErrorResponse(BaseModel):
    error: str
    detail: str


class SubscriptionRequest(BaseModel):
    """Тело запроса для POST /subscribe."""

    email: str
    city: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Проверяет формат email-адреса."""
        v = v.strip()
        pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
        if not re.match(pattern, v):
            raise ValueError(f"Invalid email format: {v!r}")
        return v

    @field_validator("city")
    @classmethod
    def validate_city(cls, v: str) -> str:
        """Запрещает пустое название города."""
        v = v.strip()
        if not v:
            raise ValueError("City name cannot be empty")
        return v


class SubscriptionResponse(BaseModel):
    """Ответ на успешную подписку, включает текущую погоду."""

    email: str
    city: str
    country: str
    temperature_celsius: float
    feels_like_celsius: float
    humidity_percent: int
    description: str
    wind_speed_mps: float
    message: str
