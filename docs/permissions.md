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
- `user.view_user_administration`, `user.change_user_administration`,
  `user.manage_account_state`
- `audit.can_view_activity_timeline` (user-facing timelines; distinct from raw audit)
- `audit.can_view_audit_events`, `audit.can_export_audit_events`

The peer [Agent Directory](agent-directory.md) is authenticated-only: it has no
capability codename. Visibility (`is_active` + engaged agent status) and the
directory field allowlist are the security boundary. Operations Users
(`web.view_users`) remains the admin people list — see
[user-directory.md](user-directory.md).

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

### Writing a notice vs sending it

Announcements split three ways rather than one:
`web.manage_announcements` opens the workspace and saves drafts,
`web.publish_announcements` moves a record between draft, scheduled,
published, and archived, and `web.pin_announcements` lifts a published one to
the top of the feed. The split follows what each action can actually do to a
reader: a draft reaches nobody, so authoring is the cheap grant and defaults
widely (office and regional administrators, compliance, IT support);
publication is the step that puts words in front of people and defaults to
managers and brokerage administrators. Pinning changes ordering only and never
who can read a notice, which is why it is neither of the other two. Every one
of the three is still bounded by the actor's office scope. See
`docs/announcements.md`.

### Training, marketing, and documents

Training authoring uses a single manage grant (`web.manage_training`). Marketing
resources split three ways, like announcements:

| Codename | What it gates |
| --- | --- |
| `web.manage_marketing_resources` | Draft, upload, audience, version within publication scope |
| `web.publish_marketing_resources` | Publish / schedule / unpublish / archive / restore |
| `web.download_marketing_sources` | Editable source-file stream (never on the consumer library) |

Export downloads use audience visibility alone. See
`docs/marketing-resources.md` and `docs/training.md`.

Documents & forms split authoring, publication, and retirement:

| Codename | What it gates |
| --- | --- |
| `web.manage_documents` | Draft, upload, audience, duplicate version within publication scope |
| `web.publish_documents` | Publish / schedule / supersede |
| `web.retire_documents` | Retire a published version after usage review |

A draft reaches nobody, so authoring is the cheap grant. Publication puts a
form in the library and supersedes the previous current sibling.
Retirement removes it from the library while keeping files and history.
See [documents-forms.md](documents-forms.md).

### Reading a record vs ending its access

`user.change_user_administration` maintains somebody's record;
`user.manage_account_state` disables or reactivates their account, which ends
every live session. They are separate codenames for the same reason: an
administrator who corrects agent IDs is not, by that fact, an administrator who
can lock people out. The account grant defaults to the brokerage admin roles
only. See `docs/user-directory.md`.

### Field-level reads

A permission can gate a *column* as well as a route. The people directory and
the administrative record omit keys the reader may not have — `agentStatus`,
`agentIdentifier`, and `startDate` behind `user.view_user_administration`;
`contractStatus` behind `web.view_agent_contracts`; operational notes behind
`user.change_user_administration`. Contract commission terms and contract
internal notes use `contract.view_commission_terms` and
`contract.view_internal_notes` (see [agent-contracts.md](agent-contracts.md)).
Keys are absent rather than null: a key
present but empty still discloses that the field exists.

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
- `docs/announcements.md` — announcement authoring, publication, and pinning
