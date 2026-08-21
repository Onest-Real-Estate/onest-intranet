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
- unbuilt modules state that they are not connected and link onward when a
  destination exists;
- transient failures use an alert and retry only their own prop through an
  Inertia partial reload.

Skeletons remain the `Deferred` fallbacks. The role-defining workflow leads the
working grid in both DOM and visual order, followed by the daily and utility
rail. That keeps mobile, desktop, keyboard, and screen-reader reading order in
agreement.

The greeting and date are server props. `user_timezone()` currently returns the
application timezone because no user or office timezone field exists. Add that
configured field at this seam rather than deriving a timezone from an address.

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
