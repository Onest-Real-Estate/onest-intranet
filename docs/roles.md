# Brokerage role catalog

Stable role **codes** are the identity used in assignments, migrations, and
integrations. Display names are presentation only. Authorization always uses
Django permission codenames (`web.view_users`, `user.change_user_administration`,
…); a role badge or label is never a grant.

## Required roles (14)

| Code | Display name | Default scopes | Protected | Baseline capabilities |
| --- | --- | --- | --- | --- |
| `system_admin` | System Admin | company | yes | Full operations + role assignment + agent administration |
| `principal_broker` | Principal Broker | company | yes | Same operational surface as System Admin; enhanced assignment audit |
| `broker_admin` | Broker Admin | company | no | Full operations; may assign non-protected roles company-wide |
| `regional_manager` | Regional Manager | region | no | Regional people, transactions, inventory, offices, training |
| `regional_admin` | Regional Admin | region | no | Regional people/admin support without full manager bundle |
| `regional_transaction_coordinator` | Regional Transaction Coordinator | region | no | Regional transactions, contracts, documents |
| `branch_manager` | Branch Manager | office | no | Office people, inventory, training, agent administration |
| `branch_admin` | Branch Admin / Office Admin | office | no | Office people lists, training, documents |
| `transaction_coordinator` | Transaction Coordinator | office | no | Office transactions, contracts, documents |
| `realtor` | Realtor | office | no | Own dashboard metrics (default signup role) |
| `marketing_team` | Marketing Team | company | no | Announcements, feedback, documents |
| `accountant` | Accountant | company | no | Transactions, users, contracts, commission visibility |
| `compliance` | Compliance | company | no | Compliance, users, contracts, documents, admin profile view |
| `it_support` | IT Support | company | no | IT support and sanitized platform tasks |

Superadmin remains Django `is_superuser`, not a catalog role.

## Lifecycle

- Code catalog: `apps.user.roles.ROLE_DEFINITIONS`
- Persisted rows: `BrokerageRole` (seeded idempotently via `seed_roles` /
  migration `0017`)
- Permission carrier: Django `Group` named by `group_name` (legacy groups
  `Admins`, `Users`, `Region Managers`, `Branch Managers` are retained for the
  four roles that already existed)
- Assignments: `UserRoleAssignment.role` stores the **stable code**
- Deactivate: set `is_active` / `is_assignable` false — never delete system
  roles referenced by history
- Re-seed does **not** reactivate deactivated rows or overwrite presentation
  unless `--sync-presentation` is passed

## Assignment policy

- Only `system_admin`, `principal_broker`, and `broker_admin` (or superuser)
  may grant/revoke non-protected roles, and only within their effective scope
- Protected roles (`system_admin`, `principal_broker`) cannot be delegated by
  ordinary administrators
- Users cannot modify their own assignments
- Effective access = union of permissions from assigned role groups, constrained
  by explicit scope; fail closed on inconsistent hierarchy nodes

## Frontend

- Catalog helpers: `frontend/lib/roles.ts`
- Presentation: `RoleBadge` (shows label + optional scope; not an auth check)
- Admin UI receives `role`, `roleLabel`, `roleDescription`, and `scopeLabel`

## Related docs

- `docs/permissions.md` — permission catalog, capability vs scope, frontend payload
- `docs/authorization.md` — route policies and permission enforcement
- `docs/agent-administration.md` — who may edit broker-controlled profile fields
- `docs/hierarchy.md` — office tree and membership (when present)
