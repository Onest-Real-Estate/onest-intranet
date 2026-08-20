# Quick Access: administered dashboard launchers

The Quick Access panel on the dashboard is configuration, not code. An
authorized administrator adds a tool, points it somewhere, decides who sees it,
and orders the panel — without a deploy. This document is the contract for what
that configuration means and who may change it.

The panel used to be a tuple in `apps/web/dashboard/providers.py`. Migration
`web.0007` carries those four vendors into the database as company-wide links,
so the deploy that turned the panel into data changed nothing an agent sees.

## Data model

`apps.web.models.QuickAccessLink` is one launcher.

| Field | Meaning |
| --- | --- |
| `stable_key` | Permanent identity. Unique, and immutable after creation — audit rows and integrations address a link by this. |
| `name`, `description` | What the reader sees. |
| `destination_type` | `external_url` or `internal_route`. |
| `destination_value` | An `https://` URL, or the key of an allowlisted internal destination. |
| `icon` | Key from the approved icon set. Never a URL. |
| `is_active` | Off hides the link without removing it. |
| `is_archived`, `archived_at` | Retired. Records are archived, never deleted. |
| `sort_order` | Lower sorts first. **Not unique** — see *Ordering*. |
| `publish_start_at`, `publish_end_at` | Optional window; start inclusive, end exclusive. |
| `sso_capability` | `none`, `microsoft_entra`, `saml`, `oidc`. Describes the tool; holds no credential. |
| `integration_health` | `unknown`, `healthy`, `degraded`, `offline`. Rendered as a badge. |
| `setup_behavior` | `none`, `self_service`, `request_access`, `provisioned`. Read by onboarding. |
| `company_wide` | Visible to every office. Implies company ownership. |
| `owner_scope` | `company` or `scoped`. Gates who may edit the definition. |
| `owner_office` | The node a scoped link belongs to; used for the audit `office_id`. |
| `created_by`, `updated_by`, `created_at`, `updated_at` | Who and when. |

Audience is two explicit tables, not a comma-separated list:

- `QuickAccessLinkRoleAudience(link, role_code)` — stable role codes from
  `apps/user/roles.py`, unique per link.
- `QuickAccessLinkOfficeAudience(link, office, include_descendants)` — an
  office-tree node, unique per link. `include_descendants` is what lets one row
  on a region cover every branch beneath it.

**A link record never stores a third-party credential.** A destination URL
carrying a token-shaped query parameter is rejected outright rather than
stripped, and there is no field for a secret.

## Audience resolution

Implemented once, in `apps/web/quick_access/resolution.py`, and used by both the
dashboard provider and the administrator's preview. A second implementation
would be a second answer, and the preview would stop meaning anything.

A link is visible to a reader when all of the following hold:

1. **Lifecycle** — not archived, and active.
2. **Publish window** — `publish_start_at` is null or in the past, and
   `publish_end_at` is null or in the future.
3. **Role audience** — no role rows means every role; otherwise the reader must
   hold at least one named role, resolved through effective assignments.
4. **Office audience** — `company_wide` short-circuits to visible; otherwise the
   reader's own office must match an audience row, either the row's office
   exactly or an ancestor node whose row includes descendants.

Dimensions are ANDed; values within a dimension are ORed. So a link naming
*Realtor* and two offices reaches realtors in those two offices, and nobody else.

"Agent" is not a special case — it is the `realtor` role code, matched by rule 3
like any other. A reader with no office sees only company-wide links: there is
no office tree that can be said to contain them.

Order is `sort_order`, then `name`, then `pk`.

## Who may administer what

Two permissions, deliberately separate because one is strictly wider:

| Permission | Grants |
| --- | --- |
| `web.manage_quick_access` | Create, edit, reorder, activate, and archive links whose audience sits inside the actor's own office scope. |
| `web.manage_company_quick_access` | Additionally publish company-wide and edit company-owned definitions. |

**Grant scope.** An administrator's targetable offices are their effective
office and region keys *expanded through the tree*: a regional manager may aim a
link at any branch beneath their region. Company-wide access short-circuits.

**The grant boundary.** `ensure_audience_within_grant` refuses an audience wider
than the actor holds — a company-wide publish without the company grant, or an
office outside their scope. The form only offers offices in scope, but a hidden
option is a courtesy, not a control; the server checks every write.

**Company-owned definitions.** A company-wide link is owned by the company. A
scoped administrator does not see it in their list, cannot edit it, and cannot
move it in a reorder. A scoped link is manageable when *every* office it names
is inside the actor's scope — a link reaching one office they manage and one
they do not is not theirs to edit.

