# Dashboard composition and widget contracts

The authenticated dashboard is the personalized landing page for the hub. Its
first response contains the server-local greeting and layout shell; every data
widget arrives independently through an Inertia deferred prop. A missing module
or failing provider therefore cannot turn the whole landing page into an error.

## Contract

Every deferred prop is a versioned envelope, never a bare payload:

```json
{
  "status": "ready | empty | unavailable",
  "version": 1,
  "generatedAt": "2026-08-19T09:00:00-04:00",
  "data": null,
  "emptyState": null,
  "unavailable": null,
  "meta": {}
}
```

- `ready` carries non-null `data`.
- `empty` means the provider ran successfully but found nothing. It carries an
  `emptyState` with a title, description, and optional next action.
- `unavailable` means no trustworthy answer exists. A provider exception sets
  `retryable: true`; a module that has not shipped sets `retryable: false` and
  may link to its future hub destination.

Exception messages never cross the browser boundary. The composer logs the
widget key, prop, and user id, then returns a fixed generic reason. Change a
widget's `version` whenever the shape of its `data` changes.

## Composition layers

The dashboard view only combines `greeting_payload()` with
`deferred_widget_props()`. Responsibilities live under `apps/web/dashboard/`:

| File | Responsibility |
| --- | --- |
| `envelope.py` | Envelope and provider-result types plus state builders |
| `providers.py` | One scoped loader per widget |
| `registry.py` | Prop names, defer groups, versions, feed caps, cache policy, failure containment |
| `timeframes.py` | User/application timezone, greeting, and local day boundaries |
| `sections.py` | Shared hub section labels without importing ORM providers |

`build_context()` resolves the signed-in user's `EffectiveAccess`. Deferred
closures memoize that context for the response, and every provider receives it;
providers must not accept office, owner, region, or user ids from query
parameters. Shared queryset scope helpers accept the pre-resolved access object
where available so authorization is not recalculated inside a feed.

## Registry and freshness

| Widget | Prop | Group | Feed cap | Cache policy |
| --- | --- | --- | ---: | --- |
| Performance | `metrics` | `metrics` | — | None; sensitive, scope-derived totals |
| Quick access | `quickApps` | `pipeline` | 8 | Per user for 300 seconds, keyed by the administered configuration stamp — see `docs/quick-access.md` |
| Announcements | `announcements` | `pipeline` | — | None; future audience targeting is user-specific |
| Active transactions | `transactions` | `pipeline` | 5 | None; owned records must reflect the last write |
| Training | `training` | `pipeline` | — | None; per-user completion |
| My day | `schedule` | `widgets` | 6 | None; stale calendar data is operationally risky |

My Day aggregates every registered calendar source into one bucketed agenda —
see [dashboard-my-day.md](dashboard-my-day.md) for the provider contract, the
timezone and DST rules, and how a failing source is isolated.
| Action items | `actionItems` | `widgets` | 5 | None; assigned work must reflect the last write |
| Market | `market` | `widgets` | 4 | None until a real feed defines its freshness contract |
| Quick documents | `documents` | `widgets` | 5 | None; visibility is role- and office-scoped |

Action Items is live via `apps.web.action_items` (contract version 2). See
`docs/dashboard-action-items.md` for the source registry, ordering, and CTA
rules. Profile-backed items ship today; other domains register collectors as
their modules land.

Registry validation fails at import for duplicate keys/props, invalid versions
or feed limits, cache policies without a rationale, and any shared cache on a
user-specific widget. Per-user cache keys include user id and effective-access
version. A widget whose source is administered data may also declare a
`cache_version` callable; its stamp joins the key, so one write retires every
cached entry instead of leaving an unbounded set of per-user keys to delete.
Retryable failures are never cached. List feed caps are applied by the
composer and set `meta.truncated` when rows are removed.

## Frontend behavior

`DashboardWidget<T>` in `frontend/types/index.ts` mirrors the envelope as a
discriminated union. `WidgetPanel` delegates `ready` data to the established
widget component and owns the other states:

- empty states explain what will appear and offer the next useful action;
- transient failures use an alert and retry only their own prop through an
  Inertia partial reload.

