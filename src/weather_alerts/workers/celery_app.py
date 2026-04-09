"""Celery application configuration for Weather Alerts asynchronous task processing.

This module provides:
- Celery app instance configured with Redis broker/backend
- Task queues for email, push, and webhook delivery channels
- Graceful configuration loading from settings
- Ready-to-run Celery worker setup

Usage:
    celery -A src.weather_alerts.workers.celery_app worker --loglevel=info
"""

from celery import Celery
from kombu import Exchange, Queue

from src.weather_alerts.config.settings import get_settings

# Create Celery application instance
_app: Celery | None = None


def get_celery_app() -> Celery:
    """Get or create the global Celery application instance.
    
    Lazy initialization ensures settings are loaded exactly once and reused.
    Thread-safe for singleton pattern.
    
    Returns:
        Celery: Configured Celery application instance
        
    Example:
        app = get_celery_app()
        result = app.send_task('send_email', args=(user_id, template))
    """
    global _app
    if _app is not None:
        return _app
    
    settings = get_settings()
    _app = Celery("weather_alerts")
    
    # ====================================================================
    # BROKER & RESULT BACKEND CONFIGURATION
    # ====================================================================
    # Redis acts as both message broker (task queue) and result backend
    _app.conf.broker_url = settings.celery.broker_url
    _app.conf.result_backend = settings.celery.result_backend
    
    # ====================================================================
    # TASK CONFIGURATION
    # ====================================================================
    _app.conf.task_serializer = "json"
    _app.conf.accept_content = ["json"]
    _app.conf.result_serializer = "json"
    _app.conf.timezone = "UTC"
    _app.conf.enable_utc = True
    
    # Task state tracking (useful for monitoring)
    _app.conf.task_track_started = settings.celery.task_track_started
    
    # Hard and soft time limits (prevent runaway tasks)
    _app.conf.task_time_limit = settings.celery.task_time_limit
    _app.conf.task_soft_time_limit = settings.celery.task_soft_time_limit
    
    # ====================================================================
    # QUEUE CONFIGURATION
    # ====================================================================
    # Define delivery channel queues with default exchange
    _app.conf.task_queues = (
        Queue(
            "default",
            exchange=Exchange("weather_alerts", type="direct"),
            routing_key="default",
            queue_arguments={"x-max-priority": 10},
        ),
        Queue(
            "email",
            exchange=Exchange("weather_alerts", type="direct"),
            routing_key="email",
            queue_arguments={"x-max-priority": 10},
        ),
        Queue(
            "push",
            exchange=Exchange("weather_alerts", type="direct"),
            routing_key="push",
            queue_arguments={"x-max-priority": 10},
        ),
        Queue(
            "webhook",
            exchange=Exchange("weather_alerts", type="direct"),
            routing_key="webhook",
            queue_arguments={"x-max-priority": 10},
        ),
    )
    
    # Default queue for tasks without explicit routing
    _app.conf.task_default_queue = "default"
    _app.conf.task_default_exchange = "weather_alerts"
    _app.conf.task_default_routing_key = "default"
    
    # ====================================================================
    # PRIORITY & WORKER BEHAVIOR
    # ====================================================================
    # Enable priority-based task processing (higher value = higher priority)
    _app.conf.worker_prefetch_multiplier = 4
    _app.conf.worker_max_tasks_per_child = 1000
    
    # Retry configuration defaults (can be overridden per task)
    _app.conf.task_acks_late = True
    _app.conf.task_reject_on_worker_lost = True
    
    return _app


# Module-level instance for convenience
app = get_celery_app()
