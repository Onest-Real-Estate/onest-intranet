# Policies & Compliance

The Policies & Compliance library at `/policies-compliance` is the consumer
surface for brokerage manuals, advertising/fair-housing guidance, agency rules,
retention, state requirements, disclosures, and transaction compliance
resources. Every read path — the library, detail page, and protected document
download — uses the same audience and jurisdiction predicates in
`apps.compliance.audience` and `apps.compliance.services`.

Administration lives at `/operations/compliance` behind `web.manage_policies`.
Approval uses `web.approve_policies`. Publishing and retirement use
`web.publish_policies`. Acknowledgement reporting uses
`web.view_compliance` / `web.view_policy_acknowledgements`; waivers use
`web.waive_policy_acknowledgements`.

## Visibility

1. Audience match (OR union across selectors)
2. `published` status and effective/expiry window
3. Jurisdiction: empty `jurisdiction_state_codes` means all states; otherwise
   the reader's `license_state` or primary office `state` must intersect
4. One **current** live row per `version_family` (highest `version_number` that
   is published and in-window)

Draft, historical, and out-of-scope policies return **404**, not 403, on
consumer routes.

## Audience

Selectors are **OR**. Kinds match announcements, training, and marketing:

| Kind | Reaches |
| --- | --- |
| company | Everyone |
| role | Live holders of that role code |
| region | Primary office under that node |
| office | Exact primary office |
| user | Named person |

Publishers must own every selector (`assert_can_target`). Company-wide
targeting requires company-wide access.

## Versioning and lifecycle

Each policy carries `version_family` + `version_number`. Editable statuses are
`draft`, `in_review`, and `approved`. **Published**, **superseded**, and
**retired** rows are immutable — change content by **Duplicate as new
version**.

Lifecycle:

| Action | From → To | Permission |
| --- | --- | --- |
| submit | draft → in_review | `web.manage_policies` |
| approve | in_review → approved | `web.approve_policies` |
| publish | approved → published | `web.publish_policies` |
| retire | published → retired | `web.publish_policies` |
| return_to_draft | in_review/approved → draft | `web.manage_policies` |

On publish the hub seals `content_checksum` from body + ready document file
checksums, supersedes prior published siblings in the family, and creates a
mandatory acknowledgement requirement when `is_mandatory` is true.

Consumer detail URLs for a superseded version **redirect** to the current live
sibling when the reader still matches audience and jurisdiction; otherwise they
404. The operations console keeps full history.

## Acknowledgements

Mandatory published policies create a `PolicyRequirement` (default due in 14
days, overridable via `COMPLIANCE_ACK_DUE_DAYS`). Readers acknowledge on the
detail page with checksum + disclosure version binding. Acknowledgements are
idempotent per `(user, policy_version)`. Scoped waivers are admin-only with a
required reason.

Overdue mandatory acks surface as dashboard action items
(`apps.compliance.action_items`) and optional reminder notifications via Celery
task `send_policy_ack_reminders`.

## Files

Document files use private storage and are streamed through
`policy_document_file` — never public or long-lived S3 URLs. Upload and remove
are admin-only and re-check publication scope. Publish refuses while any active
document file is still processing or quarantined/failed.

## Audit

Lifecycle transitions emit `policy.submitted`, `policy.approved`,
`policy.published`, `policy.superseded`, and `policy.retired` domain events
plus durable audit rows. Denied manage attempts log
`security.compliance.denied`.
