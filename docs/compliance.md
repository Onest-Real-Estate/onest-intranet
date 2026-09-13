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

Mandatory published policies create one active `PolicyRequirement` (default due
in `COMPLIANCE_ACK_DUE_DAYS`, 14 unless overridden on publish). Audience is the
published `PolicyAudience` set plus jurisdiction. There is no per-user
assignment table.

Readers must open the current version (detail visit records
`PolicyVersionAccess`) and, when ready document-role files exist, download at
least one of those files. They then confirm the disclosure and post checksum +
disclosure version. The acknowledgement row stores the authenticated user, the
immutable policy version, sealed `content_checksum`, `disclosure_version`, a
snapshot of `disclosure_text`, `acknowledged_at`, and request metadata
(`ip`, `userAgent`, `requestId`). Replayed posts return the same row.

**Re-acknowledgement.** `reacknowledge_on_supersede` is read from the
superseded sibling. When it is true (default), every current audience member
must acknowledge the new version. When it is false, people who already
acknowledged or hold an active waiver on a prior family sibling are treated as
satisfied; people who never completed the family still must acknowledge. Old
evidence stays on the old version (`PROTECT`). There is no purge: rows are
retained for the life of the family and after retirement.

**Reminders and action items.** Open mandatory requirements appear on the
dashboard (`apps.compliance.action_items`): pending is high priority, overdue
is critical. Completion is omission. The beat task
`send_policy_ack_reminders` publishes `policy.ack_reminder` until the reader
acknowledges or is waived; deliveries use `dedupe_key`
`policy-ack-reminder:{version_id}:{user_id}` and `is_mandatory=True`. Completing
the requirement expires outstanding reminder rows without deleting them.

**Reporting.** `/operations/compliance/acknowledgements` intersects
`recipients_for` ∩ jurisdiction ∩ the actor's office scope, then applies
filters (`policy`, `office`, `region`, `role`, `dueFrom`, `dueTo`, `status`,
`q`). View permission is `web.view_policy_acknowledgements` **or**
`web.view_compliance` **or** `web.manage_policies`. The operational report
`complianceOpenItems` uses the same open-item query.

**Waivers and corrections.** `web.waive_policy_acknowledgements` is required.
A waiver stores a reason and does not delete acknowledgements. A correction is
append-only (`clerical` or `revoke_waiver`). Revoking a waiver sets
`is_active=False` on the existing row. Django admin cannot delete evidence.

## Notifications

Mandatory published policies also fan out through `apps.notifications` as
`administrative` rows (there is no separate compliance type). Optional
policies stay in the library only.

| Event | Notifies |
| --- | --- |
| `policy.published` | Audience ∩ jurisdiction of a **mandatory** version that is in window, except the publisher and people who already satisfied the family |
| future `effective_at` | Nobody until Celery task `release_effective_mandatory_policies` |
| `policy.ack_reminder` | Overdue mandatory acks that are still required of the reader |

Publish notices are mandatory, high priority, and open `policy_detail`.
Detail is re-checked on every inbox read through `visible_policies` plus
jurisdiction; a reminder fails closed once the reader has acknowledged or
been waived. Mark-all-read cannot clear a mandatory ack.

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
