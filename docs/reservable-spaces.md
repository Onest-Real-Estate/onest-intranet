# Reservable office spaces

`apps.reservations` owns the room/space catalog, booking policy, office-local
weekly schedule, protected photos, availability exceptions, transfer history,
the shared capacity ledger, and the reservation record. The Inertia calendar,
booking pages, and reservation service layer are still downstream work.

## Domain records

| Record | Contract |
| --- | --- |
| `Space` | Stable UUID, owning office, governed type, capacity, descriptive and sensitive location fields, lifecycle state, booking rules, and audit timestamps |
| `Amenity` / `SpaceAmenity` | Stable governed amenity codes and filterable categories; UI icon and color values are deliberately not stored |
| `WeeklyAvailability` | One or more non-overlapping local wall-time intervals for a weekday |
| `SpaceAvailabilityException` | A half-open aware interval for a holiday, maintenance window, closure, or administrative hold |
| `SpacePhoto` | Verified JPEG/PNG/WebP content in protected storage, with required alternative text and agent-visibility metadata |
| `SpaceOfficeTransfer` | Immutable origin/destination history for an authorized office move |
| `Occupancy` | The capacity ledger: one half-open aware interval per capacity consumer, tagged with its source |
| `Reservation` | The audited booking — owner, office/space snapshot, purpose, lifecycle status, and the ledger row it holds |

Durations and capacity are positive. Maximum duration cannot be below minimum
duration. Notice, buffers, and cancellation cutoff are nonnegative. Recurrence
uses a governed policy (`none`, `weekly`, or `daily_or_weekly`) and an enabled
policy requires a bounded maximum occurrence count.

## Office timezone and DST

Every `Office` has a validated regional IANA timezone (currently seeded offices
default to `America/New_York`). Weekly intervals are naive wall times interpreted
in that office timezone; stored exceptions are timezone-aware instants. Weekly
intervals may not cross midnight. A closed day has no interval.

All resolved intervals use half-open semantics: `[start, end)`. This permits an
interval ending at 10:00 and another beginning at 10:00 without overlap.

DST boundaries use a deliberate policy in `apps.reservations.availability`:

- A nonexistent spring-forward boundary advances to the first valid local minute.
- An ambiguous fall-back start selects the earlier instant (`fold=0`).
- An ambiguous fall-back end selects the later instant (`fold=1`).

This preserves the full advertised office window and makes the conversion to UTC
deterministic. The calendar and final booking service must share this resolver;
calendar output remains advisory until the downstream atomic booking check.

## Lifecycle and identity

`Space.public_id` and `Amenity.code` are immutable. ORM hard deletion of spaces is
blocked; use `retire_space`, which preserves the row and makes it ineligible for
new agent bookings.

The downstream booking service must set `booking_history_started_at` when the
first booking is committed. A normal `transfer_space` then fails closed. Only
`migrate_space_office`, which locks the space and writes a
`SpaceOfficeTransfer(preserves_booking_history=True)` record, can move it while
preserving the stable identity and historical office context.

## Scope and sensitive fields

Agents use `agent_spaces(user)`, which derives the office from `user.office` and
returns active reservable spaces only. It never accepts an office id. Scoped
administrators use `manager_spaces(user, access=...)`; capability is checked
before the office/region/company reach is applied in SQL.

| Permission | Purpose |
| --- | --- |
| `reservations.view_spaces` | Read room/space administration records in effective scope |
| `reservations.manage_spaces` | Create, retire, and move spaces in effective scope |
| `reservations.manage_space_schedules` | Manage weekly intervals and exceptions in effective scope |
| `reservations.view_space_sensitive` | Read internal access instructions and internal exception details |
| `reservations.book_spaces` | Book a reservable space at the assigned office and manage own reservations |
| `reservations.manage_reservations` | Act on other people's reservations in effective scope |
| `reservations.override_reservations` | Book outside notice/horizon/duration/capacity policy with a recorded reason |

`SpacePermission` mirrors `Space.Meta.permissions`; `ReservationPermission`
mirrors `Reservation.Meta.permissions`. Every catalog role may book. Managing
someone else's reservation follows the scoped-administrator set; overriding
policy stays with the manager roles.

Without the sensitive permission, `access_instructions` is deferred and absent
from presentation payloads, and internal exceptions are omitted. Internal blocks
still remove availability: visibility controls disclosure, never whether the
block applies.

