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
capacity-consuming statuses via `apps.inventory.availability` /
`apps.inventory.capacity`.

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
| `over_allocation_*` | Explicit approved excess above physical capacity |

### Capacity state table

| Status | Consumes capacity? |
| --- | --- |
| `requested` | Yes |
| `confirmed` | Yes |
| `ready_for_pickup` | Yes |
| `checked_out` | Yes |
| `overdue` | Yes |
| `returned` | No |
| `completed` | No |
| `cancelled` | No |
| `denied` | No |
| `lost` | No |
| `damaged` | No |

Interval endpoints are **half-open** `[starts_at, ends_at)`. Adjacent bookings
that meet at an endpoint do not overlap.

### Locking and isolation

All capacity-affecting writes run in one short `transaction.atomic()` and follow
`apps.inventory.capacity`:

1. Lock `InventoryItem` with `select_for_update(of=("self",))` in ascending pk
   order.
2. Lock `InventoryReservation` rows the same way (ascending pk) after item
   locks.
3. Recalculate overlapping committed quantity; validate remaining capacity;
   create or transition the reservation.
4. Emit audit/domain events with `log_on_commit` — never while holding locks.
5. Never combine `select_for_update` with `select_related("owner_office")`.

The same path covers create, approve/deny, reschedule, quantity change,
cancel/release, return, item quantity reduction, and administrative override.
Preflight browser availability, frontend disabling, cache, and Celery are never
correctness boundaries.

Conflicts raise `AvailabilityConflict` (HTTP **409** on the create surface)
with an actionable message that never names other reservation owners.

### Admin override

`inventory.override_reservations` may bypass horizon / office-hours / cancel
cutoff policy (`bypass_policy=True`). It must **not** exceed
`total_quantity` unless `allow_over_allocation=True` with a non-empty reason,
which records `over_allocation_approved_at/by/reason` on the reservation.
Over-allocated rows still consume capacity for everyone else.

### Create path

Lock the inventory item, recompute overlapping quantity, validate policy,
insert one row. Idempotent `submission_key` retries return the first row.

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
and are enforced in the service layer; office lifecycle UI beyond agent cancel
is owned by the lifecycle issue (#64). Service helpers for approve, deny,
reschedule, quantity change, and return already share the capacity lock path.

## Availability

Available quantity for a requested interval is computed in
`apps.inventory.availability` against committed reservation windows from
`reservation_windows_for_items`. Item quantity reduction uses **peak**
overlapping demand (`peak_committed_quantity`), not a sum of non-overlapping
future holds.

Partial index `inv_rsv_capacity_overlap` covers
`(item, starts_at, ends_at)` for capacity-consuming statuses.

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
- #62 Inventory reservation workflow
- #63 Atomic double-booking hardening (this surface)
- #64 Full reservation lifecycle transitions
- #71 Unified My Reservations (rooms + inventory)
