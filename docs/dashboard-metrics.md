# Dashboard Metrics

The dashboard shows a different set of figures to an agent, a branch manager, a
regional leader, and a superadmin. Which figures, and what each one counts, is
reviewed data in `apps/web/metrics.py` — not a conditional tree in a view.

## The registry

`METRIC_DEFINITIONS` is an ordered tuple of `MetricDefinition` rows. Each row
carries everything needed to decide whether a user gets the card and what goes
on it:

| Field | What it decides |
| --- | --- |
| `key` | Stable camelCase identifier, unique across the registry, sent to the client |
| `label`, `group`, `order`, `format` | Display metadata |
| `all_permissions` | Django auth codenames the user must hold for the card |
| `scopes` | Which breadths the metric is defined at (`self`, `office`, `region`, `company`) |
| `source_module` | Domain module the calculator reads |
| `calculator` | `(MetricContext) -> MetricValue` |
| `definition` | How the figure is calculated, in prose |
| `drill_down` | Route the card links to, or `None` |
| `unavailable_behavior` | `mark` or `omit` when the source module is not connected |

`_validate_registry()` runs at import and raises on a duplicate key, an unknown
group, scope, or source module, a missing calculation definition, or a
drill-down that is not guarded. A malformed row fails the process, not a
request.

## Selection

`select_metrics(user)` returns the entitled rows in registry order:

1. **Effective access, not role names.** Permissions and scope come from
   `apps.user.services.role_assignments.get_effective_access`, so a revoked,
   expired, or not-yet-started assignment drops its metrics on the next request.
2. **Scope.** `resolve_scope` returns the single broadest level the user reads
   team aggregates at — `company` for a superuser or a company-wide assignment,
   then `region`, then `office`, then `self`. A metric is in scope when it is a
   self-scope metric (always) or its `scopes` contains the resolved level.
3. **Permissions.** Every listed permission must be held. Superusers pass.

Self-scope metrics are never gated on breadth: everyone reads their own book of
business, so gaining a management role adds team cards without removing agent
ones. That is the "no downgrade" half of multi-role resolution. The other half
is determinism — the registry is a fixed ordered tuple with one row per key, so
a union of role entitlements can never duplicate a card or reorder the page.

An agent whose own role assignment is office-scoped has office *reach* but holds
no team permission, so no team figure is selected. The payload then reports the
scope as `self`, because labelling that dashboard with a branch name would
misdescribe every number on it.

## Selection is not protection

Hiding a card is a courtesy. Two things make it real:

- **Drill-downs.** Every metric with a `drill_down` points at a route whose
  `enforce_policy` entry requires at least the metric's own permissions.
  `assert_drill_down_is_guarded` enforces this at import and
  `test_every_drill_down_requires_at_least_the_metric_permissions` covers it.
  Removing a permission removes the card *and* 403s the page behind it.
- **Aggregates.** Calculators filter through
  `apps.web.authorization.scope_queryset_for_user_office`, which unions the
  user's region and office keys from their effective access. No office or owner
  identifier is ever accepted from the client.

Self-scope metrics have no drill-down yet: the agent transaction and task
destinations do not exist as permission-protected routes, and pointing a card at
the merely-authenticated `coming_soon` placeholder would break the invariant
above. They get one when those destinations ship with their own policy.

## Source module availability

`SOURCE_MODULE_AVAILABILITY` records which domain modules exist. Today only
`user_directory` does; transactions, commissions, tasks, leads, contracts,
compliance, inventory, and reservations are registered but not connected.

A metric backed by an unconnected module is **marked unavailable** — the card
appears with `value: null` and a reason, so a leader can tell "not measured yet"
from "zero". Its calculator is never called. Flip the flag to `True` in the same
commit that ships the module's models and replaces `pending_source` with a real
calculator; `test_available_module_flags_stay_in_step_with_the_registry` fails if
a module is marked available while a metric still points at `pending_source`.

`unavailable_behavior = "omit"` drops the metric from the payload entirely.
Reserve it for figures that would mislead by their mere presence; no production
row uses it today.

## States the page can show

