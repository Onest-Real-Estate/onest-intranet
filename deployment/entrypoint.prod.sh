#!/bin/sh
set -e

uv run python manage.py migrate --noinput
uv run python manage.py collectstatic --noinput
uv run python manage.py generate_typescript_routes --urlconf config.urls > frontend/types/routes.ts

exec uv run gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --threads "${GUNICORN_THREADS:-2}"