## Confirming a widening change

Changes that can put a tool in front of people who could not see it route
through a confirmation:

- creating a link;
- changing the destination;
- turning on `company_wide`;
- adding offices to the audience;
- removing roles from the role filter.

Narrowing changes do not: taking access away is not the risky direction.

The React form shows the diff in `AccessChangeDialog` and resubmits with
`acknowledge_exposure`. The server runs the same test independently and returns
**422** with the diff attached if the acknowledgement is missing, so a widening
change is never applied by a single click, whatever the browser does.

## Ordering

`sort_order` is **not unique**, on purpose. A unique position makes every
routine drag a renumbering of the whole table, and a failed renumber leaves the
panel in an order nobody chose. Instead:

- positions may repeat, and ties break deterministically by name then id;
- the reorder endpoint takes the submitted sequence, collects the positions
  those links *already* occupied, and hands them back out in the new order —
  monotonically, separating ties as it goes;
- links the actor cannot manage keep their position, so a company link
  interleaved between two office links stays where it is;
- every submitted id must be manageable by the actor, or the whole reorder is
  refused.

## Destinations

External destinations must be `https://` with a hostname, no embedded
credentials, and no fragment. `http://` is refused rather than upgraded —
silently rewriting an administrator's URL hides a mistake instead of reporting
it.

Internal destinations store an **allowlist key**, not a path
(`apps/web/quick_access/catalog.py`). The path is produced by `reverse()` when
the link renders, so a route rename cannot leave a live launcher pointing at a
stranger's URL. A key that has since left the allowlist resolves to an empty
href and the link is dropped from the panel.

## Freshness

The Quick Access widget is cached per user for 300 seconds, because its payload
now depends on the reader's role and office. A save still has to reach readers
who already hold a cached panel, so every cache key carries
`configuration_version()` — a digest of the links and audience tables. Writing
recomputes it, which retires every previously cached key at once instead of
deleting an unbounded set of per-user entries.

Recomputing rather than deleting is deliberate: a delete would let a concurrent
read repopulate the key from the pre-commit state. If the cache is cold or was
evicted the stamp is recomputed from the database, so a lost entry degrades to a
slower answer, never a stale one.

## Audit

Every lifecycle-changing action writes an `AuditEvent` with before/after values:

| Action | When |
| --- | --- |
| `web.quick_access.created` | A link is created. |
| `web.quick_access.updated` | Fields or audience change. |
| `web.quick_access.audience_changed` | Emitted alongside `updated` when the audience itself moved. |
| `web.quick_access.activation_changed` | Activated or deactivated. |
| `web.quick_access.archived` | Archived or restored. |
| `web.quick_access.reordered` | Panel order rewritten, with the old and new sequences. |
| `security.quick_access.denied` | A management attempt outside the actor's authority. |

Authorization runs *outside* the write transaction. A `PermissionDenied` raised
inside `atomic` would roll the transaction back and take the denial audit row
with it; the locked row is re-checked inside, so a scope change landing between
the two checks still loses.

## Endpoints

| Route | Method | Permission |
| --- | --- | --- |
| `admin_quick_access` | GET | `web.manage_quick_access` |
| `quick_access_new` | GET | `web.manage_quick_access` |
| `quick_access_edit` | GET | `web.manage_quick_access` |
| `quick_access_create` | POST | `web.manage_quick_access` |
| `quick_access_update` | POST | `web.manage_quick_access` |
| `quick_access_state` | POST | `web.manage_quick_access` |
| `quick_access_reorder` | POST | `web.manage_quick_access` |

A link is always loaded through the actor's manageable queryset, never by bare
id, so an out-of-scope id is a **404** rather than a 403 — confirming that an id
exists is itself a disclosure across a scope boundary.

Preview lives on the index route as `previewRole` and `previewOffice` query
parameters. The office is administrator-supplied by design, so it is resolved
through their own targetable queryset; an office outside their scope produces
`outOfScope`, not a peek at somebody else's configuration. The preview lists
every link with a visible/hidden verdict and *all* the reasons it stays hidden —
a link that is both inactive and out of audience should not look like it only
needs a switch flipped.

## Adding an icon

1. Add the key and its label to `QUICK_ACCESS_ICONS` in
   `apps/web/quick_access/catalog.py`.
2. Add the matching component to `frontend/lib/quick-access-icons.ts`.

`test_every_approved_icon_has_a_mark_in_the_bundle` pins the two together. The
frontend falls back to a generic window for an unknown key, which is exactly why
the mismatch needs a test — nothing at runtime would report it.
