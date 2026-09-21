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

## Retention

Soft-archive only. Closed deals may move to Archived for retention; rows and
assignments remain queryable under scope. Hard delete and automated purge are
out of scope for #99.

## Related

- [`docs/permissions.md`](permissions.md) — capability catalog
- [`docs/roles.md`](roles.md) — TC / regional TC scopes
- [`docs/agent-contracts.md`](agent-contracts.md) — high-stakes lifecycle pattern
- Issues #101–#108 — workspace through closure notifications
- Issue #100 — scoped create workflow (this document)