#!/bin/sh
set -e

# Re-sync deps on start (the venv volume may start empty, and the host's
# pyproject/uv.lock are bind-mounted).
uv sync --frozen

# Migrations are applied by the one-shot `migrate` service; this container
# starts only after it completes (depends_on: service_completed_successfully).

exec uv run python manage.py runserver 0.0.0.0:8000
