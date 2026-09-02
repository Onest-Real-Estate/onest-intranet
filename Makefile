# oNEST HUB developer shortcuts.
#
# Docker stack (Postgres, Redis, Mailpit, MinIO, Celery):
#   make up                        start the dev stack
#   make dockerexec cmd="…"        run any command in the web container
#   make manage cmd="…"            Django management command in the container
#
# Local toolchain (fast edits; SQLite unless DATABASE_URL points elsewhere):
#   make runserver                 Django on :8000
#   make dev                       Vite on :5173 (separate terminal)
#   make test                      pytest with project addopts (-n auto --reuse-db)
#   make checks                    pre-commit gate (lint, types, migration drift)
#
# See docs/dockerexec.md for the full Docker workflow.

COMPOSE := docker compose --env-file .env -f deployment/compose.dev.yaml
WEB     := web
DOCKEREXEC   := $(COMPOSE) exec $(WEB)
DOCKEREXEC_T := $(COMPOSE) exec -T $(WEB)
MANAGE  := $(DOCKEREXEC) uv run python manage.py

.DEFAULT_GOAL := help

.PHONY: help up down clean dockerexec manage migrate makemigrations superuser shell \
	test test-fresh test-docker checks format routes seed-dev seed-dev-docker \
	load-onintra-dump load-onintra-dump-docker runserver dev

help: ## List targets
	@grep -E '^[a-zA-Z0-9_.-]+:.*##' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-26s\033[0m %s\n", $$1, $$2}'

# --------------------------------------------------------------------------- #
# Docker dev stack
# --------------------------------------------------------------------------- #

up: ## Start the dev stack (db, redis, mailpit, minio, celery, web)
	$(COMPOSE) up

down: ## Stop the dev stack
	$(COMPOSE) down

clean: ## Stop stack and remove containers, volumes, and local images
	$(COMPOSE) down -v --rmi local --remove-orphans

dockerexec: ## Run any command in the web container, e.g. make dockerexec cmd="uv run pytest -k foo"
ifndef cmd
	$(error Set cmd=…, e.g. make dockerexec cmd="uv run python manage.py check")
endif
	$(DOCKEREXEC) $(cmd)

manage: ## Run a Django management command, e.g. make manage cmd="check --deploy"
ifndef cmd
	$(error Set cmd=…, e.g. make manage cmd="migrate")
endif
	$(MANAGE) $(cmd)

migrate: ## Apply database migrations (inside web container)
	$(MANAGE) migrate

makemigrations: ## Create migrations for model changes (inside web container)
	$(MANAGE) makemigrations

superuser: ## Create a Django superuser (inside web container)
	$(MANAGE) createsuperuser

shell: ## Open the Django shell (inside web container)
	$(MANAGE) shell

test-docker: ## Run pytest inside the web container
	$(DOCKEREXEC_T) uv run pytest

test-docker-fresh: ## Run pytest inside the web container with a recreated test DB
	$(DOCKEREXEC_T) uv run pytest --create-db

seed-dev-docker: ## Seed offices, roles, demo users, and announcements (web container)
	$(MANAGE) seed_dev

load-onintra-dump-docker: ## Import legacy onintra SQL in the web container (DUMP=path; DRY_RUN=1 optional)
ifndef DUMP
	$(error Set DUMP to the repo-relative .sql path, e.g. make load-onintra-dump-docker DUMP='u375931722_onintra (3).sql')
endif
	$(MANAGE) load_onintra_dump --dump="/app/$(DUMP)" \
		$(if $(DRY_RUN),--dry-run,)

# --------------------------------------------------------------------------- #
# Local toolchain
# --------------------------------------------------------------------------- #

runserver: ## Run Django dev server on :8000 (host)
	uv run python manage.py runserver

dev: ## Run Vite dev server on :5173 (HMR, host)
	pnpm run dev

test: ## Run backend tests on the host (parallel + reuse-db)
	uv run pytest

test-fresh: ## Run backend tests on the host with a recreated test database
	uv run pytest --create-db

checks: ## Pre-commit gate: lint, types, migration drift, frontend checks
	uv run ruff check .
	uv run ruff format --check .
	uv run ty check
	uv run python manage.py makemigrations --check --dry-run
	pnpm typecheck
	pnpm exec biome check .

format: ## Auto-format Python (ruff) and frontend (biome)
	uv run ruff format .
	uv run ruff check --fix .
	pnpm exec biome check --write .

routes: ## Regenerate frontend/types/routes.ts from Django URLs
	pnpm run routes:generate

seed-dev: ## Seed dev data on the host (SQLite / local DATABASE_URL)
	uv run python manage.py seed_dev

load-onintra-dump: ## Import legacy onintra SQL on the host (DUMP=path; DRY_RUN=1 optional)
	@echo "Note: this writes to the host database (SQLite by default)."
	@echo "      localhost:8000 from \`make up\` uses Postgres — run load-onintra-dump-docker instead."
ifndef DUMP
	$(error Set DUMP to the .sql file path, e.g. make load-onintra-dump DUMP='dump.sql')
endif
	uv run python manage.py load_onintra_dump --dump="$(DUMP)" \
		$(if $(DRY_RUN),--dry-run,)
