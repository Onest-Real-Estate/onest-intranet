# Dashboard Action Items

The Action Items widget is a prioritized queue of work the signed-in user must
act on. Domain modules emit rows through a shared contract; the dashboard
merges, deduplicates, and orders them. It does **not** store completion state.

## Contract

Each source returns `ActionItem` rows (`apps/web/action_items/contract.py`):

| Field | Role |
| --- | --- |
| `id` | Stable identifier for the required action |
| `dedupe_key` | Collapses duplicate signals for the same action to one row |
| `title`, `type`, `priority` | Display and ordering inputs |
| `due_at` | Optional deadline; overdue when before "now" |
| `state` | Always `open` on the wire — completed work is omitted |
| `source_module` / `source_record_*` | Provenance for observability, not client authorization |
| `context` | Supporting subtitle (property, missing fields, …) |
| `cta_label` / `cta_href` | Server-reversed destination for the resolution workflow |
| `assignee_id` | User the item is actionable for |

Completion is **derived from the source record**. A provider that would emit a
completed, cancelled, future-not-actionable, or out-of-scope item must omit it.
Dismissing or ignoring a dashboard row never marks a legal, compliance, or
other domain item complete.

## Ordering

Deterministic sort (`apps/web/action_items/ordering.py`):

1. Overdue first (`due_at < now`)
2. Priority ascending (critical → low)
3. Due time ascending (undated after dated peers at the same priority)
4. Stable `id` tie-breaker

Then dedupe by `dedupe_key`, keeping the first survivor after that sort.

## Sources

`ACTION_SOURCE_DEFINITIONS` in `apps/web/action_items/registry.py` is the
registry. Today:

| Key | Status | What it emits |
| --- | --- | --- |
| `profile` | Live | Incomplete professional profile; expired or soon-to-expire licence |
| `compliance` | Live | Open mandatory policy acknowledgements (pending high, overdue critical) |

Contract, inventory, transaction, document/checklist, training, lead,
commission, and remaining domain modules register collectors here as they
ship. An `available=False` row is skipped and never invents placeholders.

## Permissions and stale CTAs

- Collectors receive only `ActionSourceContext` (user, effective access, now).
  No client-supplied office or owner id.
- Items are limited to work assigned to or legitimately actionable by the
  current user.
- The CTA points at a destination that enforces its own policy again (e.g.
  `profile`). A stale dashboard row cannot bypass that check.
- There is no "mark complete" endpoint on the dashboard.

## Payload and feed cap

Dashboard widget (`actionItems`, contract version **2**):

```json
{
  "total": 7,
  "items": [ /* up to feed_limit (5) */ ],
  "viewAllHref": "/dashboard/action-items"
}
```

The composer caps `items` and sets `meta.truncated` when rows are dropped.
`total` stays the uncapped actionable count. `viewAllHref` opens the full
filtered queue page, which re-runs collectors with no feed cap.

`meta.partialFailure` is set when a source raised; the reason stays in server
logs. The client never receives source keys or hidden record identifiers from
that failure.

## Frontend

`ActionItems` renders linked rows with priority/overdue **text and** tone via
`StatusBadge`. No checkbox: local dismiss would invent a second truth. Empty
and unavailable states stay on `WidgetPanel`.

## Adding a source

1. Implement `collect_*(ActionSourceContext) -> list[ActionItem]`.
2. Append an `ActionSourceDefinition` to `ACTION_SOURCE_DEFINITIONS`.
3. Cover ordering, exclusion rules, scope, and stale CTA destination policy.
4. Do not put domain rules in `providers.action_items` or the React page.