## Storage and query indexes

Photos use `apps.user.storage.private_storage`; consumers must stream them through
an authorized Django view rather than expose storage URLs. The schema indexes
office/state/type and office/reservable/display order for catalog queries,
space/weekday/time for weekly resolution, and space/start/end plus
space/kind/start for bounded exception overlap queries.

## The capacity ledger and the overlap invariant

Bookings and administrative blocks consume the same resource, so they share one
table. Every `Reservation` owns exactly one `Occupancy`, and so does every
`SpaceAvailabilityException` — the exception's `save()` mints and keeps its
ledger row in step, which is why `create_availability_exception` validates with
`exclude={"occupancy"}`. A reservation's ledger interval is the booked interval
widened by the space's configured buffers, so cleanup time is protected by the
same invariant as the meeting itself.

Overlap is decided by one PostgreSQL exclusion constraint added in migration
`0003`:

```sql
EXCLUDE USING GIST ("space_id" WITH =, (TSTZRANGE("starts_at", "ends_at", '[)')) WITH &&)
  WHERE ("consumes_capacity")
```

Three consequences worth stating plainly:

- **`consumes_capacity` is the release switch.** Cancelling a reservation clears
  the flag rather than deleting the row, so the time frees up while the audit
  history stays.
- **Two capacity-consuming blocks may no longer overlap on one space.** That was
  legal before the ledger. Migration `0003` refuses to run rather than silently
  drop one side, naming the offending rows so an operator resolves them.
- **Away from PostgreSQL the invariant does not exist.** `apps.reservations.operations`
  makes the constraint and its `btree_gist` extension no-ops on other backends,
  and keeps them out of migration state so `makemigrations --check` stays clean.
  The SQLite suite proves the service-level checks and the compiled DDL, never
  the race. Any test that claims to prove the race must run on PostgreSQL.

`Reservation` rows are never hard-deleted; `delete()` raises. Reference, public
id, office snapshot, and ownership are immutable after creation.

### Losing the race

A writer can lose in two shapes, and `_save_occupancy` maps both to
`ReservationConflict` so the view answers `409` with a refresh prompt and no
detail about the competing booking:

- **`IntegrityError` / `ExclusionViolation` (`23P01`)** — the winner had already
  committed. This is what every observed race produces today, because
  `create_reservation` and `create_availability_exception` both take
  `select_for_update(of=("self",))` on the space row first and therefore
  serialize, and because a rescheduling `UPDATE` is checked against rows the
  winner has already written.
- **`OperationalError` with `deadlock detected` (`40P01`)** — two writers were
  inside the constraint check at once, each waiting on the other's uncommitted
  row. Reproduced by concurrent inserts that hold no space lock; PostgreSQL
  aborts one. No current service path reaches it, since all of them either take
  the space lock or update an existing row, but the ledger is the shared write
  surface and an unmapped deadlock would surface as a `500` instead of a `409`.

`reschedule_reservation` is the one write path that does not lock the space row
— it locks its own reservation and occupancy — so it is the path to re-examine
if a new caller is added.

### Two mutations worth naming

**Moving a booking between rooms has no service.** `transfer_space` and
`migrate_space_office` move a *space* between offices; nothing moves a
reservation from one room to another. Because the invariant lives on the ledger
and keys on `space_id`, such a move is judged against the destination room the
moment it is written, so the guarantee is already in place for whoever adds the
mutation. `test_postgres_scopes_a_room_move_to_the_destination_room` pins that.

**Buffer-policy edits are not retroactive.** Changing a space's
`buffer_before_minutes` / `buffer_after_minutes` affects subsequent writes only;
occupancies already committed keep the interval they were written with, and each
`Reservation` snapshots the buffers it was created under. This is deliberate —
retroactively widening live rows could push the table into a state the exclusion
constraint rejects, with no sound way to choose which booking loses.

Concurrency tests live in `apps/reservations/tests/test_occupancy.py` behind the
`postgres_only` marker and `django_db(transaction=True)`. They open a real
connection per thread and release both at a barrier. Run them against
PostgreSQL, where they are the only proof of the invariant:

```bash
make dockerexec cmd="uv run pytest apps/reservations -q -p xdist -n0"
```

`-n0` matters: these tests need serial execution and their own connections.
