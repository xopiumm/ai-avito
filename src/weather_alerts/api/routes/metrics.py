"""Metrics and observability routes for Weather Alerts.

Exposes application metrics in JSON format for monitoring and alerting.

Endpoints:
  GET /metrics - Current metrics snapshot
  GET /metrics/prometheus - Prometheus-compatible format (future)

Metrics tracked:
  - HTTP requests (count, by method/endpoint)
  - Notification attempts (by channel)
  - Delivery failures (by channel/error type)
  - Deduplication skips
  - API latency (percentiles)
"""

import logging
import threading
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections import defaultdict

from fastapi import APIRouter, status as http_status
from pydantic import BaseModel

from src.weather_alerts.config.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["system"])


# ============================================================================
# METRICS MODEL
# ============================================================================


@dataclass
class CounterMetric:
    """Simple counter metric."""
    value: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)
    
    def increment(self, amount: int = 1) -> None:
        """Atomically increment counter."""
        with self.lock:
            self.value += amount
    
    def get(self) -> int:
        """Get current value."""
        with self.lock:
            return self.value


@dataclass
class HistogramMetric:
    """Histogram metric with percentiles and latency tracking."""
    values: List[float] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)
    max_samples: int = 1000  # Keep last N samples for percentile calculation
    
    def add(self, value: float) -> None:
        """Add a sample value."""
        with self.lock:
            self.values.append(value)
            # Keep only recent samples to avoid memory bloat
            if len(self.values) > self.max_samples:
                self.values = self.values[-self.max_samples:]
    
    def get_percentiles(self) -> Dict[str, float]:
        """Get percentile distribution."""
        with self.lock:
            if not self.values:
                return {}
            
            sorted_values = sorted(self.values)
            n = len(sorted_values)
            
            return {
                "min": sorted_values[0],
                "max": sorted_values[-1],
                "mean": sum(sorted_values) / n,
                "p50": sorted_values[int(n * 0.5)],
                "p95": sorted_values[int(n * 0.95)],
                "p99": sorted_values[int(n * 0.99)],
                "count": n,
            }


@dataclass
class GaugeMetric:
    """Gauge metric - can go up or down."""
    value: float = 0
    lock: threading.Lock = field(default_factory=threading.Lock)
    
    def set(self, value: float) -> None:
        """Set gauge value."""
        with self.lock:
            self.value = value
    
    def get(self) -> float:
        """Get current value."""
        with self.lock:
            return self.value


# ============================================================================
# METRICS REGISTRY
# ============================================================================


class MetricsRegistry:
    """Central registry for all application metrics."""
    
    def __init__(self):
        self.lock = threading.Lock()
        
        # HTTP Metrics
        self.http_requests_total = CounterMetric()
        self.http_requests_by_method = defaultdict(CounterMetric)
        self.http_requests_by_endpoint = defaultdict(CounterMetric)
        self.http_latency_ms = HistogramMetric()
        self.http_errors_total = CounterMetric()
        
        # Notification Metrics
        self.notification_attempts_total = CounterMetric()
        self.notification_attempts_by_channel = defaultdict(CounterMetric)
        
        # Delivery Metrics
        self.delivery_failures_total = CounterMetric()
        self.delivery_failures_by_channel = defaultdict(CounterMetric)
        self.delivery_failures_by_error = defaultdict(CounterMetric)
        
        # Deduplication Metrics
        self.dedup_skips_total = CounterMetric()
        self.dedup_skips_by_channel = defaultdict(CounterMetric)
        
        # Pending Notifications
        self.pending_notifications_total = GaugeMetric()
    
    def record_http_request(
        self,
        method: str,
        endpoint: str,
        latency_ms: float,
        status_code: int,
    ) -> None:
        """Record HTTP request metrics."""
        self.http_requests_total.increment()
        self.http_requests_by_method[method].increment()
        self.http_requests_by_endpoint[endpoint].increment()
        self.http_latency_ms.add(latency_ms)
        
        if status_code >= 400:
            self.http_errors_total.increment()
    
    def record_notification_attempt(self, channel: str) -> None:
        """Record notification delivery attempt."""
        self.notification_attempts_total.increment()
        self.notification_attempts_by_channel[channel].increment()
    
    def record_delivery_failure(
        self,
        channel: str,
        error_type: str,
    ) -> None:
        """Record delivery failure."""
        self.delivery_failures_total.increment()
        self.delivery_failures_by_channel[channel].increment()
        self.delivery_failures_by_error[error_type].increment()
    
    def record_dedup_skip(self, channel: str) -> None:
        """Record deduplication skip."""
        self.dedup_skips_total.increment()
        self.dedup_skips_by_channel[channel].increment()
    
    def get_metrics_dict(self) -> Dict[str, Any]:
        """Get all metrics as dictionary."""
        return {
            "http": {
                "requests_total": self.http_requests_total.get(),
                "requests_by_method": {
                    k: v.get() for k, v in self.http_requests_by_method.items()
                },
                "requests_by_endpoint": {
                    k: v.get() for k, v in self.http_requests_by_endpoint.items()
                },
                "latency_ms": self.http_latency_ms.get_percentiles(),
                "errors_total": self.http_errors_total.get(),
            },
            "notifications": {
                "attempts_total": self.notification_attempts_total.get(),
                "attempts_by_channel": {
                    k: v.get() for k, v in self.notification_attempts_by_channel.items()
                },
            },
            "delivery": {
                "failures_total": self.delivery_failures_total.get(),
                "failures_by_channel": {
                    k: v.get() for k, v in self.delivery_failures_by_channel.items()
                },
                "failures_by_error": {
                    k: v.get() for k, v in self.delivery_failures_by_error.items()
                },
            },
            "deduplication": {
                "skips_total": self.dedup_skips_total.get(),
                "skips_by_channel": {
                    k: v.get() for k, v in self.dedup_skips_by_channel.items()
                },
            },
            "pending": {
                "notifications_total": self.pending_notifications_total.get(),
            },
        }


