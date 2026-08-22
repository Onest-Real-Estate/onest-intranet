# oNEST HUB — agent guide

Internal intranet for oNEST real estate: **Django 6 + Inertia.js + React 19 +
shadcn/ui**, Microsoft (Entra ID) SSO only. This file is the working contract for
AI agents. `README.md` is the human setup guide — read it for env vars, SSO
registration, and deployment; don't duplicate it here.

## Golden rules

1. **Never hand-format.** `ruff format` owns Python, `biome` owns TS/TSX/JSON.
   Write code, then run the formatter.
2. **Never edit generated files.** `frontend/types/routes.ts` is generated
   (`pnpm run routes:generate`) but **committed**. `assets/` is build output.
3. **Add a Django URL → regenerate routes.** Any change to a `urls.py` requires
   `pnpm run routes:generate` in the same commit, or the frontend breaks.
4. **Permission checks are two-sided.** Guarding the UI is not security. Every
   restricted page needs `@permission_required` on the view *and*
   `<PermissionRequired>` / `hasPermission` in the page.
5. **No raw colors.** Use the semantic Tailwind tokens from
   `docs/design-system.md`. A literal hex in a component is a bug.
6. **Model change → migration in the same commit.** CI runs
   `makemigrations --check --dry-run` and fails on drift.
7. **Ask before touching** `config/settings.py` auth/CSRF settings,
   `deployment/`, `.github/workflows/`, or anything under `migrations/` that is
   already applied.
8. If there is a requirement only if create a new apps under `apps/` folder add it to `settings.py`
9. Do not use plain <a href> tag use inertia's <Link></Link> tag for all the movement 
10. select_for_update() with select_related("owner_office").
     owner_office is nullable → Postgres LEFT OUTER JOIN → FOR UPDATE cannot be
     applied to the nullable side of an outer join. SQLite hides this.
## Commands

Two ways to run things. Pick one and stay consistent within a task.

**Local (fast, default for edits and checks)**

| Command | What |
| --- | --- |
| `uv run python manage.py runserver` | Django on :8000 |
| `pnpm run dev` | Vite dev server on :5173 (HMR) |
| `uv run pytest` | Backend tests |
| `pnpm test` | Frontend tests (vitest) |
| `pnpm run typecheck` | `tsc --noEmit` |
| `pnpm run routes:generate` | Regenerate `frontend/types/routes.ts` |

**Docker dev stack (`make up`)** — bundles Postgres, Redis, Mailpit, MinIO,
DocuSeal, Celery worker + beat. Use when the task needs a real database, S3, mail,
or background tasks. Management commands go through `make manage cmd="..."`,
`make migrate`, `make makemigrations`, `make shell`, `make test`.

**The gate — run before every commit** (identical to `.husky/pre-commit` and CI):

```bash
uv run ruff check . && uv run ruff format --check . && uv run ty check \
  && uv run pytest && uv run python manage.py makemigrations --check --dry-run \
  && pnpm typecheck && pnpm test && pnpm exec biome check .
```

The `/checks` skill runs this in the right order and auto-fixes what is safely
fixable.

## Layout

