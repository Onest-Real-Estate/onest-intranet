# My Day

One chronological, timezone-correct agenda of everything the signed-in user is
due to do. Domain modules emit rows through a shared contract; the dashboard
merges, deduplicates, orders, and buckets them. It owns no calendar of its own
and stores nothing. Lives in `apps/web/my_day`.

## Contract

Each source returns `AgendaEvent` rows (`apps/web/my_day/contract.py`):

| Field | Role |
| --- | --- |
| `id` | Stable identifier for this obligation |
| `dedupe_key` | Collapses the same appointment arriving from two sources |
| `source` | Closed set — task, training, consultation, closing, meeting, room, inventory, Outlook |
| `title`, `location`, `context` | Display |
| `start_at` / `end_at` | Aware datetimes; `end_at` optional for an instant |
| `all_day` + `local_date` | An all-day row is a **date**, not an instant |
| `status` | `confirmed` or `tentative`; **`cancelled` cannot be constructed** |
| `visibility` | `normal`; **`private` cannot be constructed** |
| `priority` | Tie-breaker only — it never reorders a chronology |
| `cta_label` / `cta_href` | Server-reversed destination that re-authorizes |
| `source_module` / `source_record_*` | Provenance for tracing, never authorization |

### What the constructor refuses

Cancelled and private events raise in `__post_init__` rather than being filtered
downstream. Every source would otherwise have to remember to exclude them, and a
cancelled meeting that still renders is what this widget gets blamed for. The
same applies to naive datetimes — a row with no instant would sit wherever the
active timezone happened to put it — and to an all-day row with no date.

## Timezone rules

Everything derives from `dashboard.timeframes.user_timezone`, the same seam the
greeting and every other provider use, so the two halves of the page cannot
disagree. Labels are formatted **server-side**; the browser clock is never
consulted, and the component does no time formatting of its own.

- **All-day rows carry `local_date`.** Storing one as midnight and converting it
  is how "all day Friday" becomes "Thursday 11pm" for a reader one zone west.
  Their `start_at` is only ever a sort position within that date.
- **DST is covered by tests, not assumption.** On a spring-forward day the wall
  clock skips (1:30 a.m. → 3:30 a.m.) and on a fall-back day it repeats (two
  rows both reading 1:30 a.m.); in both cases the order is unchanged.
- **Midnight is a boundary, not a rounding.** 23:59 is today, 00:00 is tomorrow.

## Ordering and buckets

`ordering.build_agenda` sorts once, deduplicates, then splits into three lists:

1. `overdue` — past its moment, and therefore not still ahead
2. `today` — on the reader's current local date
3. `upcoming` — everything else inside the forward window (7 days)

**Past-due work never sorts into the future.** That is the reason for three
lists instead of one array: an agenda that files a missed 9am among tomorrow's
appointments has hidden the only row that needed action. The split is part of
the contract, not a presentation choice the client could undo.

Within a bucket the order is: date, all-day rows first, start time, then
priority, then id. Priority appears last on purpose — an agenda reordered by
importance is no longer an agenda.

An all-day row is overdue only once its whole date has passed. "All day today"
is not late at 9am, which a comparison against a synthesized midnight would
claim.

## Sources

`EVENT_SOURCE_DEFINITIONS` in `apps/web/my_day/registry.py`:

| Key | Status | What it emits |
| --- | --- | --- |
| `operational_task` | **Live** | Tasks assigned to the reader that carry a due date |
| `inventory` | **Live** | Capacity-consuming inventory reservations owned by the reader |
| `training`, `consultation`, `closing`, `meeting`, `room_booking` | Registered, dark | Nothing — each becomes available in the change that ships its module |
| `microsoft_calendar` | Registered, dark | Nothing |

A dark source has `available=False` and **no collector**, so it cannot be called
and cannot fabricate a row. Listing Microsoft Calendar is not a claim that
anything synchronizes: an empty agenda must never be readable as "Outlook says
you are free". The registry validates at import that no source claims to be
available without a collector.

### Operational tasks

Only tasks **with a due date** and **assigned to the reader** in `Open` or
`In progress`. A deadline is a time-bound obligation; an undated task is a queue
item and belongs in [Action Items](dashboard-action-items.md) instead. The two
widgets deliberately overlap for dated work and answer different questions —
"what must I act on" versus "what shape is my day". A blocked or waiting task is
not something its assignee can move, so it leaves the agenda.

A manager who can *see* forty tasks across three offices does not have forty
appointments: scope here is assignment, which is narrower than `for_reader`.

## Failure isolation

`collect_events` runs each available source in its own `try`. One raising source
is logged and skipped; every other source still renders. The client is told only
that a partial failure occurred — naming the source would tell the reader which
calendars they are subject to.

| Situation | Result |
| --- | --- |
| Some sources failed, rows exist | `ready` + `meta.partialFailure`; the card shows the rows *and* says the list may be incomplete |
| All sources failed, no rows | `unavailable`, `retryable=True` |
| No sources failed, no rows | `empty` — "Nothing scheduled" |

"Nothing scheduled" and "we could not look" are different sentences, and the
widget must never substitute the first for the second.

## Payload and cap

Widget prop `schedule`, contract version 1, feed cap **6** (registry). The cap
fills overdue and today before upcoming, so trimming can drop a distant
appointment but never a missed one. `total` stays uncapped so "1 of 9" is honest.

```json
{
  "dateLabel": "Monday, March 2",
  "timezone": "UTC",
  "overdue": [], "today": [], "upcoming": [],
  "total": 3,
  "viewAllHref": "/hub/inventory-reservations",
  "viewAllLabel": "View my reservations"
}
```

`viewAllHref` resolves in `registry._calendar_destination` to the agent's
inventory reservations list until the unified My Reservations page (#71) lands.

## Permissions

The widget carries no permission of its own — it shows the reader their own
obligations, and a person is always entitled to their own day. Every row's scope
is the **source's**, applied in the source's queryset before a row is built, and
every CTA points at a destination that authorizes again on arrival. A stale row
cannot widen access.
