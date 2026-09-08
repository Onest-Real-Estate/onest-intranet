# Dashboard profiles

Eleven roles read the same `/dashboard` route and see eleven different pages.
Which widgets appear, in which order, and in which column is **data** — a
profile in `frontend/lib/dashboard/profiles.ts` composed from the allowlisted
registry in `frontend/lib/dashboard/widget-registry.ts`. There is no per-role
page component and no role conditional in `frontend/pages/Dashboard.tsx`.

> **Scope of what is built.** This is the frontend half. The `DashboardProfile`
> / `DashboardProfileAssignment` models, the assignment admin screen, and the
> server-side providers for the administrative widgets are not implemented yet.
> The page already reads the props those will fill; until they exist the
> administrative widgets render as **not connected** (see
> [Unbacked widgets](#unbacked-widgets)). The dashboard never fills the gap
> with an invented figure.

## The widget registry

`DASHBOARD_WIDGETS` is an ordered array of `DashboardWidgetDefinition` rows.
Each row carries everything needed to decide whether the card is laid out and
where:

| Field | What it decides |
| --- | --- |
| `id` | Stable identifier. The **only** thing a profile stores |
| `title` | Panel heading |
| `prop` | Inertia prop carrying the envelope, and the `router.reload({ only })` target |
| `backed` | Whether a server provider fills `prop` yet |
| `permissions` | `PermissionCheck` the reader must satisfy for the card |
| `deniedBehavior` | `omit` (drop silently) or `withhold` (render a restricted placeholder) |
| `column` | `wide`, `main`, or `rail` |
| `span` | Twelfths claimed in the `wide` band, so two widgets can share the top row |
| `scopes` | Breadths the widget is meaningful at |

A profile stores ids and nothing else — no component name, no import path, no
query, no expression. An id that is not in the registry, or not a `case` in
`DashboardWidgetSlot`, renders nothing at all. That is the allowlist.

### The top of the page

Every profile leads with `performance` — the four-figure metrics row is the
first thing after the greeting, before any other widget. It is followed by the
same adjacent pair in every profile: `announcements` (span 8) and `quickAccess`
(span 4), sharing one twelve-column row. Brokerage news is the one thing
everybody is meant to have read, and a panel two columns down in a rail is a
panel nobody reads.

The news band renders one story at a time as a full-bleed hero — the picture
fills the card and the headline sits over it on a scrim built from the page's
own background tokens, so it reads in both themes. The track is moved with a
transform rather than by scrolling a snap container: a programmatic scroll
inside `scroll-snap-type: mandatory` is not dependable, because Chrome re-snaps
to the slide it is already on the moment the animation starts, and a profile
with smooth scrolling switched off drops the scroll entirely. It never advances
on its own.

Three consequences the tests pin down, because all are easy to break by
reordering a profile:

- Every profile's list starts `performance`, `announcements`, `quickAccess`,
  in that order. A widget between the news pair wraps the band into three rows.
- Everything stacks below `xl`; `span` is only honored once there is a
  twelve-column grid to divide.
- The metrics row shows every measured figure the reader is entitled to, with
  no cap and nothing folded away (see below).

### Figures without a data source

`MetricCards` renders only figures that actually have a data source. A
brokerage-wide leader is entitled to a dozen metrics and most have no provider
yet; a figure with no source is not a number anyone can act on, so it is left
out entirely rather than counted, promised behind a disclosure, or shown as a
placeholder dash. When a reader has no measured figures at all the row says so
in a sentence. Which figures a reader is *entitled* to remains entirely the
server's decision.

## Resolution

`resolveDashboard(user, assignment, remembered)` applies a fixed precedence:

1. **Explicit user assignment** — `assignment.assignedProfileId`.
2. **Designated primary role** — `assignment.primaryRoleCode`.
3. **Highest-priority effective role** — `user.roles` arrives ranked by the
   server, and `authorizedProfiles` re-sorts by catalog priority, so the same
   role set always produces the same answer regardless of array order.
4. **Office or region assignment** — `assignment.scopeProfileId`.
5. **Authenticated fallback** — the `authenticated` profile, which every signed-in
   colleague gets.

A remembered reader selection sits above all five, but only while it still names
a profile the reader is authorized for. Every rule above is filtered through
`authorizedProfiles`: an assignment naming a profile whose role the reader has
lost falls through to the next rule rather than granting a presentation their
roles do not cover. That is how revocation and expiry take effect without the
client tracking validity windows.

`assignment` is absent today, so resolution starts at rule 3.

### Resolution is not authorization

Switching or being assigned a dashboard **adds no Django permission and widens
no data scope**. Two things make that true rather than aspirational:

- `resolveWidgets` filters every widget through the reader's own
  `user.permissions`, whichever profile selected it. Inspecting the System Admin
  presentation as a realtor yields only the widgets the realtor could already
  see.
- Each widget's provider re-applies the same permissions and the reader's
  effective scope server-side, and every drill-down is guarded by its own
  policy. The client is never the authority.

`resolveWidgets` also deduplicates by id, so a multi-role reader — or a
mis-authored profile — can never put the same aggregate on the page twice.

## Widget states

Each widget owns its own lifecycle: its own `<Deferred>` fallback, its own
envelope, its own retry. One failing provider takes down one card.

| State | Where it comes from | What the reader sees |
| --- | --- | --- |
| Loading | Inertia `<Deferred>` fallback | The widget's own skeleton |
| Ready | `status: "ready"` | The widget |
| Zero | `status: "empty"` | An instructive empty state and the next action |
| Unavailable | `status: "unavailable"`, `retryable: false` | "Not connected yet" plus where the feature will live |
| Error | `status: "unavailable"`, `retryable: true` | "Couldn't load this widget" and a retry of that prop alone |
| Stale | `shell.authorizationVersion` changed since load | A quiet mark on each panel, one refresh banner on the page |
| Withheld | Permission missing and `deniedBehavior: "withhold"` | A restricted placeholder naming no figure and no codename |

"Zero" and "unavailable" are deliberately distinct: a branch with no compliance
exceptions is good news, and a compliance module that is not connected is not
news at all.

## Scope

`DashboardScopeSelector` lists only the breadths the server put in
`scope.options`, and the selected key is sent back for **server-side
revalidation** on every request. No office or region primary key is ever
accepted from the client, and holding a key widens nothing. The client never
infers a scope level from what it can see: labelling an office figure as a
company one would misdescribe every number under it.

With one option there is nothing to choose, so the page shows the scope as a
plain label rather than a control that does nothing.

## Unbacked widgets

A widget whose provider has not shipped has no prop to read. `envelope()` in
`DashboardWidgetSlot` synthesises an `unavailable` envelope for it, so the
panel says *Not connected yet* in the same vocabulary as a module that is
genuinely offline. The rules:

- A `ready` server envelope always wins, whatever the registry says, so real
  data can never end up hidden behind the placeholder because someone forgot to
  flip `backed`. Otherwise a `backed: false` widget renders as not connected,
  and a backed one shows whatever the provider said — including empty and
  failed.
- **No fixtures.** The dashboard puts no figure on the page that no provider
  produced. A reader cannot tell an illustrative 42 from a real one once they
  have scrolled past the caveat that said so, and a screenshot of the page
  outlives the caveat entirely.
- The scope selector is absent until the server sends a `scope` prop, for the
  same reason: offering breadths the reader may not hold mislabels every figure
  under it.
- Registering a provider means flipping `backed` to `true` in the same commit,
  at which point the panel starts reading real data with no other change.

## Adding a role's dashboard

1. Add the role to `apps/user/roles.py` and `frontend/lib/roles.ts` as usual.
2. Add a `DashboardProfile` row: id, label, description, its `roleCodes`, the
   catalog `priority`, and an ordered list of registry widget ids. Reuse an
   existing profile's `roleCodes` instead if the presentation is the same.
3. `resolve.test.ts` asserts that every catalogued role has a profile, that a
   role code is claimed by exactly one profile, and that no profile lists a
   widget twice — a missing row fails the suite rather than shipping a blank
   dashboard.

## Adding a widget

1. Add a `DashboardWidgetDefinition` row with its permissions, column, and
   `backed: false`.
2. Add its prop to `DashboardWidgetProp` and to `DashboardPageProps` in
   `frontend/types/index.ts`.
3. Add a `case` to `DashboardWidgetSlot`, routing the prop through
   `envelope()`. If the shape is a staged funnel, a
   work queue, a utilization meter, or an activity feed, reuse `StageFunnel`,
   `WorkQueue`, `UtilizationMeter`, or `ActivityFeed` rather than writing a
   fifth presentation.
4. List it in the profiles that should show it.
5. Ship a provider in `apps/web/dashboard/providers.py` and flip `backed`.