```
config/            Django project — settings.py, urls.py, celery.py
apps/user/         User model, Microsoft SSO views, onboarding, offices, roles
apps/web/          Inertia pages, shared props middleware, permissions, tasks
apps/notifications/  Notification domain, producers, centre, header badge
apps/announcements/  Announcement domain, taxonomy, presentation + policy adapters
frontend/pages/    One .tsx per Inertia page — the name in @inertia("Name")
frontend/components/       App components (HubLayout, PermissionRequired, …)
frontend/components/ui/    shadcn/ui primitives — regenerate, don't hand-edit
frontend/lib/      routes.ts, permissions.ts, hub-nav.ts, utils.ts
frontend/types/    index.ts (hand-written props) · routes.ts (GENERATED)
docs/design-system.md  Color/type/spacing contract for all UI work
docs/permissions.md    Permission catalog, capability vs scope, frontend payload
docs/dashboard-metrics.md  Metric registry: permissions, scope, calculations
docs/dashboard-profiles.md  Per-role dashboard profiles, widget registry, resolution
docs/dashboard-action-items.md  Action-item contract, sources, ordering, CTAs
docs/quick-access.md   Administered dashboard launchers: audience, grants, ordering
docs/notifications.md  In-app notifications: producers, sources, centre, badge
docs/user-directory.md Scoped people directory: filters, field permissions, account state
docs/profile.md    Self-service profile: editable allowlist, normalization, audit
docs/agent-administration.md  Broker-controlled profile half: scope, delegation, audit
docs/roles.md      Brokerage role catalog: stable codes, scopes, permission bundles
docs/role-assignment-administration.md  Assign User Roles: preview, concurrency, scopes
docs/office-resources.md  Scoped office resources: inheritance, precedence, protected files
docs/announcements.md  Announcement taxonomy: governance, ordering, filters, adapters
DESIGN.md          Raw design tokens (Material-style palette export)
```

## Conventions

**Inertia pages.** View: `@login_required` + `@inertia("PageName")` returning a
dict of **camelCase** props. Heavy widgets use `defer(lambda: ..., group="...")`
so the shell paints first. Page: default-exported component, props read via
`usePage<Props>().props`, `<Head title={...} />`, and the layout attached as
`Page.layout = (page) => <HubLayout>{page}</HubLayout>`. Prop interfaces extend
`PageProps` and live in `frontend/types/index.ts`.

**URLs.** Reverse with the typed map, never string literals:
`routes.dashboard()`, `routes.coming_soon("my-contract")`.

**Roles.** Catalog codes in `apps/user/roles.py` (`system_admin`, `realtor`, …)
map to Django Groups for permissions. Assignments store stable codes; display
names are presentation only. Scope follows the user's office tree and
`UserRoleAssignment` scope. See `docs/roles.md`. Never authorize from a role
label alone — use Django permissions on both sides of the stack.
See `docs/permissions.md` for the reviewed catalog and capability helpers.

**Tests.** Backend: `apps/<app>/tests/test_*.py`, pytest-django, `@pytest.mark.django_db`
where the DB is needed; assert on the Inertia page JSON, not on HTML strings (see
`inertia_page_script` in `apps/web/tests/test_permissions.py`). Frontend: `*.test.ts`
next to the source. New behavior ships with a test.

**Style.** ruff: line length 88, target py313, rules `E,F,I,B,UP,SIM,C4`, first-party
`apps`/`config`. biome: double quotes, semicolons, trailing commas, width 88, 2-space
indent. Types: `ty` on the backend, `tsc --noEmit` on the frontend — both must pass.

## Gotchas

- **SSO only.** There is no password login. Auth flows through allauth's
  `microsoft_login`; don't add a local login form.
- **Onboarding middleware.** `ProfileCompletionMiddleware` redirects incomplete
  profiles to `/onboarding`. A new page that must be reachable before onboarding
  has to be added to the exempt list in `apps/user/middleware.py`.
- **CSRF naming is deliberate.** `CSRF_COOKIE_NAME` / `CSRF_HEADER_NAME` are set
  for Inertia's `XSRF-TOKEN` → `X-XSRF-TOKEN` convention. Changing them breaks
  logout and every `router.post`.
- **Bump `INERTIA_VERSION`** in `config/settings.py` when the frontend bundle
  changes meaningfully, so stale clients hard-reload.
- **pnpm blocks fresh releases.** `minimumReleaseAge: 10080` (7 days) in
  `pnpm-workspace.yaml` — a brand-new package version will refuse to install.
  That is supply-chain hardening, not a bug; don't disable it to unblock yourself.
- **Secrets live in `.env`** (python-decouple). Never commit them, never print
  them into logs, output, or artifacts.

