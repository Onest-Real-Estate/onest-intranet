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

Resources are authored in Django admin (`OfficeResourceAdmin`) with
create/update/delete audit events. Agents reach the page through the
"Office resources" nav entry (feature key `office-resources`,
policy `office_resources`, authenticated + self-only).

## Search and URL state

The page accepts validated list-query params `q` (max 120 chars) and
`category` (must match the catalog, otherwise ignored). Both are echoed back
in props and preserved in the URL with Inertia `replace` visits so filtered
views are shareable and reloadable.
