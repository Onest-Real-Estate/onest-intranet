# Marketing Resources

The marketing library at `/marketing-resources` is the consumer surface for
brokerage-approved logos, guidelines, templates, flyers, email signatures,
vendor guidance, and campaign assets. Every read path — the library, detail
page, export/preview download, and global search — uses the same audience
predicate in `apps.marketing.audience`.

Administration lives at `/operations/marketing-resources` behind
`web.manage_marketing_resources`. Publication uses
`web.publish_marketing_resources`. Editable source downloads require
`web.download_marketing_sources` and are never offered on the consumer
surface.

## Visibility

1. Audience match (OR union across selectors)
2. `published` status and publish/expiry window
3. One **current** live row per `version_family` (highest version number that
   is published and in-window)
4. URL filters (narrow only): search, category, asset type, jurisdiction,
   brand

## Audience

Selectors are **OR**. Kinds match announcements and training:

| Kind | Reaches |
| --- | --- |
| company | Everyone |
| role | Live holders of that role code |
| region | Primary office under that node |
| office | Exact primary office |
| user | Named person |

Publishers must own every selector (`assert_can_target`). Company-wide
targeting requires company-wide access.

## Versioning

Each asset carries `version_family` + `version_number`. **Duplicate as new
version** creates a draft in the same family. Publishing a version greater
than 1 archives previous live siblings. Superseded rows stay for audit.

Consumer detail and download URLs for an archived version **redirect** to the
current live sibling when the reader still matches audience; otherwise they
404. The operations console keeps full history.

## Files

Files use private storage and are streamed through Hub routes — never public
or long-lived S3 URLs.

| Role | Who can download |
| --- | --- |
| `export` | Audience-matched readers (approved download) |
| `preview` | Audience-matched readers (generated thumbnail / derivative) |
| `source` | Actors with `web.download_marketing_sources` in manage scope |

Uploads land as `pending`. Celery `process_marketing_file` moves them to
`ready`, `quarantined`, or `failed`. Image exports get thumb/card variants.
Publish refuses while any active **export** file is not ready.

After adding the marketing app (or any new Celery task module), restart the
worker so it registers the task:

```bash
docker compose --env-file .env -f deployment/compose.dev.yaml restart celery
```

If uploads stay on **Processing** with no worker consuming them, drain the
backlog in-process:

```bash
uv run python manage.py process_marketing_file
# or via docker:
make manage cmd="process_marketing_file"
```

## Administration

Scoped publishers manage drafts at `/operations/marketing-resources`:

- **Scope.** Own only assets whose `owner_office` sits in the actor's grant.
  Out-of-scope ids are 404.
- **Lifecycle.** Stored statuses are `draft` → `published` → `archived`.
  Scheduled is `published` with a future `publish_at`.
- **Concurrency.** Mutations carry `{updated_at}` and return HTTP 409 on
  stale edits.
- **Brand / jurisdiction.** Empty lists mean unrestricted. Non-empty lists
  are filterable on the library.

## Permissions

| Codename | Purpose |
| --- | --- |
| `web.manage_marketing_resources` | Draft, upload, audience, version |
| `web.publish_marketing_resources` | Publish / schedule / archive / restore |
| `web.download_marketing_sources` | Source-file stream |

Default role bundles are in `apps.user.roles` and
`apps.web.permission_catalog`. Marketing staff receive manage and publish
without brokerage-wide admin privileges; audience targeting is still capped
by their grant.
