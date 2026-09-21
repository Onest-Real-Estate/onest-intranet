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
8. **Register new apps.** If a requirement needs a new Django app, create it
   under `apps/` and add it to `INSTALLED_APPS`.
9. **Use Inertia navigation.** Use Inertia's `<Link>` for in-app navigation,
   never a plain `<a href>`.
10. **Beware nullable joins when locking.** Do not combine
    `select_for_update()` with `select_related("owner_office")`:
    `owner_office` is nullable, so PostgreSQL creates a `LEFT OUTER JOIN` and
    cannot apply `FOR UPDATE` to its nullable side. SQLite hides this.
11. **Check dependency blocks when requested.** If a prompt says to check
    dependencies, inspect its blocking GitHub issues with `gh`. Stop when an
    unresolved blocker is open and report the required work in dependency order.
12. **Check for well maintained django and react packages before implementing yourself**, do not implement
    something that is already available as a package it would save lots of time
13. **Use Self Hosted [Centrifugo](https://centrifugal.dev/) for all real time works**, do not use django channels and others use
    pusher compatible Open source Centrifugo if you reach for any realtime activity
14. **Use Pattern /apps/views/{agents_views.py,*}** : Use the above patterns for the file structure
15. **Use Enum instead of Raw Strings for comapraision**: Always create an Enum for all the states of comparison, if using database and if there is text choices use that for comparsion
16. **Hub-native agent contract e-sign**. Agent contracts use Hub field
 placement, Hub signing UI, and pyHanko org PKCS#12 sealing — not DocuSeal.
 Customer/transaction packages remain out of scope until a later decision.
17. **Use `inertiajs's` `router.post` and `router.get` or <Form/> component instead of default <form tag>**

## Commands

Two ways to run things. Pick one and stay consistent within a task.

**Local (fast, default for edits and checks)**

| Command | What |
| --- | --- |
| `uv run python manage.py runserver` | Django on :8000 |
| `pnpm run dev` | Vite dev server on :5173 (HMR) |
| `uv run pytest` | Backend tests (`-n auto --reuse-db`) |
| `pnpm test` | Frontend tests (vitest) |
| `pnpm run typecheck` | `tsc --noEmit` |
| `pnpm run routes:generate` | Regenerate `frontend/types/routes.ts` |

**Docker dev stack (`make up`)** — bundles Postgres, Redis, Mailpit, MinIO,
Celery worker + beat. Use when the task needs a real database, S3, mail,
or background tasks. Run commands in the `web` container via
`make dockerexec cmd="…"` or `make manage cmd="…"`; see `docs/dockerexec.md`.
Shortcuts: `make migrate`, `make makemigrations`, `make shell`, `make test-docker`.

**Pre-commit gate** (`.husky/pre-commit` — lint, types, migration drift; no tests):

```bash
uv run ruff check . && uv run ruff format --check . && uv run ty check \
  && uv run python manage.py makemigrations --check --dry-run \
  && pnpm typecheck && pnpm exec biome check .
```

**CI** still runs the above plus `uv run pytest` and `pnpm test`. Run those
locally when you want a full gate before pushing.

The `/checks` skill runs the pre-commit set in the right order and auto-fixes
what is safely fixable.

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
docs/dashboard-my-day.md  My Day agenda: provider contract, timezone/DST, buckets
docs/quick-access.md   Administered dashboard launchers: audience, grants, ordering
docs/quick-create.md   Global Quick Create menu: action registry, scope, safe returns
docs/search.md     Global search: provider contract, isolation, caps, palette
docs/notifications.md  In-app notifications: producers, sources, centre, badge
docs/onboarding-operations.md  Onboarding journey contract: states, gate, dialog, live updates
docs/onboarding-support.md  Onboarding measures, runbook, reset/rollback, staging, seams
docs/user-directory.md Scoped people directory: filters, field permissions, account state
docs/agent-directory.md Peer Agent Directory: privacy allowlist, visibility, gated headshots
docs/profile.md    Self-service profile: editable allowlist, normalization, audit
docs/agent-administration.md  Broker-controlled profile half: scope, delegation, audit
docs/agent-contracts.md  Agent contract schema, snapshots, scope, permissions
docs/roles.md      Brokerage role catalog: stable codes, scopes, permission bundles
docs/reporting.md  Scoped operational reports registry, exports, reconciliation
docs/role-assignment-administration.md  Assign User Roles: preview, concurrency, scopes
docs/office-resources.md  Scoped office resources: inheritance, precedence, protected files
docs/announcements.md  Announcements: taxonomy, audience union semantics, media pipeline
docs/training.md   Training library + admin: audience, versioning, media, lifecycle
docs/training.md   Training library: audience visibility, media, progress, admin
docs/marketing-resources.md  Marketing library + admin: audience, versioning, source/export
docs/compliance.md  Policies & compliance: audience, jurisdiction, lifecycle, acknowledgements
docs/documents-forms.md  Documents & forms library: current version, audience, protected files
docs/transactions.md  Real-estate deals: model, scope, lifecycle, field projection
docs/operational-tasks.md  Operational tasks: lifecycle, scope, conversion seam
docs/feedback.md   Feedback intake: diagnostic redaction, idempotency, triage
docs/it-support.md IT help desk: lifecycle, scope, internal notes, onboarding seam
docs/onboarding-tools.md  Agent tool catalog: location rules, guides, readiness
docs/reservable-spaces.md  Room model, capacity ledger, overlap invariant, race semantics
docs/room-availability.md  Agent-facing availability calendar: privacy, DST, bounded ranges
docs/room-administration.md  Scoped room admin: permissions, impact review, stale edits
docs/my-reservations.md  Unified self-service reservations: contract, buckets, isolation
DESIGN.md          Design tokens + visual world (values win over docs/design-system.md)
```

## Conventions

**Inertia pages.** View: `@login_required` + `@inertia("PageName")` returning a
dict of **camelCase** props. Heavy widgets use `defer(lambda: ..., group="...")`
so the shell paints first. Page: default-exported component, props read via
`usePage<Props>().props`, `<Head title={...} />`, and the layout attached as
`Page.layout = (page) => <HubLayout>{page}</HubLayout>`. Prop interfaces extend
`PageProps` and live in `frontend/types/index.ts`.

**URLs.** Reverse with the typed map, never string literals:
`routes.dashboard()`, `routes.my_contract()`.

### Django best practices

- Keep views thin: authorize, validate input, call a domain service or query
  helper, and construct the response. Put multi-step business rules and writes
  in the owning app's service layer, not in views, templates, or signals.
- Treat every request value as untrusted. Use Django forms or explicit typed
  parsers, return the repository's standard validation shape, and never pass
  unchecked client values into filters, ordering, redirects, or file paths.
- Apply permission and office-scope filters in the queryset before fetching
  objects. A later Python check can leak existence or fields and is not an
  authorization boundary. Use `get_object_or_404` or `PermissionDenied` according
  to the feature's documented disclosure policy.
- Prevent N+1 queries deliberately: use `select_related()` for required
  single-valued relations and `prefetch_related()` for collections. Paginate
  unbounded lists, use deterministic ordering, and add indexes only after
  checking real query plans or measurements.
- Keep write transactions short. Lock only the rows being changed with
  `select_for_update(of=("self",))`, acquire multiple locks in a stable order,
  and schedule email, storage, cache, and Celery side effects with
  `transaction.on_commit()` when they depend on a successful commit.
- Enforce durable invariants in models and database constraints, not only in
  React or form code. Use timezone-aware datetimes and avoid `save()` overrides
  or signals for workflows that need explicit ordering, actors, or audit data.
- Use safe HTTP semantics: GET/HEAD are read-only; state changes require
  POST/PUT/PATCH/DELETE, CSRF protection, and a redirect after success. Do not
  expose raw exception text, secrets, tokens, or unnecessary personal data in
  responses, logs, tasks, or audit metadata.
- Test authorization, validation, scope boundaries, transactions, and query
  behavior at the layer that owns them. Any locking or PostgreSQL-specific
  behavior needs a PostgreSQL-backed test; SQLite is not proof of correctness.

### Inertia.js best practices

- Treat an Inertia page as a server-owned protocol, not a client-side API. Props
  must be minimal, JSON-serializable presentation data with stable camelCase
  keys; never serialize model objects wholesale or include data merely because
  the current UI hides it.
- Keep global shared props small and genuinely global. Compute request-wide data
  once in middleware, use lazy callables for expensive values, and update the
  corresponding `PageProps` type whenever the shared contract changes.
- Use typed `routes.*` URLs with `<Link>` or `router`; do not hard-code internal
  paths or use `window.location` for normal visits. Use `replace`,
  `preserveState`, and `preserveScroll` only when the interaction requires them,
  not as blanket defaults.
- Submit mutations with Inertia's router/form helpers and this repository's
  validation contract (`fields` plus `form`). Disable duplicate submissions,
  surface server errors accessibly, and redirect after a successful mutation so
  refresh/back navigation does not repeat the write.
- Defer only independent, expensive props. Deferred values are `undefined`
  initially, so render a stable skeleton/empty state and keep prop types honest.
  For partial reloads, request only documented prop keys and wrap expensive
  server computations in callables so omitted props are not evaluated.
- Keep canonical filter, search, sort, and pagination state in the URL. Debounce
  noisy searches, cancel or ignore stale visits, and prefer `replace: true` for
  transient filter changes so browser history remains useful.
- Never rely on a hidden component or `<PermissionRequired>` as authorization.
  The Django endpoint must independently authenticate, authorize, scope, and
  validate every full visit, partial reload, and mutation.
- Give every page a meaningful `<Head title>`, keyboard-safe focus behavior,
  loading/empty/error states, and tests for the Inertia visit options and props
  that drive important behavior.

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

- **SSO only.** Auth flows through allauth's `microsoft_login`; don't add a
  local login form. `ALLOW_PASSWORD_LOGIN` (defaults to `DEBUG`) keeps
  allauth's email/password views for local onboarding; production must leave
  it off.
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
- **Inertia posts JSON; `request.POST` reads it only via middleware.** Inertia
  serializes a visit's data as `application/json` unless it carries a file, and
  Django parses `request.POST` only for form-encoded and multipart bodies.
  `apps.web.middleware.InertiaJsonPostMiddleware` translates the body at the
  edge so every view keeps one input contract. Two consequences: don't remove
  it, and **don't write a write-path test that only posts form-encoded** — the
  Django test client's default hid this bug across the whole app while every
  test passed. Post `content_type="application/json"` in at least one test per
  write surface.
- **Secrets live in `.env`** (python-decouple). Never commit them, never print
  them into logs, output, or artifacts.
