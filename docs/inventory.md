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
| `requires_approval` | When true, new reservations start as `requested`; otherwise auto-confirm |
| `total_quantity` | Authoritative on-hand count for pooled stock |
| `retired_at` | Set when state is `retired`; history is preserved |

Items are retired, never deleted. Office transfers are audited
(`InventoryTransfer`) and update `owner_office` in place so reservation history
keyed by `public_id` survives the move.

## Reservations

`InventoryReservation` holds one pickup/return interval for an agent. Capacity
is **not** a stored counter — overlapping quantity comes from rows in
capacity-consuming statuses via `apps.inventory.availability`.

| Field | Notes |
| --- | --- |
| `public_id` / `reference` | Stable UUID + human `INV-R-######` |
| `owner` | Agent the hold belongs to (self-serve only today) |
| `office` / `office_name` | Owning office snapshotted at create |
| `starts_at` / `ends_at` | Half-open `[start, end)` local midnight bounds |
| `quantity` / `purpose` | Positive quantity; optional business purpose |
| `status` | See `apps.inventory.reservation_taxonomy` |
| `instructions_snapshot` | Item notes + storage copied at create |
| `submission_key` | Unique idempotency key for create |

**Capacity-consuming statuses:** `requested`, `confirmed`, `ready_for_pickup`,
`checked_out`, `overdue`.

**Create path:** lock the inventory item (`select_for_update(of=("self",))`),
recompute overlapping quantity, validate policy, insert one row. Preflight
browser availability is never trusted at write time.

**Policy** (`apps.inventory.policy`):

- Pickup within 90 days; inclusive duration ≤ 14 days
- When `Office.office_hours` is configured, pickup and return days must be open
- Agent cancel allowed from `requested` / `confirmed` / `ready_for_pickup`
  until 24 hours before `starts_at`
- `requires_approval` → initial `requested`; else `confirmed`

**Agent workflow**

| Route | Purpose |
| --- | --- |
| `inventory_reservation_new` | Draft + `?review=1` authoritative summary |
| `inventory_reservation_create` | Idempotent POST → redirect to detail |
| `inventory_reservation_detail` | Confirmation, instructions, cancel |
| `inventory_reservations_mine` | Self-only list (interim My Reservations) |

Conflicting availability responses never name other reservation owners.

Admin on-behalf / approve / override permissions exist
(`inventory.reserve_on_behalf`, `approve_reservations`, `override_reservations`)
and are enforced in the service layer; office lifecycle transitions beyond
agent cancel are owned by the lifecycle issue (#64).

## Availability

Available quantity for a requested interval is computed in
`apps.inventory.availability` against committed reservation windows from
`reservation_windows_for_items`.

## Permissions

| Codename | Use |
| --- | --- |
| `web.view_inventory` | Manager catalog within effective scope |
| `inventory.manage_inventory` | Create, update, retire, transfer |
| `inventory.view_inventory_sensitive` | Asset id, serial, replacement value, internal notes |
| `web.view_reservations` | Admin reservation lists |
| `inventory.reserve_on_behalf` | Create for another user (not self-serve) |
| `inventory.approve_reservations` | Approve/deny requested holds |
| `inventory.override_reservations` | Policy override with reason |

Agents browse and reserve for themselves without `web.view_inventory`; the
queryset is resolved from the reader's primary office server-side.

Photos use protected storage unless `photo_is_public` is explicitly set.

## Agent browser

Route: `office_inventory` (`/office-inventory/`).

Authenticated agents browse **active reservable** items for their primary
office only. The Reserve CTA opens `inventory_reservation_new` with item/date
query context; the create endpoint revalidates.

## Administration UI

Route: `admin_inventory` (`/operations/inventory/`).

| Surface | Permission | Notes |
| --- | --- | --- |
| List / filters / detail | `web.view_inventory` | Scoped to the actor's effective office tree |
| Create / edit / lifecycle | `inventory.manage_inventory` | Optimistic concurrency via `expected_version` |
| Sensitive fields | `inventory.view_inventory_sensitive` | Asset id, serial, replacement value, internal notes |

## Query services

`apps.inventory.queries` is the single visibility gate:

- `manager_inventory(user, access=…)` — scoped manager lists
- `agent_inventory(user)` — active reservable items for the reader's office
- `apply_filters(…)` — category, state, tracking mode, search (indexed fields)

`apps.inventory.browser` builds the agent Inertia payloads; reservation windows
plug into availability through `reservation_windows_for_items`.

## Related issues

- #60 Admin inventory management UI
- #61 Agent Office Inventory browser
- #62 Inventory reservation workflow (this surface)
- #63 Atomic double-booking hardening (PostgreSQL concurrency suites)
- #64 Full reservation lifecycle transitions
- #71 Unified My Reservations (rooms + inventory)