| State | How it appears | Who decides |
| --- | --- | --- |
| Measured value, including **zero** | `availability: available`, formatted `value` (e.g. `"0"`), optional `rawValue` | Calculator ran |
| **Unavailable** | `availability: unavailable`, `value: null`, `unavailableReason` | Source module flag is off |
| **Loading** | Skeleton cards | Inertia `<Deferred>` fallback for the `metrics` prop |
| **Permission withheld** | Card absent from the payload | `select_metrics` — never a visible placeholder |
| **Stale** | Auth-staleness banner on the dashboard shell | Effective access changed mid-session; metrics themselves are not cached |

Every metric carries `asOf` (ISO, server clock for that calculation). The
performance section shows one quiet "As of …" line from that stamp. There is no
per-card stale mark: the metrics widget is uncached and recomputed each request.

## Calculation definitions

Every row's `definition` is the contract for what its number means. The
non-obvious ones:

- **Windows.** "New agents" and "new leads" use a trailing 30 days computed as
  duration arithmetic (`now - timedelta(days=30)`), which is DST-safe.
  "Upcoming closings" looks 30 days forward.
- **Year to date.** `year_to_date_start` returns midnight on 1 January of the
  *local* calendar year (`settings.TIME_ZONE`), not of the UTC year. In
  `America/New_York` that is 05:00 UTC, and commission credited on 1 January
  local counts toward the right year.
- **Due today.** `end_of_local_day` is the exclusive upper bound for follow-ups,
  again in the local calendar day.
- **Room utilization.** `utilization_ratio(booked, bookable)` is booked
  room-minutes over bookable room-minutes. The denominator counts published open
  hours only, so closed days never inflate it. A non-positive denominator returns
  `None` — a window with no bookable minutes is *unmeasured*, and reporting 0%
  would read as "nobody used the rooms". The ratio is not clamped: above 1.0
  means rooms were double-booked, which is a finding rather than an artefact.
- **No double counting.** Aggregates are single querysets filtered by an OR'd
  `Q` over foreign keys, so a user whose region and office scopes overlap still
  counts each record once.

## Adding a metric

1. Add a `MetricDefinition` row. Pick an existing group or add one to
   `METRIC_GROUPS`.
2. Give it the permissions it needs. If none of the existing codenames fit, add
   one to `DashboardMetricPermission` in `apps/web/models.py` with a migration
   that creates it and grants it to the right role groups.
3. Point `drill_down` at a route whose policy already requires those
   permissions, or leave it `None`.
4. Write the calculator — scope every queryset through the shared helper — and
   write its `definition`.
5. Extend the matrix in `apps/web/tests/test_dashboard_metrics.py`: the expected
   key set per fixture, plus a scope-leakage test for the new aggregate.

No conditional in a view needs editing for any of this.

## Payload

`dashboard_metrics(user)` returns the deferred `metrics` prop for the Dashboard
page:

```json
{
  "scope": { "level": "office", "label": "Fairfax VA" },
  "groups": [
    {
      "key": "teamOversight",
      "title": "Team oversight",
      "description": "People and compliance in my scope",
      "metrics": [
        {
          "key": "teamNewAgents",
          "label": "New agents",
          "format": "count",
          "scopeLevel": "office",
          "definition": "Active users whose office is inside …",
          "asOf": "2026-08-19T09:00:00-04:00",
          "availability": "available",
          "value": "4",
          "rawValue": 4,
          "unit": "count",
          "hint": "Joined in the last 30 days",
          "tone": "neutral",
          "trend": "up",
          "drillDown": { "href": "/operations/new-agents", "label": "View new agents" }
        }
      ]
    }
  ]
}
```

`value` is always pre-formatted by the shared helpers in `apps/web/metrics.py`
(`format_count`, `format_currency`, `format_percent`). The page never does
arithmetic on `rawValue`. `drillDown.href` is reversed on the server so the
destination stays in step with `urls.py` without the page holding a route name
it would have to widen `routes` typing to call.
`frontend/components/dashboard/MetricCards.tsx` renders whatever arrives and
makes no entitlement decision of its own.
