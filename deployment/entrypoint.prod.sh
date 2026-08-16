#!/bin/sh
set -e

uv run python manage.py migrate --noinput
uv run python manage.py collectstatic --noinput

exec uv run gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --threads "${GUNICORN_THREADS:-2}"
