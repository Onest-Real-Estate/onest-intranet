# Onest developer shortcuts.
#
# Django management commands run inside the compose dev stack (the `web`
# service), so start it first:
#
#   make up            start the dev stack (db, redis, mailpit, minio, docuseal, celery, celery-beat, web)
#   make clean         stop everything and remove containers, volumes, and images
#   make migrate       apply database migrations
#   make makemigrations   create migrations for model changes
#   make superuser     create a Django superuser (prompts for credentials)
#   make shell         open the Django shell
#   make manage cmd="check --deploy"   run any management command

COMPOSE := docker compose --env-file .env -f deployment/compose.dev.yaml
MANAGE  := $(COMPOSE) exec web uv run python manage.py

.PHONY: up down clean migrate makemigrations shell superuser test manage

up:              ## Start the dev stack
	$(COMPOSE) up

down:            ## Stop the dev stack
	$(COMPOSE) down

clean:           ## Stop everything and remove containers, volumes, and images
	$(COMPOSE) down -v --rmi local --remove-orphans

migrate:         ## Apply database migrations
	$(MANAGE) migrate

makemigrations:  ## Create migrations for model changes
	$(MANAGE) makemigrations

superuser:       ## Create a Django superuser (prompts for username/email/password)
	$(MANAGE) createsuperuser

shell:           ## Open the Django shell
	$(MANAGE) shell

test:            ## Run the test suite with pytest
	$(COMPOSE) exec web uv run pytest

manage:          ## Run any management command, e.g. make manage cmd="check --deploy"
	$(MANAGE) $(cmd)
