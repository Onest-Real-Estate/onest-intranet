# Authorization Guide

All server-side entry points must declare an explicit authorization policy.
Frontend visibility is only a hint; the backend is the enforcement boundary.

## Route policy declarations

Project-owned Django views in `apps.user` and `apps.web` must use
`apps.web.authorization.enforce_policy("<policy_key>")`.

- `public`: reachable without authentication.
- `authenticated`: requires a signed-in user.
- `onboarding_only`: reachable while a user's profile is incomplete.
- `permission_protected`: requires authentication plus explicit Django auth permissions.

`AuthorizationPolicyMiddleware` denies any local route that is missing policy metadata
and writes `security.endpoint.unclassified` telemetry. The coverage test in
`apps/web/tests/test_authorization.py` fails if a project route is unclassified.

## Inventory

The machine-readable inventory lives in `apps/web/authorization.py`:

- `ROUTE_POLICIES` for normal Django routes.
- `NON_ROUTE_SURFACES` for admin prefixes, admin actions, and background tasks.

When adding a new protected surface:

1. Add or update the matching `AuthorizationPolicy`.
2. Decorate the route or wire the non-route surface through the shared service.
3. Add request tests for the allowed and denied cases.
4. Add scope tests if the surface reads collections, detail objects, counts, search,
   autocomplete, exports, or bulk mutations.

## Scope rules

Use shared helpers from `apps.web.authorization` instead of ad-hoc role checks:

- `scope_queryset_for_user_office(...)`
- `scope_queryset_for_offices(...)`
- `assert_admin_bulk_scope(...)`

Bulk operations must fail closed when the submitted collection contains any out-of-scope
object.

## Denials and request IDs

- 403 pages render `PermissionDenied` with the request ID.
- 404 pages render `NotFound` with the request ID.
- JSON/API endpoints return a structured body with `error` and `requestId`.
- Every response carries `X-Request-ID`.

## Background work

Sensitive tasks must carry explicit initiator context and revalidate it when the
worker starts. Use `system_actor` / `service_actor` for non-user work. See
`apps.audit.replay.request_replay_event()` and `apps.audit.tasks.replay_event()`.

## Permission catalog

Protected capabilities are inventoried in `apps/web/permission_catalog.py` and
evaluated through `apps.web.capability` (fail closed on unknown codenames).
Capability and organizational scope are separate layers; see
`docs/permissions.md`.

Frontend `user.permissions` / `PermissionRequired` are presentation only.
