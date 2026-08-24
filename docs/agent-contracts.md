# Agent Contracts

Brokerage agreements for recipient agents: commercial terms, lifecycle status,
protected PDF artifacts, and immutable issuance snapshots.

Admin authoring (create / validate / preview / issue) and the lifecycle
transition service are documented below. Agent-facing signing UI lands in a
later issue.

## Models

| Model | Role |
| --- | --- |
| `ContractTemplate` / `ContractTemplateVersion` | Originating template family and version (`PROTECT`). Full template admin is a separate issue. |
| `AgentContract` | One agreement version for one recipient at one owning office. |
| `ContractArtifact` | Protected file (generated/signed PDF, addendum) with SHA-256 checksum. |
| `CommissionCalculation` | Immutable mentor/referral worksheet for one GCI input (rule version + snapshots). |

`AgentContract.public_id` (UUID) is the client-facing identity. The integer PK
is internal. Family history uses shared `family_id` + monotonic
`version_number`, plus optional `root_agreement` / `supersedes` / `amends`
links so replacements never overwrite signed rows.

### Status codes

Stable machine codes in `apps.contract.statuses.ContractStatus`:

`draft` → `ready_for_review` → `sent` → `viewed` → `signed` → `active`

Terminal / alternate: `superseded`, `expired`, `terminated`,
`generation_error`.

All status changes go through `apps.contract.lifecycle.transition`. The model
refuses unguarded `status` writes. Django admin keeps status and lifecycle
timestamps read-only.

| Action | From | To | Notes |
| --- | --- | --- | --- |
| `submit_for_review` | draft | ready_for_review | Validates terms; refreshes `terms_snapshot` |
| `reopen` | ready_for_review | draft | |
| `issue` | ready_for_review | sent | Requires `confirmed=True`; re-validates sources; freezes snapshots; queues PDF stub |
| `mark_viewed` | sent | viewed | Recipient or manage |
| `mark_signed` | sent / viewed | signed | |
| `activate` | signed | active | Supersedes prior active for same recipient |
| `supersede` / `terminate` / `expire` | (see service) | terminal | High-impact actions need confirmation where configured |
| `mark_generation_error` / `retry_generation` | sent ↔ generation_error | | Retry re-queues PDF stub |

Concurrency uses `select_for_update(of=("self",))` plus an `expected_version`
token from `updated_at`. Already-at-target retries are no-ops (no duplicate
audit or domain events). Scheduled expiry: Celery task
`apps.contract.tasks.expire_due_contracts` (safe to re-run).

PDF generation after issue is currently a **stub**
(`generate_contract_pdf` returns `"stubbed"`) until the dedicated PDF pipeline
issue lands.

### Commercial terms

All money and percentage fields are `DecimalField` (no floats):

- Percentages: max 6 digits, 3 decimal places, unit **percent** (0–100).
- Money: max 12 digits, 2 decimal places, currency **USD**, nonnegative.

Mentor and referral are **separate structured blocks** (percent, fixed amount,
cap, basis, payee, notes) so calculation services cannot conflate them.
Financial mentor/referral terms require both a supported `basis` and a `payee`.

Agent and office splits are both-or-neither and must sum to 100 when set.

Each contract stores `calculation_rule_version` (default `1.0.0`). Issued
contracts always calculate under that frozen version; callers cannot pass a
newer policy to reinterpret historical terms.

### Snapshots

At draft creation the service freezes:

- `party_snapshot` — legal/display name, license, agent identifier
- `office_snapshot` — office identity and address
- `terms_snapshot` — rendered commercial terms

Later edits to the user or office row do **not** rewrite these JSON blobs.

### Artifacts

Files use `private_storage` (no public URL). Each artifact carries `kind`,
`checksum` (SHA-256 hex), `byte_size`, and `media_type`. Current generated and
signed PDFs are pointed at by nullable FKs on the contract.

## Permissions

