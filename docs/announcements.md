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
priority, empty title, empty body, no audience — as `(field, message)` pairs, so the same
list raises as a `ValidationError` on publish and renders as a checklist on the
draft. `validation_debt_payload()` is its camelCase form
(`{isPublishable, items[]}`).

At publish, the rule holds three times over: `publish_announcement()` refuses
while debt remains, `Announcement.clean()` re-checks, and the check constraint
`announcement_published_requires_taxonomy` makes it a database fact. A
published row without a category or priority cannot exist.

Audience debt is reported only once the row exists — selectors are related
rows, so an unsaved announcement has no way to carry one. `publish_announcement()`
always runs on a saved row and refuses an empty audience, so that is the gate.

`publish_announcement()` checks in a deliberate order: permission and
publishing-office scope first (an unauthorized caller learns nothing about the
draft), then the whole validation checklist at once, then authority over each
named selector.

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

1. `audience.visible_announcements()` decides which rows exist for this reader
   — audience predicate, then published status, then the publication window.
2. `apply_filters()` narrows that set with validated reader input.
3. `order_for_feed()` sorts what steps 1 and 2 produced. It does not filter and
   does not re-query.

Priority participates in step 3 only. An urgent announcement outside its
window, or not addressed to the reader, is simply not in the set that reaches
the sort. That is a property of the code shape, not a rule someone has to
remember — and `test_announcements.py` asserts it directly with deliberately
urgent invisible rows.

## Audience

Audience is a set of rows on `AnnouncementAudience`, not a column. Each row
names exactly one target, enforced by a check constraint per kind, so an
ill-formed selector cannot be stored.

`owner_office` still exists but no longer *implies* the audience: it is the
publishing office — provenance, and the scope a manager needs authority over.
Migration `0004_backfill_owner_office_audience` wrote the old implication down
as explicit rows.

### Selector types

| Kind | Reaches |
| --- | --- |
| `company` | Every user. |
| `role` | Every user holding that role code in a live assignment — validity windows honoured, multiple roles honoured. |
| `region` | Every user whose primary office is that node **or any office beneath it**. |
| `office` | Every user whose primary office is exactly that node. Never a sibling, never a parent. |
| `user` | That one person. |

`region` and `office` selectors may both point at the same node: they mean
different things ("under this node" versus "this node itself") and the unique
constraints allow both.

### Union semantics

**Selectors are OR.** A reader who matches *any* selector sees the
announcement. Matching several still yields exactly one feed entry, because
membership is a set test — `audience_q()` is one `IN` against the audience
table, not one `OR`-ed join per kind — so there is no `.distinct()` here
compensating for a join that fans out. `recipients_for()` returns a `User`
queryset for the same reason.

The UI states the rule rather than leaving the list to imply it: the detail
page's audience section reads "Sent to anyone matching any of these N
audiences", because reading "Fairfax, VA" beside "Compliance" and inferring
"compliance officers *in* Fairfax" would be exactly backwards.

### One predicate, everywhere

`apps/announcements/audience.py` is the only implementation. The feed, the
detail page, the attachment download, the dashboard, notifications, and search
all call `visible_announcements()` or `visible_to()` — so a guessed detail URL
or a shared attachment link is exactly as permissive as the list the reader was
actually shown, which is to say not at all. `assert_visible()` is the
direct-object-access form; it records the denial before raising.

Attachments live in protected storage and are streamed by the download view.
There is no durable public URL that could outlive the reader's place in the
audience.

### Evaluated at read time, never materialized

The predicate reads the reader's *current* primary office and *current*
effective roles on every request. Nothing is cached against the announcement
and no recipient list is frozen at publish. The documented consequence:

- **Moving someone to another office** changes what they can open from that
  moment on, for announcements published long before — they gain their new
  office's history and lose their old office's.
- **Ending or revoking a role assignment** closes access immediately; a
  *scheduled* assignment opens it when its window arrives, with no backfill job
  involved.
- **Deactivating an office** does not revoke news addressed to it. The reader
  still belongs to that office, and silently dropping people mid-reorganization
  would be worse than the alternative.

The `announcement.published` domain event carries the selector list — the
*rule* — not a recipient list. Consumers call `recipients_for()` so fan-out is
computed against the org as it stands.

### Publishing authority

A publisher needs `web.manage_announcements` **and** authority over every
selector they name, checked in `assert_can_target()` against the actor's own
querysets rather than against what was submitted:

