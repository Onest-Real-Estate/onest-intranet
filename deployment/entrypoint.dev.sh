#!/bin/sh
set -e

# Re-sync deps on start (the venv volume may start empty, and the host's
# pyproject/uv.lock are bind-mounted).
uv sync --frozen

uv run python manage.py migrate --noinput

exec uv run python manage.py runserver 0.0.0.0:8000
