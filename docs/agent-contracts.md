# Agent Contracts

Brokerage agreements for recipient agents: commercial terms, lifecycle status,
protected PDF artifacts, and immutable issuance snapshots.

Admin authoring (create / validate / preview / issue) and the lifecycle
transition service are documented below. Agent-facing **My Contract** and
**Hub-native one-click signing** (P1-042) are live.

## Models

| Model | Role |
| --- | --- |
| `ContractTemplate` / `ContractTemplateVersion` | Originating template family and version (`PROTECT`). Hub `field_layout` drives Prefill fill plus **Company** and **Agent** signature/date placement. Legacy DocuSeal id columns may still exist on historical rows. |
| `AgentContract` | One agreement version for one recipient at one owning office. Named `company_signatory` (required at issue) and `company_signed_at` gate agent release. |
| `ContractArtifact` | Protected file (generated/signed PDF, certificate of completion, addendum) with SHA-256 checksum. |
| `ContractSigningIntent` | Short-lived ceremony binding (checksum, session, disclosure version) with `signer_role` (`Agent` \| `Company`). |
| `ContractSignature` | Immutable electronic signature per `(contract, signer_role)`; agent ceremony triggers async final signed PDF + CoC. |

`AgentContract.public_id` (UUID) is the client-facing identity. The integer PK
is internal. Family history uses shared `family_id` + monotonic
`version_number`, plus `change_kind` (`original` / `amendment` / `addendum` /
`replacement`) and optional `root_agreement` / `supersedes` / `amends` links
so replacements and amendments never overwrite signed rows. Amendments carry a
`change_summary` legal narrative; commercial fields are still prepopulated in
full so calculations and PDFs stay self-contained per version.

### Versioning and amendments (P1-045)

Signed, active, and other issued statuses freeze legal/financial fields,
snapshots, and family links on the model. Artifacts are write-once after
create. To change terms, admins start **Create amendment** or **Create
replacement** from an eligible signed/active in-scope contract:

1. Service validates eligibility (no open pipeline sibling, no cycles, valid
   base status) and locks the family for collision-safe `version_number`
   allocation.
2. A new **draft** is created in the same family, prepopulated from the base
   — never bound to the signed row's mutable form.
3. Workspace shows a structured before/after term comparison and effective-date
   note before issue.
4. Activating a replacement (or any new governing version) supersedes the prior
   active row atomically without deleting it, its artifacts, or its audit
   history.

Governing terms for display are the focused version's own frozen
`terms_snapshot`. When the row is `active`, it is the currently governing
agreement; history labels mark base / amendment / replacement and
supersession.

### Status codes

Stable machine codes in `apps.contract.statuses.ContractStatus`:

`draft` → `ready_for_review` → `awaiting_company_signature` → `sent` →
`viewed` → `signed` → `active`

Terminal / alternate: `superseded`, `expired`, `terminated`,
`generation_error`.

All status changes go through `apps.contract.lifecycle.transition`. The model
refuses unguarded `status` writes. Django admin keeps status and lifecycle
timestamps read-only.

| Action | From | To | Notes |
| --- | --- | --- | --- |
| `submit_for_review` | draft | ready_for_review | Validates terms; refreshes `terms_snapshot` |
| `reopen` | ready_for_review | draft | |
| `issue` | ready_for_review | awaiting_company_signature | Requires `confirmed=True` + named `company_signatory`; freezes snapshots (incl. `companySignatory`); queues PDF; emails / notifies the officer |
| `mark_company_signed` | awaiting_company_signature | sent | Named officer only (via company ceremony); sets `company_signed_at` / `sent_at`; invites the agent |
| `mark_viewed` | sent | viewed | Recipient or manage |
| `mark_signed` | sent / viewed | signed | Agent ceremony or manager record |
| `activate` | signed | active | Supersedes prior active for same recipient |
| `supersede` / `terminate` / `expire` | (see service) | terminal | High-impact actions need confirmation where configured |
| `mark_generation_error` / `retry_generation` | awaiting_company_signature or sent ↔ generation_error | | Retry resumes at awaiting-company or sent based on `company_signed_at` |

Concurrency uses `select_for_update(of=("self",))` plus an `expected_version`
token from `updated_at`. Already-at-target retries are no-ops (no duplicate
audit or domain events). Scheduled expiry: Celery task
`apps.contract.tasks.expire_due_contracts` (safe to re-run).

