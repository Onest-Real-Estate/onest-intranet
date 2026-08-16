# Makes the Celery app import automatically when Django starts, so the
# worker/beat commands and @shared_task decorators can find it.
from .celery import app as celery_app

__all__ = ("celery_app",)
