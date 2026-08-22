# Announcements: categories, priorities, and the feed

Announcements are classified two ways. **Category** says what kind of news it
is; **priority** says how loudly it should arrive. Both are stored as stable
machine codes, and everything downstream — ordering, badges, notification
policy, feed URLs — is derived from those codes rather than duplicating them.

Code: `apps/announcements/`. Page: `frontend/pages/Announcements.tsx` at
`/announcements`.

## The governance split

| | Priority | Category |
| --- | --- | --- |
| Owner | Code (`apps/announcements/taxonomy.py`) | Administrators (database rows) |
| Set | Closed: `urgent`, `important`, `normal` | Open: 8 seeded + whatever is added |
| Labels | Fixed in code | Editable |
| Add / remove | Requires a deploy | Django admin |
| Retire | Not applicable | `is_active = False` |
| Delete | Not applicable | Only unseeded **and** unreferenced |

**Priority is code-owned** because two behaviours read it as a contract: the
feed's documented ordering and the notification policy adapter. An
administrator who could add a fourth level, reorder ranks, or relabel `urgent`
would be editing behaviour, not vocabulary. Governance therefore does not
permit editing priority labels at runtime.

**Category is admin-managed** because it is vocabulary. Which kinds of news a
brokerage publishes changes over time without any behaviour changing with it.

### Priorities

| Code | Label | Rank | Meaning |
| --- | --- | --- | --- |
| `urgent` | Urgent | 1 | Act today. Sorts first, notifies immediately. |
| `important` | Important | 2 | Read soon. Sorts above routine news, notifies in-app. |
| `normal` | Normal | 3 | Routine. Sorts by recency, does not notify. |

Lower rank sorts first, matching `apps/notifications/contract.py` so the two
scales never disagree about what is more urgent.

### Seeded categories

`company_announcement`, `market_update`, `event`, `training_notice`,
`compliance_update`, `office_notice`, `technology_notice`,
`urgent_operational_notice`.

All eight are created by `announcements/migrations/0002_seed_categories.py` as
`is_system` rows. The seed is idempotent and only fills in missing codes, so an
administrator's relabel survives a redeploy.

### Category rules

- **`code` is immutable.** It appears in feed URLs, audit payloads, and the
  presentation map, so `AnnouncementCategory.clean()` refuses to change it. Edit
  `label` instead — nothing outside the admin reads the label.
- **Seeded categories can never be deleted**, referenced or not. Both
  `AnnouncementCategory.delete()` and the queryset's `delete()` raise
  `ProtectedCategoryError`, so a bulk admin action cannot route around it.
- **Referenced categories can never be deleted.** `services.delete_category()`
  refuses, and `on_delete=PROTECT` is the database backstop if a caller reaches
  the row another way.
- **Retiring is `is_active = False`.** A retired category cannot be assigned to
  anything new, but every announcement already carrying it stays readable with
  its real label — the badge just says "(retired)" to a screen reader.

## Publishing requires both codes

Drafts may be incomplete. `services.validation_debt()` reports what still
stands between a draft and publication — missing category, missing or unknown
priority, empty title, empty body — as `(field, message)` pairs, so the same
list raises as a `ValidationError` on publish and renders as a checklist on the
draft. `validation_debt_payload()` is its camelCase form
(`{isPublishable, items[]}`).

At publish, the rule holds three times over: `publish_announcement()` refuses
while debt remains, `Announcement.clean()` re-checks, and the check constraint
`announcement_published_requires_taxonomy` makes it a database fact. A
published row without a category or priority cannot exist.

Publishing emits `announcement.published` twice — an `AuditEvent` with a
before/after snapshot, and a `DomainEvent` carrying the taxonomy codes plus the
already-resolved notification behaviour, so a consumer never re-derives policy
from the row.

## Ordering

The feed's documented order, applied in `services.order_for_feed()`:

1. **priority rank** ascending — urgent, important, normal
2. **`published_at`** descending
3. **`pk`** descending, as a stable tiebreak

Rank is computed with a `Case`/`When` expression built from the code catalog
rather than stored, so the database never holds a second copy of the ranking
that can drift from `taxonomy.py`.

### Priority never widens anything

`services.py` runs strictly one-directional:

1. `visible_queryset()` decides which rows exist for this reader — audience
   scope, then published status, then the publication window.
2. `apply_filters()` narrows that set with validated reader input.
3. `order_for_feed()` sorts what steps 1 and 2 produced. It does not filter and
   does not re-query.