**Company countersign (company-first).** After issue, only the named
`company_signatory` may complete `/operations/agent-contracts/<uuid>/company-sign`.
Publishable templates require ≥1 Company signature+date and ≥1 Agent
signature+date; Prefill never carries signature/initials. PDF generation may
run while awaiting company signature; the agent signing invite and
`contract.pdf_ready` agent notification wait until status is `sent`. Final
signed PDF stamps Company then Agent appearances, appends a CoC that lists both
signers, then applies the org PKCS#12 seal.

PDF generation after issue runs through Celery
(`generate_contract_pdf` → `apps.contract.pdf_generation`): frozen snapshots and
the template `field_layout` fill Prefill regions onto the blank PDF with pypdf /
reportlab. The filled PDF becomes the review `ContractArtifact`. After company
signing releases the contract to `sent`, Hub sends the signing-invite email to
the recipient (and emits `contract.pdf_ready` for the agent only when status is
already `sent`). Lifecycle emails / notifications:

| Event | Recipients | Mandatory |
| --- | --- | --- |
| `contract.awaiting_company_signature` | Named company signatory | Yes |
| `contract.issued` / `pdf_ready` (status `sent`) / lifecycle | Agent | Yes |
| `contract.viewed` | Operational staff (creator + scoped managers) | No |
| `contract.signed` | Agent + staff | Agent yes / staff no |
| `contract.generation_error` | Operational staff | Yes |
| `contract.signature_reminder` | Agent (cadence days) | Yes |
| `contract.expiration_warning` | Agent + staff | Agent yes / staff no |

Signature reminders and expiration warnings are published by Celery beat tasks
(`send_contract_signature_reminders`, `send_contract_expiration_warnings`) which
re-check status before emitting. Signing, activation, supersession, termination,
and expiry expire outstanding signature-reminder notifications so they stop
appearing and are suppressed on push channels. Cadence defaults:
`CONTRACT_SIGNATURE_REMINDER_DAYS = (3, 7, 14)`,
`CONTRACT_EXPIRATION_WARNING_DAYS = (30, 14, 7)`.
Retries are idempotent on the input fingerprint + checksum. Failures move the
contract to `generation_error` without falsely marking the agreement ready.
Authorized download streams through `agent_contract_artifact_download` (no
durable/presigned URL).

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
contract. Signed PDFs are write-once: application attach, model `save`, and
Django admin refuse replace/delete. Downloads re-check
`accessible_contract_queryset` and stream with `Cache-Control: private,
no-store`. Orphan generated objects (never current) are cleaned by
`cleanup_orphan_contract_artifacts` (signed / CoC rows referenced by
signatures are preserved).

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
- `initiate_onboarding_contract(...)` — the New Agent workspace seam. It
  rechecks contract permission and scope, requires completed profile plus a
  current confirmed office, and creates or reuses the recipient's contract.
  It does not accept or store a manual status; template review, issue,
  generation, signing, and activation continue through the lifecycle domain.
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
scoped download link. Recipient signing (P1-042) uses the Hub-native ceremony
against the issued review PDF.

### Contract template administration (Hub field placer)

Operations → Contract Templates:

1. Create a family + draft version.
2. Upload a blank PDF — hub stores it privately and streams it to the in-hub
   field placer (`GET …/source.pdf`, session auth).
3. Place fields with roles **Prefill** (commercial/party text) and **Agent**
   (signature + date) in the Hub placer, then **Save fields**. Prefill names
   seed the merge-schema mapping UI. Optional **Suggest fields (AI)** proposes
   boxes; humans must review and save.
4. Map Prefill fields to hub sources, generate a synthetic preview, then
   publish / activate (gated on a validated non-empty `field_layout`).

DOCX/AcroForm local fill is retired; templates are PDF-only with Hub-owned
field placement and signing.

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
  generated PDF). `capabilities.signingReady` is true when Hub signing is
  configured (org PKCS#12 present, or DEBUG with
  `CONTRACT_SIGNING_ALLOW_UNSIGNED_DEV`).

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
Admins cannot use this endpoint on an agent's behalf. Signing is Hub-owned:
Prefill fill, SignaturePad, pyHanko org seal, and certificate of completion.

1. **Consent gate** — versioned ESIGN/UETA disclosure from
   `apps.contract.signing_disclosure` plus required acknowledgement. The
   checkbox is informed consent, not the electronic signature.
