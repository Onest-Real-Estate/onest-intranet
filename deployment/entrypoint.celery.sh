#!/bin/sh
set -e

# Re-sync deps on start (the dev venv volume may start empty; a fast no-op in
# the prod image where deps are baked in).
uv sync --frozen

# django-celery-beat's tables are created by the one-shot `migrate` service;
# this container starts only after it completes
# (depends_on: service_completed_successfully).

# Args are the celery subcommand + flags, e.g. "worker -l info" or "beat -l info".
exec uv run celery -A config "$@"
