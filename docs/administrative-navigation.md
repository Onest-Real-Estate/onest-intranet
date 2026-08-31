# Administrative navigation

Administrative destinations use the same `HUB_NAV_REGISTRY` and responsive
sidebar as agent destinations. The `Administration` group is omitted when none of
its entries pass the current user's effective-permission checks. Roles are not read
by the frontend to decide visibility.

Within Administration, authorized entries retain the reviewed order and are divided
into `People`, `Operations`, `Content`, and `Governance & support`. A subsection with
no authorized entries is omitted, just like the parent Administration group.

The backend source of truth is `apps/web/operations.py`. The frontend mapping in
`frontend/lib/hub-nav.ts` is intentionally version controlled and covered by exact
contract tests. Availability is independent of authorization: setting a feature to
available never grants its permission, and every named route enforces its own policy.
Administrative feature keys are shared with the browser only after that destination's
permission succeeds.

## Route and permission map

| Order | Section | Label | Named route | Minimum permission | Scope rule |
| ---: | --- | --- | --- | --- | --- |
| 10 | People | Users | `admin_users` | `web.view_users` | User/office scope |
| 20 | People | New Agent List | `admin_new_agents` | `web.view_new_agents` | User/office scope |
| 30 | People | Add New User | `admin_add_user` | `web.add_users` | Delegated user scope |
| 40 | People | Assign User Roles | `admin_assign_roles` | `web.assign_user_roles` | Role delegation scope |
| 50 | People | Agent Contracts | `admin_agent_contracts` | `web.view_agent_contracts` | User/office scope |
| 55 | People | Contract Templates | `admin_contract_templates` | `contract.manage_contract_templates` | User/office scope |
| 60 | Operations | Transactions | `admin_transactions` | `web.view_transactions` | Transaction/office scope |
| 70 | Operations | Inventory | `admin_inventory` | `web.view_inventory` | Inventory/office scope |
| 80 | Operations | Reservations | `admin_reservations` | `web.view_reservations` | Reservation/office scope |
| 90 | Content | Announcements | `admin_announcements` | `web.manage_announcements` | Publication scope |
| 100 | Content | Training | `admin_training` | `web.manage_training` | Publication scope |
| 110 | Content | Documents | `admin_documents` | `web.manage_documents` | Publication scope |
| 120 | Governance & support | Compliance | `admin_compliance` | `web.view_compliance` | Compliance/office scope |
| 130 | Governance & support | Feedback | `admin_feedback` | `web.view_feedback` | Feedback/office scope |
| 140 | Governance & support | Platform Tasks | `admin_platform_tasks` | `web.view_platform_tasks` | Sanitized status only |
| 150 | Governance & support | Offices | `admin_offices` | `web.manage_offices` | Office tree scope |
| 160 | Governance & support | IT Support | `admin_it_support` | `web.view_it_support` | Support request scope |

**Users, New Agent List, Quick Access, Assign User Roles, Agent Contracts,
Offices, Office Resources, Announcements, and Contract Templates are live.** Their
feature keys in `OPERATIONS_FEATURES` are `True` and their registry entries
point at real views instead of the generated placeholder. The Users destination
is the people directory ([user-directory.md](user-directory.md)); opening a row
leads to the administrative record ([agent-administration.md](agent-administration.md)),
which is reached through the directory rather than through a nav entry of its
own. Assign User Roles
([role-assignment-administration.md](role-assignment-administration.md)) is the
dedicated grant/revoke workspace for actors with `web.assign_user_roles`.
Offices ([office-administration.md](office-administration.md)) is the scoped
office/regional administration surface for `web.manage_offices`.
Contract Templates ([agent-contracts.md](agent-contracts.md)) is the scoped
template authoring surface for `contract.manage_contract_templates`.

The remaining modules are intentionally unavailable until their domain backend ships. Their
explicit false feature keys show the protected destinations as “Soon” only to roles
whose effective permissions allow them; missing keys still hide. An authorized
direct visit can render the protected unavailable page, while an unauthorized visit
receives a 403 without the destination label. Removing a permission takes effect on
the next request. When a module becomes live, replace its placeholder view and set
its feature key to `True` in the same change.

## Baseline management grants

The `Admins` group receives all operations destination permissions. `Region Managers` and `Branch
Managers` receive the scoped operational subset below; high-risk permissions are
never implied by either scoped role.

| Destination | Admin | Region manager | Branch manager |
| --- | :---: | :---: | :---: |
| Users | Yes | Yes (own region) | Yes (own office) |
| — administrative record | Yes | Yes | Yes |
| — disable / reactivate | Yes | No | No |
| New Agent List | Yes | Yes | Yes |
| Add New User | Yes | No | No |
| Assign User Roles | Yes | No | No |
| Agent Contracts | Yes | No | No |
| Contract Templates | Yes | Yes | Yes |
| Transactions | Yes | Yes | No |
| Inventory | Yes | Yes | Yes |
| Reservations | Yes | Yes | Yes |
| Announcements | Yes | No | No |
| Training | Yes | Yes | Yes |
| Documents | Yes | Yes | Yes |
| Compliance | Yes | No | No |
| Feedback | Yes | Yes | Yes |
| Platform Tasks | Yes | No | No |
| Offices | Yes | Yes | Yes |
| IT Support | Yes | No | No |

Specialty access is permission-based. Compliance, accounting, marketing, support,
or coordinator users can receive only the permission for their module without an
`Admins` assignment. Their existing role assignments still determine office,
region, or brokerage scope.

## Data boundary

Navigation items carry no badges. Placeholder responses expose only the user's own
resolved scope label and no records, worker names, queue details, logs, secrets, or
counts. A future badge or alert must come from a purpose-built read model that first
checks the destination permission and applies the same effective office scope as the
page query.
