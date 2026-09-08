# Room administration workspace

The scoped counterpart to `docs/room-availability.md`. Where that surface lets an
agent browse and book, this one lets a delegated administrator change what there
is to book: identity, booking policy, opening hours, maintenance blocks, and
other people's reservations.

Domain services live in `apps/reservations/administration.py`; the HTTP surface
is `apps/reservations/views/admin_views.py`; the pages are
`frontend/pages/SpaceAdministration.tsx` and
`frontend/pages/SpaceAdministrationWorkspace.tsx`.

## Scope and permissions

Four permissions are deliberately separate, so a schedule keeper is not also a
room editor and neither can touch a booking:

| Permission | Grants |
| --- | --- |
| `reservations.view_spaces` | Open the list and a room workspace |
| `reservations.manage_spaces` | Create, edit, activate/deactivate, retire |
| `reservations.manage_space_schedules` | Replace weekly hours, add/edit/remove blocks |
| `reservations.manage_reservations` | Move or cancel another user's booking |
| `reservations.view_space_sensitive` | Read access instructions and internal block reasons |

Every view resolves its target through `manager_spaces()` — the
hierarchy-scoped queryset — before a service runs. A room, block, or booking
outside the actor's effective hierarchy returns **404, not 403**: a 403 would
confirm that the record exists.

Scope is revalidated per object, not per request. `move_reservation` checks
`SpacePermission.MANAGE` against the **destination's** office independently of
the source, and the view resolves the destination through the actor's own scoped
queryset rather than trusting the posted id. Moving a booking into a room you
cannot administer fails even when you administer the room it is leaving.

## Impact review

Schedule, policy, and lifecycle changes can strand a booking that is already on
someone's calendar. `future_impact()` answers *which* bookings and *why* before
anything is written:

- With no proposal it reports every future capacity-holding booking — what
  deactivation and retirement need.
- With a proposed `policy` or `schedule` it reports only the bookings that would
  **stop** being valid, each with a reason ("Falls outside the new opening
  hours", "Shorter than the new minimum duration"). An edit that leaves every
  booking valid does not interrupt the administrator at all.

When the report is non-empty and the actor has not acknowledged it, the service
raises `ImpactRequiresAcknowledgement` and the view answers **409** with an
`impact` prop. The page lists the affected bookings and offers one explicit
"Apply anyway", which replays the same edit with `acknowledgeImpact`. Nothing is
written until then.

Only fields that can actually invalidate a booking trigger this
(`IMPACTING_SPACE_FIELDS`): capacity, bookability, duration bounds, and buffers.
Renaming a room does not.

## Stale edits

`update_space` and `replace_weekly_schedule` accept `expected_updated_at`, which
the workspace sends from the copy it loaded. If the row moved on in between, the
service raises `StaleEdit` and nothing is overwritten.

The comparison uses a 1ms tolerance — enough to absorb sub-microsecond loss in
JSON round-tripping, small enough that two deliberate edits a second apart are
still caught. A wider tolerance silently permits the clobber the check exists to
prevent.

## Overlap safety

Blocks and moved bookings write to the same capacity ledger as any reservation,
so the PostgreSQL exclusion constraint governs them (see
`docs/reservable-spaces.md`). Two guards sit in front of it:

- `_guard_no_protected_overlap()` runs before the write and produces a specific,
  readable refusal on **every** backend, including SQLite where the constraint
  does not exist.
- `_save_occupancy()` maps whatever the database raises to one
  `ReservationConflict`, which the views return as **409**.

A block therefore cannot be created over a live booking. Freeing that time is a
deliberate act: move or cancel the booking first.

## Audit and notifications

Every lifecycle change publishes a domain event with before/after context:
`reservations.space.updated`, `.activation_changed`, `.schedule_replaced`,
`.availability_block_updated`, `.availability_block_removed`,
`reservations.booking.moved`, and `.cancelled_by_admin`. Notifications are built
from those events by `apps/notifications/producers.py` — adding a notification
never means editing this workflow.

Moves and admin cancellations require a non-empty reason, which is recorded on
the event and shown to the person whose booking changed.

## Interaction notes

The weekly-hours editor is a list of rows, not a drag-to-paint grid: it has to
be completable from the keyboard, and a painted grid cannot express "08:00–12:00
and 13:00–17:00" without a second control anyway. It refuses overlapping
intervals on one day client-side before the server has to.

Both pages are container-query driven — the workspace declares `@container` and
its panels size to their own column, never to the viewport behind the sidebar.
Destructive actions confirm in a dialog whose submit stays disabled until a
reason is typed.
