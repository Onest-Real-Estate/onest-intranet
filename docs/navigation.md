# Hub navigation

The authenticated shell has one version-controlled navigation registry:
`frontend/lib/hub-nav.ts`. `HubLayout` resolves that registry once and renders the
same result in the desktop rail and mobile drawer. Do not add a role check or a
second menu array to a component: relevance is registry data (see
[Role relevance](#role-relevance)) and authorization is permissions.

## Adding or changing a destination

Each `HUB_NAV_REGISTRY` item declares a stable key and label, a generated Django
route name and URL, its icon, group and numeric order, authorization mode,
effective-permission requirements, feature key when applicable, and explicit
active-route matching. Administrative children also reference one of the reviewed
collapsible sections in `HUB_NAV_SECTIONS`.

1. Register and protect the Django route through `ROUTE_POLICIES`. A hidden menu
   item is never an authorization boundary.
2. If a `urls.py` changed, run `pnpm run routes:generate` and commit the generated
   `frontend/types/routes.ts`.
3. Add the item to `HUB_NAV_REGISTRY` using `routes.<name>()`; never construct a URL
   from strings.
4. Set an explicit feature key for a module that can be unavailable. Add that key
   to the backend source in `apps/web/navigation.py` or
   `apps/web/operations.py`. `true` marks the live module, an explicitly
   registered `false` value renders the authorized placeholder with a “Soon”
   marker, and missing or unknown keys hide the item.
5. Add registry, permission, active-match, and route-denial tests. A
   `permission-protected` item must declare at least one `any` or `all`
   requirement matching its backend route policy.

`resolveHubNav` uses the effective permission union supplied on the authenticated
user prop. It never authorizes from a role, and it never reads a role display
name. It filters permission and feature requirements, drops destinations the
reader's roles make irrelevant, removes items that lack required user context,
deduplicates by stable key and destination, sorts by configured order, and removes
empty groups. This makes overlapping Agent, Branch, Regional, and Brokerage
assignments additive without rendering duplicate links.

## Role relevance

Permissions decide what a reader *may* reach. They do not decide what is worth
putting in front of them. "My contract" and "Agent transactions" describe a book
of business; to an accountant, a coordinator, or IT support they are permanent
dead ends in the rail, and no permission expresses that because the destinations
are open to every signed-in colleague.

An item may therefore declare `roles: [...]` — the stable role codes from
`apps/user/roles.py` the destination is relevant to. Absent means everyone. Four
rules keep it from becoming a second, weaker authorization system:

1. **It only ever hides.** A role list never reveals an entry, and a hidden route
   is exactly as reachable as it was before. Route policy is unchanged.
2. **It is legal only on items that require no permissions.** Where a permission
   exists it already expresses relevance; filtering on top of it would hide a
   destination somebody was deliberately granted.
   `validateHubNavRegistry` reports `permission-protected item declares roles`.
3. **Codes must exist** in the role catalog, and an empty list is rejected — that
   is a deletion written as a filter.
4. **Superusers are exempt**, so a platform administrator can still reach every
   destination from the rail.

Someone holding several roles keeps the union, so a branch manager who also
carries listings still sees the agent entries. Today three items use it:
`my-contract` and `agent-transactions` (`PRODUCING_ROLES`) and
`marketing-resources` (`MARKETING_ROLES`). Changing who counts is an edit to
those two arrays.

## Availability, loading, and revocation

Feature availability is explicit backend configuration, not an environment value
interpreted by the browser. An explicit false state advertises only a registered,
protected placeholder to an otherwise authorized user; it can never grant the
destination permission. Administrative feature keys are shared only after their
effective permission succeeds. Permission and feature props arrive in the initial
Inertia response, so the shell does not render an optimistic menu while
authorization data loads. A subsequent Inertia response recomputes the resolver;
revoked items and emptied groups disappear immediately.

`marketing-resources` and `admin-marketing-resources` are **live**
(`HUB_FEATURES` / `OPERATIONS_FEATURES` both `True`) — not Coming Soon stubs.
They resolve to the real library and operations workspace behind audience and
`web.manage_marketing_resources` respectively.

`documents-forms` and `admin-documents` are **live** the same way. The
library is audience-scoped; the operations workspace is
`web.manage_documents`, with publication and retirement on separate grants.

Unknown permission names, absent permission data, missing feature keys, and missing
required office context fail closed. A current deep link can therefore have no
visible parent after a revocation; the route still returns the backend's 403 page.

## Nested state and accessibility

Administrative subsections use native buttons with `aria-expanded` and
`aria-controls`. Their open keys are stored under a registry-versioned local
storage key. Parsing accepts only known subsection keys, ignores stale keys, and
falls back safely when storage is unavailable or corrupt. The subsection that
contains the current route is always exposed. The collapsed icon rail keeps all
authorized icons available and labels them with tooltips.

Navigation uses a labelled `nav`, list markup, visible keyboard focus, and
`aria-current="page"`. Long labels truncate only visually, mobile uses the same
full labels, and reduced-motion preferences disable the small chevron transition.

## Analytics and badges

Navigation emits no analytics today. Any future event must be reviewed and limited
to stable, non-sensitive configuration metadata such as item key, route name,
group key, and interaction type. Do not send labels, URLs with parameters, user or
office identifiers, permission names, counts, or badge values.

Badges are not part of the registry. A future count endpoint must enforce the same
permission and effective office scope as its destination before the count can be
shared or rendered.
