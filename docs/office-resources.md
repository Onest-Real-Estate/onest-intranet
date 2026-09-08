# Office Resources

Location-specific instructions, procedures, contacts, links, and files for one
branch — the "how does my building actually work" module. Replaces the
`office-resources` Coming Soon destination.

## Data model

`OfficeResource` (`apps/user/models.py`) is owned by a node of the office
tree. The owning node's kind **is** the scope:

| Owner kind | Scope level | Example |
| --- | --- | --- |
| `head_office` | `company` | Onest Real Estate (head office) |
| `region` | `region` | Mid-Atlantic, New England |
| `regional_office` / `branch` | `office` | Fairfax VA, Harrisburg |

Fields: stable `slug`, `title`, optional `summary`, type-specific payload
(`body` for content, HTTPS-only `url` for links, protected-storage `file` for
files), `category`, `is_active`, `sort_order`, publish window
(`starts_at` / `ends_at` dates), audit timestamps and `created_by`.

Validation is enforced in `clean()` and mirrored by DB constraints where
possible: links must be HTTPS, only link resources carry a URL, only file
resources carry an upload, only content resources carry body text, and
`ends_at >= starts_at`.

## Visibility contract

Implemented once in `apps/user/services/office_resources.py`. The agent page,
search, and the download view all go through the same gate.

1. **Scope chain.** The signed-in user's primary office plus its ancestors up
   to and including the head office. The primary office is always
   `user.office`; no office or resource identifier is ever accepted from the
   client. A user without an active primary office sees nothing.
2. **Window + active filter.** Only active resources whose publish window
   contains today are candidates. This filtering happens before serialization,
   so search results can never contain titles or snippets from another office.
3. **Precedence by slug.** `slug` is the resource identity across scopes. When
   the same slug exists at several levels of the chain, the closest scope wins:
   `office > region > company`. A branch therefore overrides company defaults
   deterministically, and no duplicates are displayed.
4. **Ordering.** Categories follow catalog order; within a category,
   `sort_order`, then `title`, then `pk`.

## Files

Uploads never use public media URLs. Locally they live under
`MEDIA_ROOT/private/` with no browsable base URL; on S3/MinIO they are stored
under `private/` with a private ACL. The only read path is
`GET /office-resources/<slug>/download`, which re-resolves the actor's
effective resources (same gate as the page), streams via `FileResponse` with
`Cache-Control: private, no-store`, restores the original filename, and emits
an `office_resource.downloaded` audit event. A slug that is not currently
visible to the actor 404s — including content/link-type slugs and resources
from other branches.

## Administration

Resources are authored in the scoped operations console at
`/operations/office-resources` (`OfficeResourcesAdministration` list page +
`OfficeResourceWorkspace` editor), backed by
`apps/user/services/office_resource_administration.py`. Django admin
(`OfficeResourceAdmin`) remains available as a fallback with audit events on
create/update/delete.

### Permission model

| Codename | Purpose |
| --- | --- |
| `web.view_office_resources_admin` | Open the console; see scoped rows. |
| `web.manage_office_resources` | Create/edit/schedule/reorder/archive within scope. |
| `web.publish_company_resources` | Author company-owned (head-office) resources. |

Default holders mirror the office-administration bundles: brokerage admins and
principal broker hold all three; regional managers/admins, branch managers,
branch admins, and marketing hold read+manage.

### Grant boundaries

Writable owners come from the actor's effective access (same source as office
administration): company-wide actors reach every node; region actors reach
their region nodes and descendants; office actors reach their own seat only.
Server-side enforcement re-validates every write:

- The owning office must be inside the actor's writable boundary.
- Editing head-office resources additionally requires
  `web.publish_company_resources` plus company-wide authority.
- A slug that would shadow (collide with) a resource owned by a node outside
  the actor's boundary is rejected — crafted slug values fail closed.
- Preview (`?preview=<officeId>`) only resolves offices inside the boundary.

### Concurrency, lifecycle, files

- Every edit form carries an optimistic-concurrency token
  (`{pk}:{updated_at}`); a stale token returns HTTP 409 with a recoverable
  message instead of overwriting a newer edit.
- Lifecycle transitions are `activate`, `deactivate`, `archive`,
  `unarchive`, `move_up`, `move_down`. Archive is preferred over delete:
  rows stay for audit and are excluded from visibility while archived.
- Uploads are validated by extension allowlist and a 10 MB cap. A failed
  upload marks the row **quarantined** (and deactivates it); quarantined
  files cannot be published until replaced. Replaced or abandoned upload
  objects are deleted from protected storage; nothing is written to public
  media URLs.
- Every content/ownership/file/activation/schedule/order change emits audit
  events (`office_resource.created`, `.updated`, `.archive`, `.activate`,
  …) with before/after snapshots; denials emit
  `security.office_resource_administration.denied`.

### Cache

Agent-facing resolution caches per office node keyed by a generation counter;
any resource save/delete bumps the generation via signals, so console changes
are visible immediately without stale reads.


## Search and URL state

The page accepts validated list-query params `q` (max 120 chars) and
`category` (must match the catalog, otherwise ignored). Both are echoed back
in props and preserved in the URL with Inertia `replace` visits so filtered
views are shareable and reloadable.
