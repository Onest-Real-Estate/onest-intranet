# Documents & Forms

The Documents & Forms library at `/documents-forms` is the consumer surface
for brokerage-approved forms. Every read path — the library, detail page,
protected download, and global search — uses the same audience, jurisdiction,
and current-version predicates in `apps.documents.audience` and
`apps.documents.services`.

Administration of families, drafts, approval, and retirement lives in a later
ticket (#89). Until then, staff can seed rows through Django admin. The
operations console at `/operations/documents` remains a Coming Soon stub.

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

## Versioning

`DocumentFamily` holds the stable `key` and owning office. Each
`DocumentVersion` belongs to one family. Publishing a newer version
supersedes prior published siblings. Effective is inclusive
(`effective_at <= now`); expiry is exclusive (`expires_at > now`). When two
in-window published rows exist (bad data), the highest version number wins,
then primary key.

Consumer detail URLs for a superseded version **redirect** to the current
live sibling with `?superseded=1` when the reader still matches audience and
jurisdiction; otherwise they 404. The banner on the current page warns that
the bookmark was outdated.

## Files

Files use private storage and are streamed through `document_file` — never
public or long-lived S3 URLs. Responses send `Cache-Control: private,
no-store`. Uploads are inspected for extension, sniffed MIME, and size before
anything is stored. Consumer downloads require a **ready** file on the
reader's **current** live version. Guessing a historical file id 404s.

## Search

The documents search provider starts from `library_queryset(actor)` — the
same collapsed current-version set the page uses — and matches name,
description, and family key only. File bytes are never indexed.
