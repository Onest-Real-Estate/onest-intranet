# Dashboard productionization — working log

Running handoff notes for the P1 issue "Convert the existing visual dashboard
prototype into the production personalized landing page". Updated as each phase
lands so another session can pick up mid-flight.

**Branch base:** `main` at `3b0a165` (P1 dashboard metrics registry merged).

---

## The problem

`apps/web/dashboard.py` returned hard-coded business records — four invented
transactions with `picsum.photos` images, invented announcements, a fake 72%
training ring, invented mortgage rates, three invented document names, and a
schedule with a hard-coded `"Aug 19"` date label. `Dashboard.tsx` rendered them
as if they were real. There was no way for a widget to say "I have no data
source yet" or "I failed", so every widget either lied or would have to 500.

## The shape of the fix

1. **Envelope contract.** Every deferred widget prop becomes a versioned
   envelope: `{status, version, generatedAt, data, emptyState, unavailable}`
   with `status` one of `ready | empty | unavailable`. A widget with no backing
   module returns `unavailable`; a widget that ran and found nothing returns
   `empty` with a next action; a widget whose provider raised returns
   `unavailable` with `retryable: true`.
2. **Composition layer.** `apps/web/dashboard/` package replaces the flat
   module: `contracts.py` (envelope), `registry.py` (widget rows: prop name,
   defer group, contract version, cache policy, feed cap, provider), and
   `providers.py` (the loaders). The view composes; it holds no ORM queries.
3. **Timezone-aware today.** Greeting and date move server-side, computed from
   the application timezone via a `user_timezone(user)` hook, instead of the
   browser clock.
4. **Resilient frontend.** A `WidgetPanel` renders the three states from the
   envelope, with a retry that does an Inertia partial reload of just that prop.

---

## Phase status

| Phase | What | State |
| --- | --- | --- |
| 1 | Backend: contracts, registry, providers, composer, greeting, view wiring | **done** |
| 2 | Backend tests: scope, timezone, empty, partial failure, query counts | pending |
| 3 | Frontend: types, `WidgetPanel`, widget components, Dashboard page | pending |
| 4 | Frontend tests: states, retry, source order, a11y | pending |
| 5 | Docs (`docs/dashboard.md`), full gate | pending |

---

## Phase 1 — backend composition layer (done)

`apps/web/dashboard.py` (flat module of fake payloads) became `apps/web/dashboard/`:

| File | Holds |
| --- | --- |
| `envelope.py` | `Widget`, `ProviderResult`, `WidgetEmptyState`, `WidgetUnavailable`, and the `ready()` / `empty()` / `unavailable()` builders |
| `providers.py` | `DashboardContext` + one loader per widget |
| `registry.py` | `WIDGET_DEFINITIONS`, `CachePolicy`, validation, `load_widget`, `deferred_widget_props` |
| `timeframes.py` | `user_timezone`, local day boundaries, `greeting_payload` |
| `sections.py` | `HUB_SECTIONS` (split out so `navigation.py` imports it without pulling in providers/ORM) |

### Widget registry as it stands

| key | prop | group | v | provider status today | feed cap | cache |
| --- | --- | --- | --- | --- | --- | --- |
| performance | `metrics` | metrics | 1 | ready / empty | — | none (sensitive) |
| quick_access | `quickApps` | pipeline | 1 | ready | 24 | per-user, 300s |
| announcements | `announcements` | pipeline | 1 | unavailable | — | none |
| active_transactions | `transactions` | pipeline | 1 | unavailable | 5 | none |
| training | `training` | pipeline | 1 | unavailable | — | none |
| my_day | `schedule` | widgets | 1 | unavailable | 6 | none |
| action_items | `actionItems` | widgets | 2 | ready / empty | 5 | none |
| market | `market` | widgets | 1 | unavailable | 4 | none |
| quick_documents | `documents` | widgets | 1 | unavailable | 5 | none |

### Decisions

- **Envelope, not bare payload.** `{status, version, generatedAt, data, emptyState, unavailable, meta}`.
  `status` distinguishes *ready* / *empty (with a next action)* / *unavailable*.
  `unavailable.retryable` separates "module not built" (false — offer a
  destination) from "provider raised" (true — offer a reload).
- **Failure containment lives in `load_widget`.** A raising provider is logged
  with `logger.exception` and returns a retryable envelope for its own prop
  only. The user-facing reason is a fixed generic string: exception text can
  carry query fragments and record ids, and this string renders in the browser.
- **Feed caps are enforced centrally** in `_apply_feed_limit`, not per provider,
  so a future provider cannot ship an unbounded feed by forgetting a slice.
  Truncation sets `meta.truncated`.
- **Cache safety is validated at import.** `user_specific=True` + `scope=shared`
  raises; a cached scope without a positive ttl raises; a ttl without a scope
  raises; every policy needs a written `rationale`. `widget_cache_key` puts the
  user pk *and* `authorization_version(access)` in per-user keys, so a role
  change invalidates. Transient failures are never cached.
- **Quick Access stays populated.** Lofty / SkySlope / Microsoft 365 / RPR
  are the brokerage's real vendor systems — reviewed configuration that changes
  by commit, not invented business records. Everything that was a fabricated
  *record* (transactions, announcements, documents, training %, mortgage rates,
  schedule) is now `unavailable`.
- **Greeting moved server-side** as a non-deferred `greeting` prop. It was
  computed from the browser clock, which disagreed with server-side date ranges.
  `user_timezone(user)` returns the application timezone today and is the single
  seam for a future per-user/office timezone field.
- **One access lookup per request.** `build_context` resolves `EffectiveAccess`
  once and every provider shares it.

### Files touched in phase 1

- added `apps/web/dashboard/{__init__,envelope,providers,registry,sections,timeframes}.py`
- deleted `apps/web/dashboard.py`
- `apps/web/views.py` — dashboard view is now `greeting_payload` + `deferred_widget_props`
- `apps/web/navigation.py` — imports `HUB_SECTIONS` from `dashboard.sections`
- `apps/web/tests/test_web.py`, `apps/web/tests/test_dashboard_metrics.py` — unwrap the envelope

Backend suite: 256 passed. `ruff`, `ty` clean.

## Open questions / follow-ups

- The production dashboard now shows: greeting, **performance metrics**
  (``P1-022``), Quick Access, **Action Items** (``P1-027`` — profile-backed
  sources today; other domains register as they ship), and remaining feed
  widgets in an explicit unavailable state. See ``docs/dashboard-action-items.md``.
  Flagged for the product call.
- No per-user timezone field exists. `user_timezone()` returns the application
  timezone; if per-user timezones are wanted, that function plus a migration is
  the whole change.
