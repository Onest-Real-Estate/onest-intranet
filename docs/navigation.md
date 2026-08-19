# Hub navigation

The authenticated shell has one version-controlled navigation registry:
`frontend/lib/hub-nav.ts`. `HubLayout` resolves that registry once and renders the
same result in the desktop rail and mobile drawer. Do not add role-name checks or a
second menu array to a component.

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
user prop. It does not inspect role display names. It filters permission and
feature requirements, removes items that lack required user context, deduplicates
by stable key and destination, sorts by configured order, and removes empty
groups. This makes overlapping Agent, Branch, Regional, and Brokerage assignments
additive without rendering duplicate links.

## Availability, loading, and revocation

Feature availability is explicit backend configuration, not an environment value
interpreted by the browser. An explicit false state advertises only a registered,
protected placeholder to an otherwise authorized user; it can never grant the
destination permission. Administrative feature keys are shared only after their
effective permission succeeds. Permission and feature props arrive in the initial
Inertia response, so the shell does not render an optimistic menu while
authorization data loads. A subsequent Inertia response recomputes the resolver;
revoked items and emptied groups disappear immediately.

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
