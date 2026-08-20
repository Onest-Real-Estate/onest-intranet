# Permission catalog

Django `Permission` rows remain the runtime grant store. The reviewed catalog in
`apps/web/permission_catalog.py` is the code-owned inventory of every protected
intranet capability: description, domain, action, default roles, risk, and
whether an organizational scope context is required.

Authorization helpers **fail closed** on any `app_label.codename` absent from
this catalog.

## Layers (keep separate)

| Layer | Responsibility |
| --- | --- |
| Authentication | Session / Microsoft SSO (`request.user`) |
| Capability | Does the actor hold the permission? (`apps.web.capability`) |
| Scope | Which offices/regions does the grant apply to? (`get_effective_access`) |

Never treat a role label, badge, or client-supplied permission list as a grant.

## Codename convention

Use stable `domain.action` style Django codenames, for example:

- `web.view_users`, `web.add_users`, `web.assign_user_roles`
- `user.view_user_administration`, `user.change_user_administration`
- `audit.can_view_audit_events`, `audit.can_export_audit_events`

Sensitive actions split read / export / approve / manage rather than bundling
them into a single “admin” bit.

## Backend primitives

| Helper | Use |
| --- | --- |
| `has_capability(user, perm)` | Capability only |
| `evaluate_permission(user, perm, office=…)` | Capability + optional scope |
| `require_permission(...)` | Raise `PermissionDenied` + audit high-risk denials |
| `matches_permission_check(...)` | Shared any/all for views and APIs |
| `@permission_required` / `enforce_policy` | Route enforcement |
| `system_actor` / `service_actor` | Explicit non-user actors for tasks |

Unknown permissions, missing scope context (when the catalog marks a permission
`scoped=True`), inconsistent hierarchy nodes, and evaluation errors deny.

### Cache / invalidation

- Effective access is resolved per request (`get_effective_access` /
  `capability.request_access`). Mutation of role assignments takes effect on
  the next request.
- `shell.authorizationVersion` is a hash of effective roles, permissions, and
  scope keys. Clients compare successive values to detect mid-session revocation
  (`isAuthorizationStale` in `frontend/lib/permissions.ts`).

### Superuser vs System Admin

`is_superuser` is break-glass and bypasses capability checks. It must **not**
define production System Admin behaviour — System Admin receives grants only
through the role → group → permission matrix seeded from `apps.user.roles`.

## Role defaults

Role → permission bundles live in `apps.user.roles.ROLE_DEFINITIONS` and are
applied to Django groups via `seed_roles` / migrations. Catalog
`default_roles` document the intended recipients for reviews and docs; CI tests
assert every role default permission is catalogued.

### Paired scoped / company grants

Where a capability has a strictly wider variant, the two are separate codenames
rather than one grant with a scope flag: `web.manage_quick_access` covers links
inside the actor's own office scope, and `web.manage_company_quick_access`
additionally allows a brokerage-wide publish and editing company-owned
definitions. Revoking the wider one then never depends on reading a scope
field, and a scoped administrator cannot be widened by accident. See
`docs/quick-access.md`.

Direct user permission exceptions are not a product feature in P0. If added
later they must record grant/deny, reason, actor, effective dates, and scope,
and remain auditable.

## Frontend payload

Authenticated Inertia shares:

- `user.permissions` — sorted effective **catalogued** codenames only
- `shell.authorizationVersion` — opaque access fingerprint
- `shell.capabilitySchemaVersion` — catalog revision string (not a grant list)

Helpers: `hasPermission`, `isAuthorizationStale`, `isAccessRevoked`, and
`<PermissionRequired>`. UI gates are presentation only.

## Adding a permission

1. Add the Django permission on a model / unmanaged anchor (`Meta.permissions`)
   with a migration.
2. Add a `PermissionDefinition` in `permission_catalog.py`.
3. Attach it to role `default_permissions` in `roles.py` when it should seed.
4. Guard the view/API/task with shared helpers; add matrix tests.
5. Use the same codename in frontend `PermissionRequired` / nav checks.

## Related docs

- `docs/authorization.md` — route policies and scope helpers
- `docs/roles.md` — brokerage role catalog
- `docs/dashboard-metrics.md` — metric-level permissions
- `docs/quick-access.md` — administered dashboard launchers and their grants
