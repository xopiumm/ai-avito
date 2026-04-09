"""Location domain model for weather alerts."""

from sqlalchemy import Column, Integer, String, Float
from sqlalchemy.orm import relationship

from src.weather_alerts.config.database import Base


class Location(Base):
    """Location entity for storing location information.
    
    Stores geographic locations that subscriptions are associated with.
    
    Attributes:
        id: Unique location identifier
        name: Human-readable location name (e.g., "Moscow", "San Francisco")
        latitude: Geographic latitude coordinate
        longitude: Geographic longitude coordinate
        timezone: IANA timezone identifier (e.g., "Europe/Moscow", "America/Los_Angeles")
    
    Relations:
        subscriptions: Subscriptions for this location (one-to-many)
    """
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    timezone = Column(String(50), nullable=False, default="UTC")

    # Relationships
    subscriptions = relationship("Subscription", back_populates="location", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Location(id={self.id}, name='{self.name}', timezone='{self.timezone}')>"
