# Reservable office spaces

`apps.reservations` owns the room/space catalog, booking policy, office-local
weekly schedule, protected photos, availability exceptions, and transfer
history. Actual bookings and overlap exclusion constraints belong to the
downstream reservation workflow issues.

## Domain records

| Record | Contract |
| --- | --- |
| `Space` | Stable UUID, owning office, governed type, capacity, descriptive and sensitive location fields, lifecycle state, booking rules, and audit timestamps |
| `Amenity` / `SpaceAmenity` | Stable governed amenity codes and filterable categories; UI icon and color values are deliberately not stored |
| `WeeklyAvailability` | One or more non-overlapping local wall-time intervals for a weekday |
| `SpaceAvailabilityException` | A half-open aware interval for a holiday, maintenance window, closure, or administrative hold |
| `SpacePhoto` | Verified JPEG/PNG/WebP content in protected storage, with required alternative text and agent-visibility metadata |
| `SpaceOfficeTransfer` | Immutable origin/destination history for an authorized office move |

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

The downstream PostgreSQL overlap-hardening issue will add the exclusion
constraint shared by bookings and administrative blocks. These model intervals
already use the same half-open semantics and aware UTC persistence required by
that work.
