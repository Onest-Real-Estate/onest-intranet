# Agent Contracts

Brokerage agreements for recipient agents: commercial terms, lifecycle status,
protected PDF artifacts, and immutable issuance snapshots.

Admin authoring (create / validate / preview / issue) and the lifecycle
transition service are documented below. Agent-facing **My Contract** and
**one-click DocuSeal signing** (P1-042) are live.

## Models

| Model | Role |
| --- | --- |
| `ContractTemplate` / `ContractTemplateVersion` | Originating template family and version (`PROTECT`). Field placement lives in DocuSeal Builder (`docuseal_template_id`). |
| `AgentContract` | One agreement version for one recipient at one owning office. Stores issue-time `docuseal_submission_id` for signing reuse. |
| `ContractArtifact` | Protected file (generated/signed PDF, addendum) with SHA-256 checksum. |
| `ContractSigningIntent` | Short-lived recipient ceremony binding (checksum, session, DocuSeal ids). |
| `ContractSignature` | Immutable electronic signature record + signed PDF artifact link. |

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
| `mark_generation_error` / `retry_generation` | sent ↔ generation_error | | Retry re-queues PDF generation |

Concurrency uses `select_for_update(of=("self",))` plus an `expected_version`
token from `updated_at`. Already-at-target retries are no-ops (no duplicate
audit or domain events). Scheduled expiry: Celery task
`apps.contract.tasks.expire_due_contracts` (safe to re-run).

PDF generation after issue runs through Celery
(`generate_contract_pdf` → `apps.contract.pdf_generation`): frozen snapshots and
the published DocuSeal template create a two-role submission (Prefill
auto-completes readonly commercial fields; Agent is reserved for signature).
The Prefill-completed documents become the review `ContractArtifact`, and
`contract.pdf_ready` is emitted once after commit. The same DocuSeal submission
id is stored on the contract for the recipient signing ceremony. Retries are
idempotent on the input fingerprint + checksum. Failures move the contract to
`generation_error` without falsely marking the agreement ready. Authorized
download streams through `agent_contract_artifact_download` (no durable/presigned
URL).

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
`checksum` (SHA-256 hex), `byte_size`, `media_type`, plus generation metadata
(`renderer_version`, `rule_version`, `input_fingerprint`, page/marker facts).
Current generated and signed PDFs are pointed at by nullable FKs on the
contract. Downloads re-check `accessible_contract_queryset` and stream with
`Cache-Control: private, no-store`. Orphan generated objects (never current)
are cleaned by `cleanup_orphan_contract_artifacts`.

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
- `recipient_visible_queryset(user)` / `my_contract_page_payload` — agent
  My Contract (issued+ statuses only)
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

Issuance freezes snapshots and queues `generate_contract_pdf`. Double-submit is
idempotent via lifecycle locks. When the PDF lands, the workspace exposes a
scoped download link. Recipient signing (P1-042) reuses the issue-time DocuSeal
submission rather than creating a one-off PDF submission.

### Contract template administration (DocuSeal Builder)

Operations → Contract Templates:

1. Create a family + draft version.
2. Upload a blank PDF — hub stores it privately and mints a builder JWT with a
   short-lived `document_urls` fetch link (`DOCUSEAL_DOCUMENT_FETCH_BASE`,
   docker default `http://web:8000`). Open-source DocuSeal does **not** expose
   `POST /templates/pdf` (Pro-only); the embedded builder creates the remote
   template on save.
3. Place fields with roles **Prefill** (commercial/party text) and **Agent**
   (signature + date), then Save in the builder so hub stores
   `docuseal_template_id`.
4. Sync fields, map Prefill field names to hub merge sources, generate a
   DocuSeal preview, then publish / activate.

**Embedded builder / form require DocuSeal Pro.** Community
`docuseal/docuseal` serves a DummyBuilder stub at `/js/builder.js` (“Upgrade to
Pro”). Without Pro, the workspace links out to the DocuSeal web UI: create the
template there, paste the template id into the hub, then Sync fields. Signing
similarly opens `/s/<slug>` in a new tab and polls for the webhook record.

Local HTTP DocuSeal must load embed scripts over `http://` (not `https://`);
the hub passes `DOCUSEAL_BASE_URL`'s scheme into the embed wrappers.

DOCX/AcroForm local fill is retired; templates are PDF-only through DocuSeal.

Compose sets `DOCUSEAL_API_URL=http://docuseal:3000` for server API calls while
browsers keep `DOCUSEAL_BASE_URL=http://localhost:3000` for embeds.

