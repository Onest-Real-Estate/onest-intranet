# Quick Create: the global action menu

One code-owned registry decides what a person can start from anywhere in the
hub. `apps/web/quick_actions.py` holds it; the header button in
`frontend/components/QuickCreateMenu.tsx` renders it.

## The registry

Each entry is a frozen `QuickAction`:

| Field | Meaning |
| --- | --- |
| `key` | Stable identity, used in tests and telemetry |
| `label` / `description` | What the menu shows |
| `group` | Section heading; ordered by `GROUP_ORDER` |
| `icon` | Lucide name, mapped to a component client-side |
| `permission` | Reviewed catalog codename the actor must hold |
| `route_name` / `route_args` | Destination, reversed at serialization |
| `feature` | Key from `HUB_FEATURES` that must be live |
| `scopes` | Scope shapes the action makes sense in |

### Destinations are route names, never URLs

A destination is a **name**, resolved through Django's `reverse()` when the
payload is built. Nothing stores a path, and nothing stores a callable.

That is the security shape of the module rather than a style preference. An
entry cannot name a path that does not exist, cannot be pointed at another
origin, and cannot be edited into an executable by anybody with database
access — adding an action is a reviewed code change, the same bar the
navigation registry and the permission catalog already hold. A renamed route
makes the entry *unreversible*, and it is dropped rather than serialized as a
dead link; `test_quick_actions.py` asserts every entry reverses, so that never
fires silently.

## Filtering happens before serialization

`quick_actions_for()` applies three independent gates — permission, feature,
scope — and returns only what survives. An unavailable action is **absent from
the props**, not hidden by CSS.

That is a disclosure control, not a convenience: the set of actions somebody
can see is itself a description of what they are allowed to do, so a branch
administrator should not be able to read "New user" out of the page source.

**Hiding is still never the enforcement.** Every destination keeps its own
`enforce_policy` entry, and the tests navigate directly to actions the menu
withheld to prove the endpoint refuses them anyway.

### Scope shapes

`actor_scopes()` turns an `EffectiveAccess` into the shapes a grant actually
has. A wider grant fills in the narrower ones — company-wide implies region and
office, because a brokerage administrator can obviously act on one office — so
callers do not each have to remember that. `any` is always present: it marks
"no particular scope required", not a scope anybody holds.

### Multi-role users

The registry is consulted **once**, not once per role, so two roles granting the
same permission produce one entry. Order is `group`, then the entry's `order`,
then `key` — a total order, so the same person sees the same menu in the same
sequence on every render.

## Actions with no module yet

New lead, buyer, and seller are named in the specification and are deliberately
**not registered**: there is no leads, clients, or listings section in
`HUB_SECTIONS`, and inventing a feature key to hang them on would put an action
in the menu with nothing behind it. They land in the commit that registers their
section. `test_every_feature_dependency_is_a_real_feature_key` fails on any
entry naming a feature key that does not exist, which is what keeps this honest
rather than a comment nobody rereads.

## Actions that open a drawer

`new-announcement` and `new-quick-access` do **not** point at their standalone
create pages. They carry `query=(("create", "1"),)` and land on the *list* page,
whose view reads the flag and opens its create drawer — the queue stays in view,
and the standalone form remains for a direct visit or a bookmark.

The query parameters are part of the registry, so they are code-owned like the
route name: an action still cannot name an arbitrary URL. And the flag opens a
drawer, not a door — `?create=1` on a page the actor may not open is still a
403, which `test_opening_a_drawer_is_still_refused_without_the_permission`
asserts.

## Return destinations

`safe_return_path()` accepts a site-relative path and nothing else. `//host` is
refused because it looks relative and is not — it inherits the page's scheme and
leaves the origin — and anything carrying a scheme, a backslash, or a control
character is refused outright. Everything a caller does with the result is an
open redirect if this is wrong, so it is deliberately narrow.

## The menu

One registry drives both entry points: the header is the same component on
desktop and mobile, so the two can never offer different actions.

- **Keyboard**: the trigger is a real button that opens a dialog
  (`aria-haspopup="dialog"`); Escape closes it. Focus moves to the search box
  on open when there is one, and is returned to the trigger on close — the
  trigger is not a `DialogTrigger`, so Radix has nothing to restore to and the
  component does it explicitly.
- **Search** appears only when the server says the set is large
  (`SEARCH_THRESHOLD`); below that, searching a list you can read at a glance is
  friction.
- **Scope context** is shown as "Acting for …", so somebody holding several
  hats does not have to guess which one an action will use.
- **External actions** carry an icon and a screen-reader "(leaves the hub)"
  disclosure, so a click is never a surprise.
- **Empty states** distinguish "you have no actions yet" from "nothing matches
  what you typed".

## Related docs

- `docs/permissions.md` — the catalog every action's permission comes from
- `docs/navigation.md` — the sidebar registry and feature flags