Priority participates in step 3 only. An urgent announcement outside its
window, or owned by a node the reader does not sit under, is simply not in the
set that reaches the sort. That is a property of the code shape, not a rule
someone has to remember — and `test_announcements.py` asserts it directly with
deliberately urgent invisible rows.

**Audience** is the owning office node: head office owns brokerage-wide news, a
region owns its region, a branch owns itself. A reader sees announcements owned
by any node on their own office's ancestor chain, resolved server-side from
`request.user.office`. No office identifier is ever accepted from the client.

## Feed filters

Stable query values, both stable codes:

```
/announcements?category=compliance_update&priority=urgent&page=2
```

`AnnouncementFilters.from_params()` validates both. A value that is not a live
category code or a catalog priority code is **dropped, not applied**, and named
in `filters.rejected` so the page can say the filter was ignored rather than
quietly returning a wider set than the reader asked for.

Filtering by a *retired* category is allowed and returns its history; that code
also stays in the filter options while it is selected, so a bookmarked filter
survives the category's retirement. `rejected` is a report, never echoed back
into a URL. Pagination preserves both filters — `buildListUrl()` merges the
current filters into every page link.

## Presentation adapter

`apps/announcements/presentation.py` is the only place taxonomy becomes
something a badge can render. What crosses the boundary is a **semantic tone** —
`neutral`, `info`, `success`, `warning`, `destructive` — matching
`frontend/types/design-system.ts`.

| Priority | Tone | Category | Tone |
| --- | --- | --- | --- |
| `urgent` | `destructive` | `urgent_operational_notice` | `destructive` |
| `important` | `warning` | `compliance_update` | `warning` |
| `normal` | `neutral` | `event` | `success` |
| | | `company_announcement`, `training_notice` | `info` |
| | | `market_update`, `office_notice`, `technology_notice` | `neutral` |

No hex value, Tailwind class, or badge variant is stored on a model or crosses
the wire. The priority map is total by construction (closed set); the category
map is deliberately partial — **any category added through the admin renders on
`DEFAULT_CATEGORY_TONE` (`neutral`)**, which is the documented fallback, not an
omission to fix on each vocabulary change.

**Colour is never the only carrier.** Every badge payload includes `label` and
an `srLabel` sentence, the page repeats both as visually-hidden text, and
`urgent` / `important` carry an icon as a second non-colour channel.

## Notification policy adapter

`apps/announcements/policy.py` is the only place priority is allowed to
influence delivery, and it decides two things — whether to interrupt, and how
the resulting notification sorts. It never decides **who** receives one; that
comes from the announcement's audience scope, computed before this module is
consulted.

| Priority | Notifies | Notification priority |
| --- | --- | --- |
| `urgent` | yes | `NotificationPriority.CRITICAL` |
| `important` | yes | `NotificationPriority.HIGH` |
| `normal` | no | `NotificationPriority.NORMAL` |

Routine news does not earn a badge increment: making every publish notify is
how a notification centre stops being read.

**Integration point.** The adapter and the `announcement.published` domain
event are in place. Fan-out to recipients belongs with the announcement
publishing pipeline — register a builder in
`apps/notifications/producers.py` keyed on `announcement.published`, take
`notify` and `notification_priority` straight from the event payload, and
resolve recipients from the audience scope. Do not re-derive policy there.

## Unknown legacy codes

Read paths never raise; write paths never accept.

| Situation | Read | Write |
| --- | --- | --- |
| Unknown priority code | `resolve_priority()` returns `normal` with `known=False`, keeps the original in `requested_code`, logs a warning | `require_priority()` raises `ValidationError` |
| Missing priority | Same fallback, no warning (a draft has simply not chosen yet) | Publish refused as validation debt |
| Missing category | `resolve_category(None)` returns the `uncategorized` placeholder | Publish refused as validation debt |
| Unknown filter value | Dropped and reported in `filters.rejected` | — |

A legacy code therefore sorts as normal, notifies as normal, and renders on the
normal badge — and the page says in words that it was substituted, rather than
pretending the row was always normal.

## Extending

- **New category:** add it in the Django admin. No deploy. It renders on the
  default tone until someone adds a deliberate one to `CATEGORY_TONES`.
- **New category that ships with the product:** add a `CategorySeed` to
  `CATEGORY_SEED`, a tone to `CATEGORY_TONES`, and a data migration that
  mirrors `0002_seed_categories.py`.
- **New priority:** a deliberate deploy. Add the `PriorityDefinition`, its
  tone, and its `NotificationBehavior`, and update this document's tables —
  `test_taxonomy.py` fails if the priority tone or policy map is incomplete.
