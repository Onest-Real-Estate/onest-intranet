# Docker exec workflow

The dev stack in `deployment/compose.dev.yaml` runs Django against **PostgreSQL,
Redis, Mailpit, MinIO, and Celery** inside Docker. Your repo is bind-mounted at
`/app` in the `web` container, so code edits on the host are visible immediately.

Use **`make dockerexec`** (or the shorter **`make manage`**) to run commands in
that environment without typing the full `docker compose exec` line.

## Start the stack

```bash
make up
```

In another terminal, keep Vite on the host for HMR:

```bash
make dev
```

Django is already served from the container on http://localhost:8000.

## `make dockerexec`

Runs an arbitrary command in the **`web`** service:

```bash
make dockerexec cmd="uv run python manage.py check"
make dockerexec cmd="uv run pytest apps/user/tests/test_onintra_import.py -q"
make dockerexec cmd="uv run python manage.py shell"
```

Equivalent raw compose invocation:

```bash
docker compose --env-file .env -f deployment/compose.dev.yaml exec web \
  uv run python manage.py check
```

**Paths inside the container** are under `/app` (the repo root). For example, a
dump file at the project root is `/app/u375931722_onintra (3).sql`.

Non-interactive runs (CI-style) use `-T` internally on `test-docker*` targets so
Docker does not allocate a TTY.

## `make manage`

Shortcut for Django management commands:

```bash
make manage cmd="migrate"
make manage cmd="makemigrations"
make manage cmd="createsuperuser"
make manage cmd="seed_dev"
make manage cmd="load_onintra_dump --dump='/app/dump.sql' --dry-run"
```

Dedicated Make targets wrap the same pattern:

| Target | What it runs in `web` |
| --- | --- |
| `migrate` | `manage.py migrate` |
| `makemigrations` | `manage.py makemigrations` |
| `superuser` | `manage.py createsuperuser` |
| `shell` | `manage.py shell` |
| `seed-dev-docker` | `manage.py seed_dev` |
| `load-onintra-dump-docker` | `manage.py load_onintra_dump` |
| `test-docker` | `uv run pytest` |
| `test-docker-fresh` | `uv run pytest --create-db` |

## Legacy onintra import (Docker)

The import needs Postgres and seeded offices — run it in the container:

```bash
make load-onintra-dump-docker \
  DUMP='u375931722_onintra (3).sql' \
  DRY_RUN=1

make load-onintra-dump-docker DUMP='u375931722_onintra (3).sql'
```

`DUMP` is **repo-relative**; the Makefile prefixes `/app/` for the container path.

## When to use Docker vs local

| Need | Use |
| --- | --- |
| Real Postgres, Redis, S3, mail, Celery | `make up` + `make dockerexec` / `make manage` |
| Fast Python/TS edits and unit tests (SQLite) | `uv run …`, `make test`, `make checks` on the host |
| Pre-commit / CI lint gate | `make checks` on the host |

## Troubleshooting

**`service "web" is not running`** — start the stack with `make up`.

**`exec … cannot enable tty`** — use a `*-docker` target that passes `-T`, or
run `docker compose … exec -T web …` directly.

**Database empty after `make clean`** — `clean` removes volumes; run
`make migrate` and `make seed-dev-docker` again.
