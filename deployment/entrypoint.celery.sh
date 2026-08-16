#!/bin/sh
set -e

# Re-sync deps on start (the dev venv volume may start empty; a fast no-op in
# the prod image where deps are baked in).
uv sync --frozen

# django-celery-beat needs its tables (idempotent; web also runs migrate).
uv run python manage.py migrate --noinput

# Args are the celery subcommand + flags, e.g. "worker -l info" or "beat -l info".
exec uv run celery -A config "$@"
