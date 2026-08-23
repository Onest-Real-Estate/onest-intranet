# Activity timeline

Reusable, permission-aware activity projection for records across the hub
(users today; contracts, transactions, leads, reservations, and support as
those domains land).

## Source of truth

Timelines **project** append-only `AuditEvent` rows. They are not a second
mutable log. Domain-event replay must not create duplicate audit rows; the
projection deduplicates by audit event primary key.

## Contract

Each entry carries:

| Field | Meaning |
| --- | --- |
| `id` | Stable audit event UUID (dedup key) |
| `eventType` | Audit action name |
| `summary` | Human-readable action |
| `occurredAt` / `occurredAtDisplay` | Instant + brokerage-timezone display |
| `actorLabel` / `actorKind` | Who acted (`user` / `system` / `service` / …) |
| `target` / `related` | Record refs |
| `source` | Origin channel (`app`, …) |
| `visibility` | `full` / `redacted` / `summary` |
| `typedAction` | Optional machine action for icons/filters |
| `files` | Safe file pointers (id + name), never permanent public URLs |
| `changeSummary` | Field names (values only when permitted) |
| `metadata` | Scrubbed leftovers |

Pagination uses an opaque keyset cursor over `(-occurred_at, -id)`.

## Permissions (keep separate)

| Capability | Purpose |
| --- | --- |
| `audit.can_view_activity_timeline` | User-facing timeline API / embeds |
| `audit.can_view_audit_events` | Raw audit log query/export |

Holding one never implies the other. Direct APIs still require **record-level**
authorization (for users: `administered_user_queryset`). Out-of-scope or unknown
ids answer **404**, not an empty timeline that could be used to probe.

Sensitive field values are redacted unless the viewer holds the paired field
permission (see `apps.audit.activity.redaction`).

## Surfaces

- **API:** `GET /activity/<record_type>/<record_id>?cursor=&limit=`
  (`activity_timeline`), JSON, camelCase payload.
- **Embed:** `project_user_administration_history` powers the user-administration
  recent-activity panel without re-checking the timeline permission (record
  access already enforced).
- **UI:** `frontend/components/activity/ActivityTimeline.tsx` — loading, empty,
  error, load-more, system actors, files, axe-covered.

## Adding a domain

1. Register actions in `apps/audit/activity/mappers.py`.
2. Add a `RecordTypeConfig` in `apps/audit/activity/access.py` with target types
   and the domain view permission.
3. Emit `AuditEvent`s from the domain with the correct `target_type` /
   `target_id`.
4. Cover mapping, redaction, scope denial, and cursor ordering in
   `apps/audit/tests/test_activity.py`.
