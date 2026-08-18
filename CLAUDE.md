# CLAUDE.md

@AGENTS.md

## Scope note

Instructions inherited from `~/CLAUDE.md` describe **Chatpatey AI** (React Native
/ Expo / Supabase street-food app). That is a different project and **does not
apply here**. This repository is a Django + Inertia + React intranet; follow
`AGENTS.md` above and ignore the React Native / Supabase methodology, folder
structure, and schema for any work in this repo.

## Working here

- Prefer the local toolchain (`uv run …`, `pnpm …`) over `make …` unless the task
  needs Postgres, Redis, S3, mail, or Celery — then bring up the docker stack.
- Run `/checks` before reporting a change as done. Report failures with their
  output rather than describing them.
- `/add-page` walks the full recipe for a new Inertia page; `/design-system`
  carries the UI token rules. Use them instead of re-deriving conventions.
- Migrations, `deployment/`, and CI workflows are high-blast-radius: propose the
  change before applying it.
