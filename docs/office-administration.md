# Office administration

Scoped office and regional administration for branch information, contact
assignments, hierarchy visibility, and links to related operations modules.

Permission: `web.manage_offices`. Scope follows the actor's effective office
tree (`company_wide`, region keys, or office keys). Out-of-scope offices return
404. Frontend `PermissionRequired` is a courtesy — every write re-checks
authority in `apps.user.services.office_administration`.

## Surfaces

| Route | Page | Who |
| --- | --- | --- |
| `/operations/offices` | List / filter | Managers with `web.manage_offices` |
| `/operations/offices/<id>` | Detail / edit | Same, office in scope |
| `/office-info` | Agent brochure | Authenticated; **primary office only** (no office id in the URL) |

Feature keys: `admin-offices` and `office-info` are live in `HUB_FEATURES` /
`OPERATIONS_FEATURES`.

## Field tiers

| Tier | Fields | Who may write |
| --- | --- | --- |
| Identity (read-only) | `stable_key`, `slug` | Nobody through product UI; `stable_key` is immutable |
| Info | Name, address, phones, public email, hours, parking, access copy, contacts | Any scoped `web.manage_offices` actor |
| Sensitive | `internal_email`, internal access instructions | Same scope; never in public/summary payloads |
| High-impact | `parent`, `kind`, `is_active`, `is_assignable` | Company-wide only; impact preview + `confirmed=1` |

## Contacts

`OfficeContactAssignment` types: branch manager, branch admin, broker contact,
transaction coordinator, IT support. Constraints:

- User must belong to the same office
- At most one primary per `(office, assignment_type)`
- Validity dates (`starts_at` / `ends_at`); end cannot precede start
- Optimistic concurrency via `expected_version` (office `updated_at`)

## Impact analysis

Deactivation and reparenting report affected primary users, memberships, role
grants, current contacts, and descendant offices before commit. The UI uses
`AccessChangeDialog`; the service raises `ConfirmationRequired` if `confirmed`
is missing.

## Agent preview and cache safety

Detail pages embed `office_info_payload(..., include_internal=True)` as
`agentPreview`. The agent page always derives the office from
`request.user.office`. Payloads include `id`, `updatedAt`, and `version` so a
primary-office change cannot reuse another office's body. There is no shared
HTTP cache for office info.

## Related resources

Detail links to Users, New Agents (live), and Coming Soon destinations for
inventory, reservations, announcements, and documents. Those modules keep their
own authorization.

## Audit

Material changes emit `office.updated`, `office.deactivated`,
`office.contact.created` / `.updated` / `.ended`, and reuse
`user.office.transferred` for reparenting.