# ============================================================================
# GLOBAL METRICS INSTANCE
# ============================================================================

metrics = MetricsRegistry()


def get_metrics() -> MetricsRegistry:
    """Get the global metrics registry instance."""
    return metrics


# ============================================================================
# RESPONSE MODELS
# ============================================================================


class MetricsResponse(BaseModel):
    """Metrics response structure."""
    timestamp: str
    metrics: Dict[str, Any]


# ============================================================================
# ENDPOINTS
# ============================================================================


@router.get(
    "/metrics",
    tags=["metrics"],
    summary="Application metrics snapshot",
)
async def get_metrics_endpoint() -> MetricsResponse:
    """Get current application metrics in JSON format.
    
    Returns comprehensive metrics about:
    - HTTP request volume, latency, and error rates
    - Notification delivery attempts and failures
    - Deduplication effectiveness
    - Pending notifications
    
    Used for monitoring dashboards and alerting.
    Can be parsed by monitoring systems (Grafana, DataDog, etc.)
    
    Returns:
        MetricsResponse with current metrics snapshot
        
    Example response:
        {
            "timestamp": "2026-04-09T10:30:45.123Z",
            "metrics": {
                "http": {
                    "requests_total": 1250,
                    "requests_by_method": {"POST": 500, "GET": 750},
                    "latency_ms": {
                        "min": 5.2,
                        "max": 2150.3,
                        "mean": 45.3,
                        "p95": 120.5,
                        "p99": 450.2,
                        "count": 1250
                    }
                },
                "notifications": {
                    "attempts_total": 450,
                    "attempts_by_channel": {"email": 200, "push": 150, "webhook": 100}
                },
                "delivery": {
                    "failures_total": 15,
                    "failures_by_channel": {"webhook": 12, "email": 3}
                },
                "deduplication": {
                    "skips_total": 89,
                    "skips_by_channel": {"email": 45, "push": 30, "webhook": 14}
                }
            }
        }
    """
    logger.info("Metrics endpoint accessed")
    
    return MetricsResponse(
        timestamp=datetime.now(timezone.utc).isoformat(),
        metrics=metrics.get_metrics_dict(),
    )


@router.get(
    "/metrics/health",
    tags=["metrics"],
    summary="Key health metrics summary",
)
async def get_metrics_health() -> Dict[str, Any]:
    """Get key health metrics for quick monitoring.
    
    Simplified view showing only critical metrics:
    - Total requests and error rate
    - Delivery success/failure rate
    - Dedup effectiveness
    
    Returns:
        Dict with key metrics
    """
    metrics_dict = metrics.get_metrics_dict()
    
    total_requests = metrics_dict["http"]["requests_total"]
    error_count = metrics_dict["http"]["errors_total"]
    error_rate = (error_count / total_requests * 100) if total_requests > 0 else 0
    
    delivery_failures = metrics_dict["delivery"]["failures_total"]
    notification_attempts = metrics_dict["notifications"]["attempts_total"]
    delivery_success_rate = (
        ((notification_attempts - delivery_failures) / notification_attempts * 100)
        if notification_attempts > 0
        else 0
    )
    
    dedup_skips = metrics_dict["deduplication"]["skips_total"]
    dedup_effectiveness = (
        (dedup_skips / (notification_attempts + dedup_skips) * 100)
        if (notification_attempts + dedup_skips) > 0
        else 0
    )
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "http": {
            "requests_total": total_requests,
            "error_rate_percent": round(error_rate, 2),
        },
        "delivery": {
            "attempts": notification_attempts,
            "failures": delivery_failures,
            "success_rate_percent": round(delivery_success_rate, 2),
        },
        "deduplication": {
            "skips_total": dedup_skips,
            "effectiveness_percent": round(dedup_effectiveness, 2),
        },
    }


# ============================================================================
# HELPER FUNCTIONS FOR INTEGRATION
# ============================================================================


def record_request_metrics(
    method: str,
    path: str,
    latency_ms: float,
    status_code: int,
) -> None:
    """Record HTTP request metrics.
    
    Called from middleware or request handlers.
    
    Args:
        method: HTTP method (GET, POST, etc.)
        path: Request path/endpoint
        latency_ms: Request duration in milliseconds
        status_code: HTTP response status code
    """
    metrics.record_http_request(method, path, latency_ms, status_code)


def record_notification_attempt(channel: str) -> None:
    """Record notification delivery attempt.
    
    Args:
        channel: Delivery channel (email, push, webhook)
    """
    metrics.record_notification_attempt(channel)


def record_delivery_failure(channel: str, error_type: str) -> None:
    """Record delivery failure.
    
    Args:
        channel: Delivery channel
        error_type: Type of failure (timeout, invalid_recipient, etc.)
    """
    metrics.record_delivery_failure(channel, error_type)


def record_dedup_skip(channel: str) -> None:
    """Record deduplication skip.
    
    Args:
        channel: Delivery channel (notification was skipped via dedup)
    """
    metrics.record_dedup_skip(channel)


def set_pending_notifications_count(count: int) -> None:
    """Set gauge for pending notifications.
    
    Args:
        count: Current number of pending notifications
    """
    metrics.pending_notifications_total.set(float(count))
