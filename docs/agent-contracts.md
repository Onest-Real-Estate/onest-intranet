# Agent Contracts

Brokerage agreements for recipient agents: commercial terms, lifecycle status,
protected PDF artifacts, and immutable issuance snapshots.

Product authoring, signing, and state-machine transitions land in later issues.
This document covers the **data model and query services** shipped with the
foundational schema.

## Models

| Model | Role |
| --- | --- |
| `ContractTemplate` / `ContractTemplateVersion` | Originating template family and version (`PROTECT`). Full template admin is a separate issue. |
| `AgentContract` | One agreement version for one recipient at one owning office. |
| `ContractArtifact` | Protected file (generated/signed PDF, addendum) with SHA-256 checksum. |

`AgentContract.public_id` (UUID) is the client-facing identity. The integer PK
is internal. Family history uses shared `family_id` + monotonic
`version_number`, plus optional `root_agreement` / `supersedes` / `amends`
links so replacements never overwrite signed rows.

### Status codes

Stable machine codes in `apps.contract.statuses.ContractStatus`:

`draft` → `ready_for_review` → `sent` → `viewed` → `signed` → `active`

Terminal / alternate: `superseded`, `expired`, `terminated`,
`generation_error`.

Allowed transitions are enforced by a later lifecycle service — the model
stores codes and timestamps only.

### Commercial terms

All money and percentage fields are `DecimalField` (no floats):

- Percentages: max 6 digits, 3 decimal places, unit **percent** (0–100).
- Money: max 12 digits, 2 decimal places, currency **USD**, nonnegative.

Mentor and referral are **separate structured blocks** (percent, fixed amount,
cap, basis, payee, notes) so calculation services cannot conflate them.

Agent and office splits are both-or-neither and must sum to 100 when set.

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

## Query services

- `recipient_contract_queryset(user)` — self-only
- `scoped_contract_queryset(actor)` — office/region/company from effective access
- `create_draft_contract(...)` — validates active recipient, active assignable
  office, in-scope assignment, decimal bounds, and published template version
- `agent_contract_status(user)` / `contract_status_options()` — directory and
  admin standing (wired from `apps.user` via `apps.contract.services`)

Cross-scope create attempts raise `ValidationError`. Missing manage permission
raises `PermissionDenied`.

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
