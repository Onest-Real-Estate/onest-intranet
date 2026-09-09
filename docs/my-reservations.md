# My reservations

One self-service destination for every booking in a person's name, across two
domains that keep their own time, status, and action semantics.

- Contract and composer: `apps/web/my_reservations/`
- Source providers: `apps/reservations/summaries.py`, `apps/inventory/summaries.py`
- Views: `apps/web/my_reservations/views.py`
- Pages: `frontend/pages/MyReservations.tsx`, `MyReservationDetail.tsx`

## Self-only by construction

No route in this module takes an owner, user, or office parameter. Each provider
starts from its domain's `for_owner(user)` queryset, and the detail and cancel
routes resolve a public id **through the reader's own feed** — so an id
belonging to somebody else is indistinguishable from one that does not exist and
returns 404.

There is deliberately no admin variant here. Scoped administration of other
people's bookings lives in `docs/room-administration.md` behind its own
permissions.

## Normalization is presentation, not authority

`display_status` is a coarse vocabulary — awaiting approval, confirmed, in
progress, overdue, completed, cancelled, denied, needs attention — that exists
so one page can sort a room booking beside an equipment hold without the reader
learning two lifecycles.

The domain's own code and label travel with every row in `source_status` and
`status_label`, and both are rendered. Mapping runs one way only: nothing turns
a normalized status back into a domain one, and this page never writes a status.
Each domain maps **every** one of its codes explicitly — a test asserts the
mapping covers the domain's full status set, so a new state cannot silently
inherit another's meaning.

## Time semantics differ, on purpose

A room booking is an instant with a real start and end on the clock. An
inventory hold is a **date**: you collect an item during a day. Those rows carry
`all_day` with a `local_date`, and their `starts_at` is only a sort position.
Rendering a pickup window as midnight-in-some-zone is how "Friday" becomes
"Thursday 11pm" for a reader one zone west.

Every row also carries the IANA zone it must be read in — the office's, not the
viewer's.

## Ordering

Upcoming reads soonest-first; past and cancelled read newest-first. The sort key
is `(bucket, signed timestamp, source_id)` — one uniform key across all buckets,
because a datetime key and a time-until key cannot be compared to each other.
`source_id` is the tiebreak that makes the order stable, which is what a cursor
needs.

Cancelled and denied rows leave the time axis entirely rather than sorting into
Past: a cancellation is a decision someone wants to find, not history to bury.
Overdue rows stay in Upcoming despite being past their return time, because they
are the most actionable thing the reader has.

## Partial failure

Each provider is called inside its own try/except. One that raises is logged and
skipped, and the page names it — "Equipment could not be loaded" — rather than
presenting a half list as the whole truth or blanking the half that answered.

## Actions delegate

A provider decides which actions to offer by asking its own domain (the room
service's cancellation cutoff; `inventory.policy.agent_may_cancel`). The view
then routes the request to that domain's service, which re-checks permission,
cutoff, capacity, and overlap for itself. Every action carries the
`expected_status` it was rendered against, so a tab left open overnight cannot
act on a record that has moved on.

## My Day

`apps/reservations/agenda.py` supplies room bookings to the My Day agenda, which
had been registered and dark. My Day now costs one query per available source —
tasks, rooms, inventory.
