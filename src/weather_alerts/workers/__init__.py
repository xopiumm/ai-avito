"""Background tasks and async job processing (Celery workers).

Exports:
    app: Global Celery application instance for task distribution.
         Use this to:
         - Send tasks: app.send_task('queue_name', args=(arg1, arg2))
         - Check results: result.get()
         - Monitor workers: celery -u celery inspect active
"""

from src.weather_alerts.workers.celery_app import app

__all__ = ["app"]
