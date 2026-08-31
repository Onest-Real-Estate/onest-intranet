# Office inventory

Physical assets and pooled stock owned by assignable offices. Agents discover
active reservable items for their primary office; managers browse and manage
inventory within their effective office/region scope.

## Data model

| Field | Notes |
| --- | --- |
| `public_id` | Stable UUID exposed to clients |
| `owner_office` | Owning assignable office; scope is read from it |
| `tracking_mode` | `serialized` (qty 1 + asset id) or `pooled` (total quantity) |
| `availability_state` | `active`, `available`, `temporarily_unavailable`, `damaged`, `lost`, `retired` |
| `total_quantity` | Authoritative on-hand count for pooled stock |
| `retired_at` | Set when state is `retired`; history is preserved |

Items are retired, never deleted. Office transfers are audited
(`InventoryTransfer`) and update `owner_office` in place so reservation history
keyed by `public_id` survives the move.

## Availability

Available quantity for a requested interval is computed in
`apps.inventory.availability` — it is **not** stored as a drifting global
counter. Reservation rows plug into that service in a later issue.

## Permissions

| Codename | Use |
| --- | --- |
| `web.view_inventory` | Manager catalog within effective scope |
| `inventory.manage_inventory` | Create, update, retire, transfer |
| `inventory.view_inventory_sensitive` | Asset id, serial, replacement value, internal notes |

Agents browse reservable items for their assigned office without
`web.view_inventory`; the queryset is resolved from the reader's primary
office server-side.

Photos use protected storage unless `photo_is_public` is explicitly set.

## Agent browser

Route: `office_inventory` (`/office-inventory/`).

Authenticated agents browse **active reservable** items for their primary
office only. Office scope is derived server-side from `user.office`; a
client-supplied office id is ignored. Managers with `web.view_inventory` still
see only their primary office on this surface — administrative catalogs stay
on `/operations/inventory/`.

| Surface | Access | Notes |
| --- | --- | --- |
| List / filters | Authenticated | Category, condition, name search, pickup/return dates, quantity |
| Item detail | Authenticated | Same field projection and office gate as the list |
| Photo | Authenticated | Only when `photo_is_public`; protected storage, no public URL |

Date-range availability uses `apps.inventory.availability` against committed
reservation windows (empty until #62). Unavailable results explain capacity
without naming other agents. The Reserve CTA carries item/date query context
into the reservation workflow placeholder; the create endpoint revalidates.

Agent payloads never include replacement value, internal notes, serial numbers,
or other agents' reservation identities. Asset id appears only with
`inventory.view_inventory_sensitive`.

## Administration UI

Route: `admin_inventory` (`/operations/inventory/`).

| Surface | Permission | Notes |
| --- | --- | --- |
| List / filters / detail | `web.view_inventory` | Scoped to the actor's effective office tree |
| Create / edit / lifecycle | `inventory.manage_inventory` | Optimistic concurrency via `expected_version` |
| Sensitive fields | `inventory.view_inventory_sensitive` | Asset id, serial, replacement value, internal notes |

The list supports search, category, tracking mode, condition, availability state,
and owning-office filters with pagination. The item workspace separates physical
state from interval-based booking availability, shows transfer history, and
records lifecycle transitions (unavailable, damaged, lost, restore, retire) in the
audit trail. Reservation panels and committed-quantity guards wire in when the
reservation workflow issues land (#62+).

## Query services

`apps.inventory.queries` is the single visibility gate:

- `manager_inventory(user, access=…)` — scoped manager lists
- `agent_inventory(user)` — active reservable items for the reader's office
- `apply_filters(…)` — category, state, tracking mode, search (indexed fields)

`apps.inventory.browser` builds the agent Inertia payloads (list, detail,
availability, empty states) on top of `agent_inventory`.

## Related issues

- #60 Admin inventory management UI
- #61 Agent Office Inventory browser (this surface)
- #62+ Inventory reservation workflow