Unbuilt modules never reach `WidgetPanel`. A widget the registry marks
`backed: false`, or whose provider answers `unavailable` with
`retryable: false`, is moved out of the grid by `lib/dashboard/layout.ts` and
stated once in the `PendingModules` band at the foot of the page — named, with
the server's reason where it authored one, and linking onward where a
destination exists. `WidgetPanel` still renders the unavailable envelope, for
the retryable case and for anything that reaches it another way.

Skeletons remain the `Deferred` fallbacks; a deferred prop that has not landed
is not yet known to be unbacked, so it keeps its slot and its skeleton. The
role-defining workflow leads the working grid in both DOM and visual order,
followed by the daily and utility panels. That keeps mobile, desktop, keyboard,
and screen-reader reading order in agreement. Widths, and only widths, are
computed: see "Rows, not columns" in `docs/dashboard-profiles.md`.

The greeting and date are server props. `user_timezone()` currently returns the
application timezone because no user or office timezone field exists. Add that
configured field at this seam rather than deriving a timezone from an address.

## Connected modules

Fourteen of the sixteen registered widgets read a live source. Each provider is
a *view* of an existing operations surface and reuses that surface's own
visibility gate rather than re-deriving one, so a panel can never show a row its
destination would deny:

| Widget | Source | Gate it reuses |
| --- | --- | --- |
| `performance` | `web.metrics` registry | per-metric permission + scope |
| `quick_access` | administered Quick Access links | audience resolution |
| `announcements` | `announcements.audience` | the feed's own predicate |
| `training` | `training` progress | per-user completion |
| `my_day` | reservations agenda | the reader's own bookings |
| `action_items` | action-item registry | per-source permission |
| `overdue_inventory` | `inventory.overdue` | `managed_reservation_queryset` |
| `support_queue` | `it_support.SupportTicket` | `TicketQuerySet.for_reader` |
| `team_tasks` | `operational_tasks.OperationalTask` | `TaskQuerySet.for_reader` |
| `quick_documents` | `user.OfficeResource` | `effective_resources` |
| `agent_onboarding` | `user.UserOnboardingCase` | `new_agent_queryset` |
| `room_utilization` | `reservations.Occupancy` | `manager_spaces` |
| `contracts_awaiting_signature` | `contract.AgentContract` | `scoped_contract_queryset` |
| `feedback_signals` | `feedback.FeedbackTicket` | `FeedbackQuerySet.for_reader` |

Two rules the connected set follows:

- **The widget's declared permission is the destination's permission.** A panel
  admitted by a different grant links every row into a 403. `team_tasks` and
  `support_queue` previously listed `web.view_platform_tasks`, which is
  sanitized Celery job status and a different module entirely; both now ask for
  the grant their own page enforces.
- **An empty scope is `empty`, never `unavailable`.** "Nothing open" and "this
  module does not exist" are different facts, and only the second belongs in the
  closing "Not connected yet" band.

**Still unconnected**, and honestly reported in the closing band rather than
faked:

- `active_transactions` and `market` have registered providers that answer
  `unavailable`: the first needs a transactions domain, the second an external
  market feed.
- `closing_pipeline` and `compliance_exceptions` have no domain model. A
  compliance "exception" needs defining before it can be counted.
- `operational_activity` has the data — `audit.AuditEvent` carries office and
  region stable keys — but `activity_timeline` is a per-record JSON endpoint,
  not a browsable page, so there is nowhere for the panel to lead. Connecting it
  means building that page first.

**Known gap.** No catalogued role holds `web.triage_it_support`, so the IT
support queue — page and panel alike — shows even an IT Support reader only the
requests they raised. That is a role-bundle gap, not a widget behaviour; the
panel deliberately mirrors the page rather than inventing wider reach.

## Adding a production provider

1. Implement the loader in `providers.py` using only `DashboardContext` and
   shared authorization scope helpers.
2. Return `ready(data)`, or `empty(...)` when a successful query has no rows.
3. Set an explicit feed cap and reviewed cache rationale in `registry.py`.
4. Update the matching TypeScript data type and bump the contract version when
   its shape changes.
5. Add scope-isolation, empty, failure, feed-size, query-count, component-state,
   and accessibility coverage.

The regression suite pins the production first-paint shell at eight database
queries, proves deferred providers do not run during that response, bounds the
live performance provider at two queries after context construction, and
asserts a multi-widget partial response resolves effective access once.
