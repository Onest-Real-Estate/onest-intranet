# Documents & Forms

The Documents & Forms library at `/documents-forms` is the consumer surface
for brokerage-approved forms. Every read path — the library, detail page,
protected download, and global search — uses the same audience, jurisdiction,
and current-version predicates in `apps.documents.audience` and
`apps.documents.services`.

Administration lives at `/operations/documents` behind
`web.manage_documents`. Publication uses `web.publish_documents`.
Retirement uses `web.retire_documents`. Django admin remains a seed path;
the Hub console is the staff workflow.

## Visibility

1. Audience match (OR union across selectors)
2. `published` status and effective/expiry window
3. Jurisdiction: empty `jurisdiction_state_codes` means all states; otherwise
   the reader's `license_state` or primary office `state` must intersect
4. One **current** live row per family (highest `version_number`, then `pk`,
   among published in-window siblings)

Draft, historical, expired, and out-of-scope documents return **404**, not
403, on consumer routes.

URL filters (search, category, state, office, role) can only **narrow** the
already-visible set. An office or role the reader cannot see is rejected
rather than applied.

## Audience

Selectors are **OR**. Kinds match announcements, training, marketing, and
compliance:

| Kind | Reaches |
| --- | --- |
| company | Everyone |
| role | Live holders of that role code |
| region | Primary office under that node |
| office | Exact primary office |
| user | Named person |

Publishers must own every selector (`assert_can_target`). Company-wide
targeting requires company-wide access. Scoped publishers must name the
states they can cover; empty jurisdiction (all states) is a company-wide
grant.

## Versioning

`DocumentFamily` holds the stable `key` and owning office. Each
`DocumentVersion` belongs to one family. **Duplicate as new version**
creates a draft in the same family and copies active files. Publishing a
newer version supersedes every published sibling. Scheduling a future
effective time keeps siblings published and sets their `expires_at` to that
moment, so only one version is current once the window opens.

Effective is inclusive (`effective_at <= now`); expiry is exclusive
(`expires_at > now`). When two in-window published rows exist (bad data),
the highest version number wins, then primary key.

Stored statuses stay `draft` → `published` → `superseded` / `retired`. There
is no separate in-review or approved status.

Consumer detail URLs for a superseded version **redirect** to the current
live sibling with `?superseded=1` when the reader still matches audience and
jurisdiction; otherwise they 404. The banner on the current page warns that
the bookmark was outdated.

## Files

Files use private storage and are streamed through Hub routes — never
public or long-lived S3 URLs. Responses send `Cache-Control: private,
no-store`. Uploads are inspected for extension, sniffed MIME, and size
before anything is stored. Consumer downloads require a **ready** file on
the reader's **current** live version. Guessing a historical file id 404s.

Administrators preview and download through `document_admin_file` after a
manage-scope check, including historical versions. Removing a draft file
sets `is_active=False`; bytes stay for audit. Published, superseded, and
retired files cannot be overwritten or deleted.

## Search

The documents search provider starts from `library_queryset(actor)` — the
same collapsed current-version set the page uses — and matches name,
description, and family key only. File bytes are never indexed.

## Administration

Scoped authors manage drafts at `/operations/documents`:

- **Scope.** Own only versions whose family `owner_office` sits in the
  actor's grant. Out-of-scope ids are 404.
- **Lifecycle.** Drafts are edited in the workspace. Publish makes the
  version current and supersedes published siblings. Schedule publishes
  with a future `effective_at`. Retire leaves the library after a usage
  review (current?, file count, download count, whether the family would
  have no live form).
- **Concurrency.** Mutations carry `{updated_at}` and return HTTP 409 on
  stale edits.
- **Preview.** The workspace preview never makes a draft reachable.
  Admin file streams use the same protected storage as consumer downloads.

## Permissions

| Codename | Purpose |
| --- | --- |
| `web.manage_documents` | Draft, upload, audience, duplicate version |
| `web.publish_documents` | Publish / schedule / supersede |
| `web.retire_documents` | Retire after usage review |

Default role bundles are in `apps.user.roles` and
`apps.web.permission_catalog`. Transaction coordinators receive manage
without publication. Office administrators can publish but not retire.
Retirement is a separate, high-risk grant.