| Codename | Purpose |
| --- | --- |
| `web.view_agent_contracts` | Metadata / standing for people in scope |
| `contract.manage_agent_contracts` | Create/edit drafts in scope |
| `contract.view_commission_terms` | Commercial terms for scoped contracts |
| `contract.view_internal_notes` | Broker-only notes |
| `web.view_own_commission` | Recipient may read **their own** commercial terms |

Serialization (`serialize_contract`) **omits** gated keys rather than nulling
them.

## Mentor / referral commission calculations

Pure math lives in `apps.contract.calculations` (`Decimal` only — never float).
Persistence and scope checks live in `apps.contract.calculation_service`.

### Rule version `1.0.0` (brokerage/legal sign-off)

Documented in `apps.contract.calculations.rules`. Summary:

| Step | Behavior |
| --- | --- |
| Rounding | `ROUND_HALF_EVEN` to cents (`0.01`) at every money step; percents to `0.001` |
| Currency | USD only in v1 |
| Order | Validate → quantize GCI → agent/office split → transaction fee → **mentor** → **referral** (parallel bases) → agent net |
| Parallelism | Mentor and referral each resolve their own basis from shared intermediates; neither reduces the other's base |

### Supported bases (stable codes)

| Code | Meaning |
| --- | --- |
| `gross_commission` | Gross commission income (GCI) |
| `agent_side_before_fees` | Agent share of GCI before transaction fee |
| `agent_side_after_fees` | Agent share after transaction fee |
| `fixed_only` | Fixed amount only (percent must be unset) |

Unknown bases, missing payees, out-of-range percents, negative GCI, conflicting
`fixed_only`+percent, agent-side bases without a split, and deductions that
drive agent net negative all **fail validation** — the engine never guesses.

### Persistence

`persist_commission_calculation` stores input/terms/intermediate/result
snapshots, explanation lines (mentor and referral labeled separately), money
totals, and a SHA-256 fingerprint of rule+input+terms. Identical worksheets
reuse the same row (idempotent). Changing `CURRENT_RULE_VERSION` later does
not recalculate issued contracts; new drafts pick up the new default.

Preview helpers and PDF/commission UIs should share
`serialize_commission_calculation` / `summarize_terms_for_display` so labels
stay consistent.

## Query services

- `recipient_contract_queryset(user)` — self-only
- `scoped_contract_queryset(actor)` — office/region/company from effective access
- `create_draft_contract(...)` — validates active recipient, active assignable
  office, in-scope assignment, decimal bounds, published **and applicable**
  template version
- `apps.contract.administration` — admin authoring: `update_draft_contract`,
  `applicable_template_versions`, `search_contract_recipients`, commercial and
  agreement preview, `issue_contract` (wraps lifecycle `issue`)
- `agent_contract_status(user)` / `contract_status_options()` — directory and
  admin standing (wired from `apps.user` via `apps.contract.services`)

Cross-scope create attempts raise `ValidationError`. Missing manage permission
raises `PermissionDenied`.

### Admin authoring UI

Operations → Agent Contracts (`/operations/agent-contracts`):

1. List scoped contracts (`web.view_agent_contracts`).
2. New draft: scoped agent typeahead + applicable template picker
   (`contract.manage_agent_contracts`).
3. Workspace: multi-section terms, commercial breakdown, agreement preview,
   submit-for-review / reopen / confirm-issue.

Issuance freezes snapshots and queues `generate_contract_pdf` (stub until the
PDF pipeline issue). Double-submit is idempotent via lifecycle locks.

## Constraints and indexes

Database constraints cover date ranges, nonnegative/bounded terms, both-or-
neither splits, one **active** contract per recipient, and unique
`(family_id, version_number)`. Indexes cover recipient/status, office/status,
status/effective date, and family/version.

Referenced agents, offices, templates, and artifacts use `PROTECT` (or
archival pointers) so history cannot be deleted out from under a contract.

## Related

- [agent-administration.md](agent-administration.md) — contract status is
  derived, never typed into the profile
- [permissions.md](permissions.md) — catalog and field-level omission
- [authorization.md](authorization.md) — scope helpers
