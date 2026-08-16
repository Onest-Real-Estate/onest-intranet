"""Celery application — background tasks and the django-celery-beat scheduler.

The broker and result backend come from Django settings (``CELERY_BROKER_URL``
/ ``CELERY_RESULT_BACKEND``), which the compose stacks point at Redis (on
dedicated DBs so they never compete with the cache on db 0).
"""

import os

from celery import Celery

# Ensure Django settings are loaded before the app is used.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("onest")

# Load the CELERY_* settings from Django (the namespace strips the prefix:
# CELERY_BROKER_URL -> broker_url, etc.).
app.config_from_object("django.conf:settings", namespace="CELERY")

# Pick up a tasks.py module in every installed app automatically.
app.autodiscover_tasks()