| Selector | Requires |
| --- | --- |
| `company` | Company-wide effective access. |
| `region` / `office` | The node inside `targetable_office_ids()` — the actor's grant, expanded downward. Never a sibling, never an ancestor. |
| `role` | The role inside `targetable_role_codes()`, which is the set the actor may *delegate*. Reusing the delegation catalog keeps one answer to "which roles may this administrator act on". |
| `user` | The person inside the actor's administered user queryset. |

One denied selector rejects the whole set; a mixed request is never partially
applied. Denials are recorded as `security.announcement.audience_denied`, and
every change to a stored audience is recorded as
`announcement.audience_changed` with before/after selector lists.

### Recipient search is not a directory

`search_recipients()` backs the individual-recipient typeahead. Three things
stop it becoming an enumeration tool: the manage permission is required, the
queryset starts from the actor's administered set, and a query shorter than
`MIN_RECIPIENT_QUERY` (2) returns nothing at all. Results are capped at 20.

### Cost

The reader's facts — office ancestor chain and live role codes — are gathered
once per request into an `AudienceContext` and turned into one indexed
subquery. The three indexes on `AnnouncementAudience` lead with `kind` and then
the selector's own target column, matching the shape of each `OR` branch.
Answering "can this person see these fifty announcements" costs the same as
asking about two; `test_the_feed_cost_does_not_grow_with_the_number_of_announcements`
pins that by comparing query counts at two sizes.

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
`notify` and `notification_priority` straight from the event payload, and call
`audience.recipients_for()` for the recipient set. Do not re-derive policy
there, and do not cache the recipients: audience is re-evaluated at read time,
so a notification's *detail* must still pass `visible_to()` when it is
rendered.

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
- **New audience selector kind:** a deliberate deploy. Add the `Kind`, extend
  the check constraint and the index set, add a branch to `selector_q()` *and*
  `recipients_for()` — the two directions must agree, and
  `test_the_two_directions_agree` is what catches it if they do not — then add
  its authority rule to `assert_can_target()`.
- **New priority:** a deliberate deploy. Add the `PriorityDefinition`, its
  tone, and its `NotificationBehavior`, and update this document's tables —
  `test_taxonomy.py` fails if the priority tone or policy map is incomplete.

## Media: hero image and attachments

One optional hero image plus up to 10 ordered attachments per announcement,
each a row on `AnnouncementMedia`. The row — not the file path — is the record:
it carries the display name, detected type, byte size, SHA-256 checksum,
uploader, dimensions, generated variants, and processing state, which is what
makes retention answerable after the fact.

### Allowed file matrix

| Extension | Stored type | Max | Hero? |
| --- | --- | --- | --- |
| `.png` | `image/png` | 8 MB | yes |
| `.jpg` / `.jpeg` | `image/jpeg` | 8 MB | yes |
| `.webp` | `image/webp` | 8 MB | yes |
| `.pdf` | `application/pdf` | 20 MB | no |
| `.docx` | Word (OOXML) | 20 MB | no |
| `.xlsx` | Excel (OOXML) | 20 MB | no |
| `.txt` | `text/plain` | 2 MB | no |
| `.csv` | `text/csv` | 5 MB | no |

A hero must additionally be at least 600px wide. Images are capped at
8000×8000 and 40 million pixels.

### Three checks, all of which must agree

Nothing about an upload is taken on trust — not the filename, not the
`Content-Type` header, not the extension:

1. **Extension** must be in the matrix.
2. **Detected type**, sniffed from the leading bytes, must be one the extension
   is allowed to carry. This is what catches a disguised upload: a `.png` whose
   bytes are `MZ…` is refused, and the error says what was actually found.
3. **Shape** — byte size always; dimensions and total pixel count for images.

The pixel-count ceiling is applied to the **header, before any decode**.
`Image.open` parses only the header, so a decompression bomb — a few kilobytes
of PNG claiming a 7000×7000 canvas — is refused while it is still a few
kilobytes. Decoding first and asking afterwards is how that attack works.

Detection uses a local signature table rather than `libmagic`, so there is no
system dependency to be present in one environment and missing in another.

### Storage keys

`storage_key()` returns `announcements/<uuid4-hex><ext>`. The submitted
filename never reaches the path — only the extension survives, and only after
the matrix accepted it. `../../etc/passwd.png`, an absolute path, and a NUL
byte all produce an ordinary random key. The original name is kept separately
as `display_name`, for display only.

### Processing

An upload lands `PENDING` and is **not readable by anyone but an
administrator**. `process_announcement_media` then, after the transaction
commits:

