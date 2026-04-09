"""Background tasks and async job processing (Celery workers).

Exports:
    app: Global Celery application instance for task distribution.
         Use this to:
         - Send tasks: app.send_task('queue_name', args=(arg1, arg2))
         - Check results: result.get()
         - Monitor workers: celery -u celery inspect active

    Delivery task helpers (T024):
    - DeliveryTaskPayload: Structured payload for delivery tasks
    - ExponentialBackoffStrategy: Retry backoff calculation
    - send_email_with_retry: Email delivery with exponential backoff
    - send_push_with_retry: Push delivery with exponential backoff
    - send_webhook_with_retry: Webhook delivery with exponential backoff
    - submit_delivery_task: Helper to submit tasks to delivery queues
"""

from src.weather_alerts.workers.celery_app import app
from src.weather_alerts.workers.delivery_tasks import (
    DeliveryTaskPayload,
    ExponentialBackoffStrategy,
    send_email_with_retry,
    send_push_with_retry,
    send_webhook_with_retry,
    submit_delivery_task,
)

__all__ = [
    "app",
    "DeliveryTaskPayload",
    "ExponentialBackoffStrategy",
    "send_email_with_retry",
    "send_push_with_retry",
    "send_webhook_with_retry",
    "submit_delivery_task",
]
