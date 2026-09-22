# Transactions

Owning app: `apps/transactions`.

Foundational real-estate deal domain for Buy, Sell, and Rent workflows,
including Dual Representation as a representation posture. This document is
the contract for the data model, scope, field projection, and enforced
lifecycle shipped in [#99](https://github.com/Onest-Real-Estate/onest/issues/99).
Creation UI, workspace, documents, checklists, commissions, and notification
producers are later epic issues (#101–#108). The guided create workflow in
[#100](https://github.com/Onest-Real-Estate/onest/issues/100) is documented
below. CRM property/client foreign keys arrive with the CRM stack (#109+);
until then the deal stores snapshots and opaque external references.

## Permissions

| Codename | Opens |
| --- | --- |
| `web.view_transactions` | Scoped list/detail and ops nav destination |
| `web.manage_transactions` | Create drafts, edit non-status fields, mutate assignments |
| `web.create_own_transactions` | Agents open a draft as primary agent in their home office |
| `web.transition_transactions` | Lifecycle moves through the service |
| `transactions.view_transaction_financials` | `listPrice` / `contractPrice` in serialization |
| `transactions.view_transaction_clients` | Client snapshot PII in serialization |

Holding a manage grant does **not** imply financial or client field grants.
Frontend hiding is never authorization.

Branch managers hold `web.manage_transactions` (office-scoped). Realtors hold
`web.create_own_transactions` without the full manage grant.

## Scope

`Transaction.objects.for_reader(user, access=…)` is the only visibility gate.
Call it before count, serialize, search, or background delivery.

1. Anonymous → empty
2. Superuser or company-wide effective access → all rows
3. Else office / region keys on `office`, **or** active `TransactionAssignment`
   for the user, **or** convenience FKs `primary_agent` / `coordinator`

`assigned_record` role scope contributes permissions without expanding office
reach; personal assignment membership is what lets a TC or agent see their
deals outside office expansion.

## Model

- **Identity:** `public_id` (UUID), human `reference` (`TXN-000412`)
- **Classification:** `transaction_type` (`buy` / `sell` / `rent`),
  `representation_type` (`buyer` / `seller` / `landlord` / `tenant` / `dual`)
- **Ownership:** `office` (`PROTECT`), indexed with status
- **People:** `primary_agent` / `coordinator` FKs (`SET_NULL`) mirrored from
  authoritative `TransactionAssignment` rows
- **Property / clients:** JSON snapshots + opaque external refs (no CRM FK yet)
- **Money:** `list_price` / `contract_price` via Decimal USD helpers (12/2)
- **Dates:** `acceptance_date`, `closing_date`; lifecycle timestamps per status
- **Vendors:** opaque `lender_ref` / `title_ref` / `referral_ref`
- **Idempotency:** nullable unique `submission_key` stamped on prepare
- **Archive:** soft only — `archived_at` / `archived_by` / `archive_reason`.
  No hard delete of deal history.

## Create workflow (#100)

Routes: `transaction_new`, `transaction_draft_save`, `transaction_prepare`,
`transaction_people_search`, `transaction_workspace`. Services live in
`apps.transactions.creation`.

### Creator matrix

| Actor | Gate | Hard rules |
| --- | --- | --- |
| Manage grant (admins, RM, TC, branch manager) | `web.manage_transactions` | Office and people must sit in effective scope |
| Agent | `web.create_own_transactions` | `primary_agent=self`, `office=home`; crafted expansions refused |
| Anyone else | — | 403 |

Status is never accepted from the client. Draft save allows incomplete prepare
fields. Prepare validates `REQUIRED_FIELDS[preparing]` plus a street address,
then transitions Draft → Preparing under a client `submissionKey`.

### Server-owned schema

`build_create_schema` returns camelCase sections, required markers, locked
fields, and type/representation options. Type↔representation pairs are
allowlisted (buy→buyer/dual, sell→seller/dual, rent→landlord/tenant/dual).
The UI mirrors required flags; the server remains authoritative.

### Duplicates

`find_duplicate_matches` searches only `for_reader` rows by MLS (casefold),
normalized address, and client email/name. Visible hits expose `reference` +
`publicId` only. Out-of-scope candidates are never acknowledged. Prepare
returns 409 with those matches until `confirmedDuplicate` is set.

### Idempotency

The same `submission_key` returns the same transaction without a second create
audit or prepare transition event.

### Workspace shell

`TransactionWorkspace` is a read-mostly confirmation page for #100. Parties,
documents, tasks, and compliance expand in #101+.

## Workspace (#101)

Routes: `my_transactions`, `admin_transactions` (ops list),
`transaction_workspace?section=`, plus section POST saves
(`transaction_party_save`, `transaction_property_save`,
`transaction_key_date_save`, `transaction_note_save`,
`transaction_assignment_save`).

### Sections

Live URL-driven sections: Overview, Parties, Property, Dates, Notes,
Assignments, Activity, Documents, Signatures. Stub sections (Checklist, Tasks,
Commission, Compliance) render “coming soon” and stay non-writable until later
epics.

### Models

| Model | Purpose |
| --- | --- |
| `TransactionParty` | Structured party with role/kind/contact, primary-per-role uniqueness, frozen `snapshot` JSON |
| `TransactionPropertySnapshot` | Immutable history row on material property/MLS changes |
| `TransactionKeyDate` | Typed aware datetime + timezone; soft-supersede via `ended_at` / `superseded_by` |
| `TransactionNote` | Body + visibility enum; never one unrestricted stream |
| `TransactionDocument` | Deal document package (category, requirement, retention, current version) |
| `TransactionDocumentVersion` | Immutable file revision with processing/lock/signature/compliance state |
| `TransactionDocumentReviewComment` | Version-bound review note with visibility + resolution |

Concurrency: every workspace write bumps `Transaction.updated_at`. Clients post
`expectedVersion` (ISO µs from `updated_at`); mismatch → **409** with form
error (contract pattern).

### Note visibility mapping

No new permission catalog entries:

| Visibility | Who sees it |
| --- | --- |
| `team` | Anyone who can `for_reader` the deal |
| `broker_compliance` | Holders of `web.manage_transactions` or `web.transition_transactions` |
| `private_author` | Author only |

Contact fields on parties reuse `transactions.view_transaction_clients`.
Financial fields keep `transactions.view_transaction_financials`.

### Documents (#102 / P1-085)

Routes (workspace write + file read policies):
`transaction_document_upload`, `…_classify`, `…_revision`, `…_retire`,
`…_retry`, `…_lock`, `…_comment_save` / `…_resolve` / `…_end`,
`transaction_document_download`, `transaction_document_preview`.

| Concern | Rule |
| --- | --- |
| Scope | Every list/serialize/stream path starts from `for_reader` |
| Upload | Extension + sniffed MIME + size via `apps.transactions.media`; UUID keys under `transactions/` on `private_storage` |
| Processing | Celery `process_transaction_document_version`: checksum verify → `ready` / `quarantined` / `failed`. Images are sanitized. |
| Current | After READY, highest `version_number` then `pk` among ready active versions; quarantined/failed never become current |
| Lock | `signed` / `approved` (or `locked_at`) refuse replace/delete/retire of that version; new revisions still allowed |
| Delivery | Hub stream only (`Cache-Control: private, no-store`); ordinary readers get the **current** ready version; managers may history-stream. Guessed ids → 404 |
| Reviews | Version-bound comments reuse note visibility (`team` / `broker_compliance` / `private_author`) plus open/resolved |

Compliance review queue, correction workflow, and Ready-to-Close gating stay in
[#106](https://github.com/Onest-Real-Estate/onest/issues/106) — this epic only
ships lock fields and review comments those flows will drive.

Orphan cleanup: `manage.py sweep_transaction_documents` (abandoned pending /
failed older than 14 days + unreferenced storage keys past a 6h grace).

### Signatures (#103 / P1-086)

Hub-native multi-party packages on locked PDF document versions. Owning code:
`apps/transactions/signing/`. Workspace section `signatures` is live.

| Model | Role |
| --- | --- |
| `SignaturePackage` | Draft→sent→in_progress→completed (or declined/expired/cancelled) |
| `SignaturePackageDocument` | Frozen `TransactionDocumentVersion` + source checksum |
| `SignaturePackageSigner` | Role, contact, hub/email delivery, routing order, status |
| `SignaturePackageField` | Page coordinates keyed to signer public id |
| `SignatureAccessToken` | Hashed magic-link token (raw never stored) |
| `SignatureSigningIntent` / `SignatureRecord` | Ceremony bind + immutable evidence |
| `SignatureArtifact` | Write-once signed PDF per document + package CoC |

**Routing.** `ordered`: only the lowest unsigned `routing_order` cohort may
sign. `parallel`: every invited signer may sign. Enforced on start/complete
under `select_for_update(of=("self",))`.

**Delivery.** Hub users open `/transactions/sign/<package>/` after SSO.
External parties open `/sign/p/<token>/` (public policy; token authenticity is
the gate). Signers see only their eligible fields.

**Finalize.** Celery `finalize_signature_package` stamps appearances, appends
CoC, seals with the org PKCS#12 (`CONTRACT_SIGNING_CERT_*`), stores artifacts,
and locks source versions at `signature_status=signed`. Idempotent.

**Reminders / expiry.** Beat tasks `send_signature_package_reminders` and
`expire_signature_packages`; cadence `TRANSACTION_SIGNATURE_REMINDER_DAYS`.
Domain events `transaction.signature_package_*` / `transaction.signature_*`
feed notifications for Hub recipients; email invites/reminders cover magic-link
signers.

Authoring requires `web.manage_transactions` inside `for_reader` scope. No
presigned artifact URLs — Hub stream only.

### Activity

Audit `target_type` is `transaction.transaction` (legacy
`transactions.transaction` still projects). Timeline embeds on the Activity
section and Overview teaser via `project_record_activity`; out-of-scope ids
404 through `scoped_transaction_queryset`.

## Assignments

`TransactionAssignment` records `(transaction, user, role)` with `ended_at`
null while active. Roles: `primary_agent`, `co_agent`, `coordinator`,
`compliance_reviewer`. Partial unique constraints enforce one active row per
`(transaction, user, role)` and at most one active primary / coordinator per
deal. Ending an assignment is audited; it never deletes history.

## Lifecycle

Happy path:

```
Draft → Preparing → Under Contract → Pending → Compliance Review
  → Ready to Close → Closed → Archived
```

Side paths:

- **On Hold** from Preparing / Under Contract / Pending / Compliance Review /
  Ready to Close; resume returns to `held_from_status`
- **Cancelled** from Draft / Preparing
- **Withdrawn** from Under Contract / Pending
- **Terminated** from Under Contract through Ready to Close

`apps.transactions.lifecycle.transition` is the only writer of `status`:

1. Authorize against the stored row
2. `select_for_update(of=("self",))` (no nullable `select_related` joins)
3. `expected_status` mismatch → `ConcurrentUpdate`
4. Same-target retry → idempotent no-op (no second audit/event)
5. Preconditions from `REQUIRED_FIELDS[target]`
6. **Closed** requires `compliance_approved_at` and `closing_date`
7. **Archived** only from Closed
8. Entering Ready to Close stamps `compliance_approved_at` (checklist gate
   refined in #106)
9. `allow_status_write()` context; model `save` and queryset `update(status=…)`
   refuse unguarded status edits
10. Audit (`log_on_commit`) + domain events after commit

Assignee-safe moves (`by_assignee`) allow the active primary agent or
coordinator (or any active assignment) to advance early pipeline steps and
place/resume holds without the transition grant. Approve-for-closing, close,
archive, and terminate require an explicit transition/manage grant.

## Field projection

`serialize_transaction` returns camelCase presentation data. Financial and
client keys are **omitted** (not null) without the matching field permission.
Internal primary keys are never exposed; office uses `stableKey`.

## Events

Registered in `apps/audit/catalog.py`:

- `transaction.created`
- `transaction.status_changed`
- `transaction.archived`
- `transaction.assignment_changed`
- `transaction.updated` (workspace field writes; allowlisted metadata only)

## Retention

Soft-archive only for deals. Closed deals may move to Archived; rows and
assignments remain queryable under scope. Hard delete and automated purge of
deal history are out of scope for #99.

Document packages carry `retention_policy` / `retain_until` metadata. Version
bytes are soft-retained (locked/approved versions cannot be deleted through
normal paths). Orphan storage cleanup only removes abandoned pending/failed
uploads and unreferenced keys — never ready history.

## Related

- [`docs/permissions.md`](permissions.md) — capability catalog
- [`docs/roles.md`](roles.md) — TC / regional TC scopes
- [`docs/agent-contracts.md`](agent-contracts.md) — high-stakes lifecycle pattern
- [`docs/documents-forms.md`](documents-forms.md) — brokerage forms library (not deal attachments)
- Issues #101–#108 — workspace through closure notifications
- Issue #100 — scoped create workflow
- Issue #102 — deal document management (this document)
- Issue #106 — compliance review queue that locks approved evidence