# ---------------------------------------------------------------------------
# Self-service My Contract (P1-041)
# ---------------------------------------------------------------------------

Agents open **My Contract** (`/my-contract`, Inertia page `MyContract`). The
recipient is always the authenticated user — the route never accepts an agent
id. Optional `?v=<public_id>` selects another **visible** version in the same
recipient's family; unknown or foreign ids fall back to the current agreement
without disclosing other agents' contracts.

### What the page shows

- Presentation state: `no_contract`, `generating`, `generation_failed`,
  `awaiting_signature`, `signed`, `active`, `expired`, `superseded`,
  `terminated`.
- Frozen dates, office name, contract/version id, sent/viewed/signed stamps.
- Plain-language commission summary from
  `summarize_terms_for_display` (mentor and referral labeled separately).
- Secure PDF preview (inline stream, same-origin framing) plus attachment
  download via the existing artifact delivery path.
- Family/history of superseded agreements and amendments the recipient may
  view.
- Sign CTA when the focused version is signable (`sent`/`viewed` with a
  generated PDF). `capabilities.signingReady` is true when DocuSeal is
  configured (`DOCUSEAL_API_KEY` + `DOCUSEAL_BASE_URL`).

### Viewed status

`mark_viewed` runs through the lifecycle service **once** when the recipient
opens My Contract and the issued PDF is ready — never from a dashboard
preload that only references standing. Retries are idempotent.

### Serialization

Recipient props omit `internalNotes`, admin ids, and other agents' rows.
Commission keys require `web.view_own_commission` (or broader commission
grants). Summary text is informational; the PDF controls on discrepancy.

# ---------------------------------------------------------------------------
# One-click signing ceremony (P1-042)
# ---------------------------------------------------------------------------

Recipients sign only through `/my-contract/sign` (Inertia `MyContractSign`).
Admins cannot use this endpoint on an agent's behalf. Outbound DocuSeal calls
use the official [`docuseal`](https://pypi.org/project/docuseal/) Python package
(`create_submission` against the published template, `get_submission`,
`get_submission_documents`).

1. **Consent gate** — versioned disclosure from
   `apps.contract.signing_disclosure` plus required acknowledgement. The
   checkbox is informed consent, not the electronic signature.
2. **Signing intent** — `POST /my-contract/sign` creates a short-lived
   `ContractSigningIntent` bound to recipient, contract version token,
   generated PDF checksum, and session hash; then reuses the issue-time
   DocuSeal submission's Agent submitter embed URL (`send_email=false`).
3. **Embed** — DocuSeal form via `@docuseal/react` using the server
   `embedSrc`.
4. **Completion** — DocuSeal webhook `POST /webhooks/docuseal/contracts`
   (HMAC `X-Docuseal-Signature`) downloads the signed PDF, attaches
   `signed_pdf`, writes immutable `ContractSignature`, consumes the intent,
   and runs lifecycle `mark_signed`. Client `onComplete` only polls
   `/my-contract/sign/status` until the signature row exists — success UI
   never trusts the browser event alone.

Replay, duplicate webhooks, and concurrent completes are idempotent (one
signature, one signed artifact, one `contract.signed` effect). Stale version,
expired intent, checksum drift, or non-signable status return recovery copy.

Network metadata retained on the signature is minimized to hashed IP and
hashed truncated user agent from intent start. Disclosure version is stored
with the signature. Legal must approve disclosure copy before production;
bump `DISCLOSURE_VERSION` when text changes.

### Ops

- Local DocuSeal: `make up`, open `http://localhost:${DOCUSEAL_PORT:-3000}`,
  create an API key, set `DOCUSEAL_API_KEY` and `DOCUSEAL_USER_EMAIL` (the
  DocuSeal admin that owns the key) in `.env`. Compose sets
  `DOCUSEAL_API_URL=http://docuseal:3000` for server-side calls (browser embeds
  still use `DOCUSEAL_BASE_URL=http://localhost:3000`). Generate a long random
  `DOCUSEAL_WEBHOOK_SECRET` yourself (self-hosted has no webhook-secret UI) and
  paste this URL into DocuSeal → Settings → Webhooks (enable `form.completed`):

  `http://host.docker.internal:8000/webhooks/docuseal/contracts?token=<DOCUSEAL_WEBHOOK_SECRET>`

  From the host (not Docker networking), use `http://localhost:8000/...` instead.
  Completion still downloads the signed PDF via the DocuSeal API, so a guessed
  submission id alone cannot invent a signature without a real completed form.
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
