#!/bin/sh
set -e

# One-shot migration runner. web, celery, and celery-beat no longer run
# migrate themselves; they wait for this service via
# `depends_on: service_completed_successfully`. Concurrent migrates race on
# unapplied migrations and crash the losers with DuplicateColumn.
#
# Re-sync deps on start (the dev venv volume may start empty; a fast no-op
# in the prod image where deps are baked in).
uv sync --frozen

uv run python manage.py migrate --noinput