1. re-reads the stored bytes and **verifies the checksum** — if storage holds
   something other than what was validated, the row is quarantined;
2. for images, **strips metadata** by copying the raw bitmap into a fresh image
   (nothing but pixels crosses over, so there is no EXIF, XMP, or ICC block
   left to enumerate) — an announcement hero has no use for GPS coordinates or
   a camera serial, and it is about to be served to the whole brokerage;
3. generates **responsive variants** at 320 / 768 / 1600px, skipping any width
   that would upscale the source;
4. lands on `READY`, `QUARANTINED`, or `FAILED`.

The pass is idempotent: re-running it produces the same variants and the same
state. Queuing happens in `transaction.on_commit`, so a rolled-back upload
never leaves a worker chasing a row that does not exist.

**Publication is gated on it.** `media_publish_debt()` blocks publish while any
active file is not `READY`, and `processingState` / `processingNote` appear
only in administrator payloads — telling a recipient that a file was
quarantined tells them a file exists, which is more than they are entitled to
know.

### Access: no presigned URLs, deliberately

A presigned S3 link is an *escape* from the audience predicate for the length
of its TTL: once issued it works for whoever holds it, and a reader who leaves
the audience the next minute keeps it until it expires.

Every file — hero, attachment, and every generated variant — is therefore
streamed through a view that re-runs `audience.visible_to()` **on each
request**, and additionally refuses anything that is not `READY`. Responses
carry `Cache-Control: private, no-store`.

That is what the acceptance criterion is really after: guessing a storage key
gets you nothing (the key is random and the bucket is private), and a
previously issued URL is just the view path, which authorizes again on arrival.
`test_the_same_url_stops_working_when_the_reader_leaves_the_audience` pins it.

### Retention and orphan cleanup

| Situation | What happens to the file |
| --- | --- |
| Removed or replaced on a **draft** | Row and bytes deleted — a draft has no readers, so its discards are storage nobody needs. |
| Removed or replaced on a **published** announcement | Row deactivated, bytes kept. Anything a recipient could already have seen stays reconstructable. |
| Announcement **archived** | Nothing. Media stays active and stored. |

`sweep_orphan_media()` is the counterweight that stops retention becoming
storage nobody can account for. It handles two distinct leaks:

- **Rolled-back writes.** The file is written inside the transaction that
  creates its row; if that rolls back, the row is gone and the object is not.
  Unreferenced objects under the announcements prefix, older than a 6-hour
  grace period, are swept. The grace period is what keeps an upload in flight
  in another request from looking like an orphan.
- **Abandoned drafts.** A draft untouched for 30 days is not history worth
  retaining, so its media rows and bytes both go.

Run it with `uv run python manage.py sweep_announcement_media`
(`--dry-run` to see the thresholds), or schedule
`sweep_announcement_media_orphans` through Celery beat — this project uses the
database scheduler, so the periodic entry is created in the Django admin rather
than in settings.

### Management

`/operations/announcements/<id>/media` — hero uploader and attachment list,
gated by `web.manage_announcements` on the server *and* `PermissionRequired` in
the page, scoped to the actor's publishing offices.

Upload progress comes from `XMLHttpRequest` rather than `fetch`, which has no
upload-progress event; a large hero with no feedback reads as a frozen page.
Rejections surface the server's own sentence, since it is the only party that
knows whether a file was the wrong type, too large, or disguised.

Reordering is **buttons, not drag-and-drop**: a drag target is unreachable from
the keyboard without building a parallel control anyway, and two buttons are
that control. Each move persists immediately, so there is no separate save step
to forget.

### Missing hero degrades to text

`heroSources()` returns `null` when there is no hero, when it is not an image,
or when nothing renderable exists — and the page treats that identically to an
image that fails at runtime, via `onError`. In every case the hero simply is not
there; the headline and body stand on their own. The hero's `alt` is empty
because the headline above it already carries the meaning, and a description
would be read out twice.

## Local demo data

```bash
uv run python manage.py seed_announcements   # announcements only, idempotent
uv run python manage.py seed_dev             # offices + roles + users + announcements
```

The seed deliberately includes rows a Fairfax reader should **not** see — a
sibling branch's notice, another region's news, a scheduled one, an expired
one, a role they do not hold — plus a draft carrying validation debt. A seed
that only produces visible rows makes an audience bug look like a working
feature, so the negatives are the point;
`test_the_seeds_negatives_really_are_negative` asserts each row that claims to
be hidden really is.

The individual-recipient row targets `agent.fairfax@onest.test` and is skipped
with a note if `seed_users` has not run.
