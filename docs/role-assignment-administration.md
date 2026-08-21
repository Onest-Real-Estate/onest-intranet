# Role and scope assignment administration

The Assign User Roles destination under Operations
(`/operations/role-assignments`) is the product surface for granting,
scheduling, editing dates on, and revoking `UserRoleAssignment` rows. The
assignment service in `apps.user.services.role_assignments` remains
authoritative for delegation, duplicates, dates, and audit; this surface is
the caller that also owns preview, confirmation, and optimistic concurrency.

Per-user grant/revoke on the administrative record
([agent-administration.md](agent-administration.md)) still works for actors
with `user.change_user_administration`. The dedicated page is gated by
`web.assign_user_roles` and is aimed at brokerage administrators who need the
full matrix.

## Surfaces

| Route | Name | Permission | Purpose |
| --- | --- | --- | --- |
| `GET /operations/role-assignments` | `admin_assign_roles` | `web.assign_user_roles` | Scoped people index |
| `GET /operations/role-assignments/<id>` | `admin_assign_roles_user` | `web.assign_user_roles` | One person's workspace |
| `POST …/<id>/preview` | `admin_assign_roles_preview` | `web.assign_user_roles` | Dry-run effective access |
| `POST …/<id>/assignments` | `admin_assign_roles_mutate` | `web.assign_user_roles` | Grant, edit, or revoke |

Out-of-scope user ids are **404**, not 403.

## Scopes

| Scope | `scope_office` | Org reach |
| --- | --- | --- |
| `company` | must be null | Brokerage-wide |
| `region` | required region node | That region |
| `office` | required branch / regional office | That office |
| `assigned_record` | must be null | Permissions only — no office/region expansion |

`assigned_record` is valid for Realtor and both Transaction Coordinator roles.
Effective access sets `assigned_record=True` without adding office or region
keys, so authorization/navigation that depends on org reach stays narrow.

## Preview and confirmation

Preview builds a hypothetical assignment set and runs the same effective-access
helpers used after save. The response includes before/after snapshots,
permission and operations-navigation deltas, high-impact changes, and warnings.

High-impact grants (company-wide, management/protected roles) and high-impact
revocations (last live role, management loss) require `confirmed=1` on the
mutate POST. The UI shows `AccessChangeDialog` first; the server still
re-validates.

## Concurrency

- Grant: `expected_version` is `grant_version(user)` (max assignment
  `updated_at`, or `"0"`).
- Edit / revoke: `expected_version` is that row's `updated_at`.
- Mismatch → **409** with refreshed workspace props.

## Guards (server)

- No self-assignment or self-escalation.
- Only roles/scopes the actor may delegate (`actor_can_manage_assignments`).
- Protected roles blocked for non-superusers.
- Duplicate live (role, scope, office) rejected.
- Engaged agents cannot lose their last live assignment without a replacement
  (same rule as agent administration).
- Successful mutations call `invalidate_permission_cache`; the target's next
  request recomputes access, and `shell.authorizationVersion` changes.

## Unavailable options

The workspace sends every catalog role with `available` and
`unavailableReason` (protected, deactivated, or outside delegation) so the UI
can explain disabled choices without inventing rules.

## Related docs

- [roles.md](roles.md) — catalog and assignment policy
- [agent-administration.md](agent-administration.md) — per-user record panel
- [administrative-navigation.md](administrative-navigation.md) — ops nav
- [permissions.md](permissions.md) — capability vs scope