2. **Signing intent** — `POST /my-contract/sign` creates a short-lived
   `ContractSigningIntent` bound to recipient, contract version token,
   generated PDF checksum, disclosure version, and session hash. Issue-time
   PDF generation also sends a Hub branded invite email linking to
   `/my-contract/sign` (plus the existing `contract.pdf_ready` in-app notify
   and preference-aware email). Completing the ceremony emits
   `contract.signed`, sends a signed-confirmation email to the recipient, and
   delivers an in-app notification. Other agent-facing lifecycle moves
   (`issue`, `activate`, `supersede`, `terminate`, `expire`) likewise email
   the recipient and notify in-app.
3. **Ceremony** — Hub SignaturePad + required Agent date on the review PDF
   overlay (`ContractSignaturePad`). Appearance is posted to
   `POST /my-contract/sign/complete` (CSRF + intent binding).
4. **Completion** — Hub persists an immutable `ContractSignature`
   (`signature_method=hub_embedded`) bound to the review PDF checksum and
   appearance bytes, consumes the intent, runs lifecycle `mark_signed`, and
   queues asynchronous final signed-PDF generation (P1-043). Success UI may
   poll `/my-contract/sign/status` — it must not trust the browser alone.

Replay and concurrent completes are idempotent (one signature, one signed
artifact, one `contract.signed` effect). Stale version, expired intent,
checksum drift, or non-signable status return recovery copy.

Network metadata retained on the signature is minimized to hashed IP and
hashed truncated user agent from intent start. Disclosure version, appearance
checksum, and seal cert subject/fingerprint are stored with the signature.
Retention: private storage + `PROTECT` FKs; brokerage policy owns statutory
retention years. Legal must approve disclosure and CoC copy before production;
bump `DISCLOSURE_VERSION` when text changes.

# ---------------------------------------------------------------------------
# Final signed PDF (P1-043)
# ---------------------------------------------------------------------------

After the durable signature exists, Celery task
`generate_signed_contract_pdf` builds the authoritative final artifact:

1. Re-read the issued review PDF and verify its live SHA-256 matches
   `ContractSignature.source_checksum` (never re-render legal terms from
   mutable party/office/terms rows).
2. Stamp Agent appearance + date from the stored ceremony files onto those
   exact bytes; append the approved certificate/audit page (signer name,
   contract/version id, signed timestamp, signature method, disclosure
   version, document/verification identifiers, minimized IP/UA hashes).
3. Optionally apply the org PKCS#12 PAdES seal so the seal covers legal +
   certificate pages.
4. Validate readability, page/content markers, source binding, and output
   checksum; only then attach a write-once `ContractArtifact(kind=signed_pdf)`
   and point `AgentContract.signed_pdf` / `ContractSignature.artifact` at it.
5. Emit `contract.signed_pdf_ready` once. Metadata records source checksum,
   output checksum, renderer version (`hub-signed-final-1.0.0`), byte size,
   storage key, created time, generation task id, and signature public id.

Idempotent retries reuse an already-attached final artifact and never replace
it. Application attach paths, Django admin, and model `save()` refuse
overwrite/delete of final signed / CoC artifacts. Generation failure sets
`finalization_status=failed` with a non-PII code while retaining the signature
so ops can re-queue from the unchanged source.

Integrity without streaming private bytes:

- Recipient: `GET /my-contract/<public_id>/signed-pdf/verify`
- Scoped ops: `GET /operations/agent-contracts/<public_id>/signed-pdf/verify`

Both return camelCase checksum / status facts after re-checking
recipient or scoped admin access. Downloads continue to stream through the
existing authorized artifact delivery path (no durable/presigned URL).

### Ops

- Set `SITE_BASE_URL` so invite emails link back to the hub.
- Production requires `CONTRACT_SIGNING_CERT_PATH` (+ passphrase) for the org
  PKCS#12 seal. Local DEBUG may set `CONTRACT_SIGNING_ALLOW_UNSIGNED_DEV=1`.
- Optional field AI: `CONTRACT_FIELD_AI_*` (Azure OpenAI, OpenAI, or Gemini).
  Gemini OpenAI-compat currently expects `gemini-3.6-flash` (older
  `gemini-2.5-flash` ids 404 for new API keys).
- S3 private storage uses `file_overwrite=False`; application no-replace
  semantics remain the primary immutability guarantee.
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
