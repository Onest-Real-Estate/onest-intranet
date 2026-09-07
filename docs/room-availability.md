# Room availability calendar

The room availability page is the agent-facing projection of the reservations
domain. It combines a space's published weekly schedule, booking rules,
availability exceptions, and capacity-consuming reservations. The result is
advisory: every submitted reservation is validated again inside a database
transaction and the occupancy ledger remains the final overlap authority.

## Access and privacy

The page requires `reservations.book_spaces`. It defaults to the signed-in
user's office. Another office is selectable only when the existing office-scope
policy grants access to it; scope is applied before rooms or occupancies are
loaded.

Reservations owned by another user are serialized only as a `Busy` interval.
Their owner, title, purpose, attendee count, and related-record context are not
included. A user's own interval is labelled `Your reservation`. Public closure
reasons may be displayed, while internal maintenance and admin-hold reasons are
coarsened to `Unavailable` unless the viewer has
`reservations.view_sensitive_space_details`.

Calendar responses use `Cache-Control: private, no-store` because the busy
projection is user- and permission-specific.

## Query contract

`GET /rooms` accepts URL-backed `date`, `view`, `office`, `type`, `capacity`,
`amenities`, and `space` filters. `view` is `day`, `week`, or `list`; day returns
one local date and week/list return at most seven. Dates in the past and dates
more than 366 days ahead are rejected. At most 50 matching spaces are returned,
with an explicit truncation flag.

Each room day contains:

- published open intervals;
- privacy-safe busy or unavailable intervals;
- open intervals after busy periods are subtracted; and
- selectable minimum-duration candidate slots with a typed booking URL.

The service loads weekly rules and governed amenities with prefetches, then
loads all overlapping occupancy rows in one bounded range query. The same
`validate_reservation_interval` service generates candidate slots and validates
create/reschedule mutations, preventing calendar and write-path rules from
drifting.

## Time and interval policy

Schedules are wall-clock rules in the owning office's IANA timezone. Stored
occupancies and reservations are timezone-aware instants. Intervals are
half-open (`[start, end)`), so one reservation may begin exactly when another
buffered occupancy ends.

During a spring-forward gap, a nonexistent schedule boundary advances to the
first valid local minute. During a fall-back fold, a start boundary uses the
earlier instant and an end boundary uses the later instant. This maximizes the
represented office-open interval while keeping the policy deterministic. A
reservation must fit within one local-date schedule interval; it cannot cross a
local midnight boundary.

## Accessible interaction

Day and week views use a semantic table with room row headers and date column
headers. Every candidate is an ordinary keyboard-focusable link. List view uses
the same candidate-slot payload as the grid, providing equivalent selection
without dragging or pointer-only gestures. Loading, invalid-filter, no-office,
no-results, and no-valid-start states are announced or labelled for assistive
technology.
