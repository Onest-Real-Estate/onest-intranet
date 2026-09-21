# Training & Learning

The training library at `/training-learning` is the consumer surface for
brokerage training content. Every read path — the library, detail page, media
download, and global search — uses the same audience predicate in
`apps.training.audience`.

Administration lives at `/operations/training` behind `web.manage_training`.

## Visibility

1. Audience match (OR union across selectors)
2. `published` status and publish/expiry window
3. URL filters (narrow only)

Required content sorts before optional items, then `display_order`, then title.

## Content types

Articles, guides, videos, checklists, courses, quizzes, live sessions,
recordings, and tool onboarding entries are modeled on `TrainingContent`.
Quizzes and live sessions become interactive once their definitions are saved
on the draft and published with the content. The training workspace shows a
quiz or live-session editor (draft-only) after the content type is saved; those
forms post to `training_quiz_save` / `training_session_save` separately from the
main content draft. Publish validation refuses unconfigured quiz or session
items.

### Tool onboarding guides

A `tool_onboarding` item is the activation guide an onboarding tool unlocks. It
carries `tool_code`, matched against the live catalog's stable slug (legacy
codes from the retired four-value enum stay valid), and the training workspace
picks that code from the catalog rather than from free text — so a new tool
needs configuration, not a deploy.

Like a video or recording, publishing one requires a ready primary recording or
an approved embed: the whole point is something to watch, and a guide with
nothing behind it ships a play button that opens nothing.

`apps.training.tool_guides.activation_guides_for` is the only way another module
asks for one. It reuses `visible_training_content`, so a guide offered beside a
tool can never be more permissive than the same item in the library, and it
returns the current version per tool — highest visible version number in the
lowest-ordered family. The onboarding journey decides *when* a guide is offered;
see `docs/onboarding-operations.md`. Completing one writes `TrainingProgress`
and nothing else: it never marks a vendor account ready.

Accessibility: uploaded recordings have no caption track yet, and transcripts
have no authoring surface. Until both ship, publish activation guides as
provider embeds with captions enabled, and verify captions during the staging
pass in [onboarding-support.md](onboarding-support.md#staging-checklist).
Opened and completed guides are counted per tool in the **Onboarding journey
health** report.

## Transcriptions

Video and recording items may include searchable transcript segments
(`{startMs, endMs, text}`). The detail page lets readers search the transcript
and jump to timestamps when the embed provider allows seeking.

## Protected media

Files are stored in private storage and streamed through `training_media`.
There are no presigned or public URLs. Uploads land as `pending`, then a Celery
task (`process_training_media`) moves them to `ready`, `quarantined`, or
`failed`. Publish refuses while any active file is not ready.

## Progress

`TrainingProgress` is keyed to `(user, content)` — a specific content primary
key — so historical completions survive when a newer version supersedes them.

Learners may start and complete passive content. Quizzes complete only through
server-graded attempts. Live sessions complete through attendance (usually an
admin correction). Courses roll up module completions.

Writes are idempotent: repeating the same status does not write a second audit
event. Learner mutations always bind to the authenticated user and cannot be
forged for another person. Admins with `web.manage_training` may correct
progress or attendance inside their publication and learner scope with a
required reason.

### Version completion policy

Each content row carries `version_completion_policy`:

- `current_version` — required-training satisfaction needs completion of the
  **live published** row in the version family.
- `any_version` — any completed row in the family satisfies.

Required-training status for onboarding and the dashboard is computed by
`apps.training.required_status` and reused by:

- `bulk_agent_onboarding_states`
- the dashboard `training` provider
- the `trainingCompletion` operational report

## Quizzes

`TrainingQuiz` + `TrainingQuizQuestion` define MCQ quizzes. Attempts store
submitted answers, server-computed score, pass result, attempt number, and
content version. Client-supplied scores are rejected. Learner payloads never
include correct choice ids (except under the `review` feedback policy after
submit).

## Live sessions

`TrainingLiveSession` stores schedule (UTC + IANA timezone), capacity,
meeting URL, and registration window. `TrainingSessionRegistration` tracks
register / cancel / attended / no-show. Capacity is enforced under row lock.

## Certificates

Certificates of completion are **admin-issued** from the training workspace
(`/operations/training/<id>/edit`). Publishers with `web.manage_training` see
completed learners in their author and learner scope and **Issue** a PDF in one
step (`training_certificate_issue`). Issuance is idempotent once the certificate
is `approved` with a stored file.

The PDF is a landscape, branded certificate of completion (reportlab) with a
cryptographic HMAC-SHA256 signature and a QR code pointing at the public
verification URL. Each certificate has a stable `public_id` (UUID).

### Verification

- Human / QR: `GET /verify/training-certificates/<uuid>` (Inertia page)
- External providers: same URL with `Accept: application/json` or `?format=json`

The JSON envelope includes `valid`, `status`, `signatureValid`, learner name,
training title, dates, and a signature fingerprint. Signing key:
`TRAINING_CERTIFICATE_SIGNING_KEY` (falls back to a purpose-bound derivation of
`DJANGO_SECRET_KEY`).

`TrainingCertificate` stays approval-gated for learners: they only see a
download when the certificate is `approved` and stored in private storage
(`/training-learning/<id>/certificate`). The workspace list is capped (newest
completions first) so the edit page stays light. Use **Reissue** to refresh an
already-issued PDF (new signature + QR).

## Administration

Scoped publishers manage drafts at `/operations/training`:

- **Scope.** Own only content whose `owner_office` sits in the actor's grant.
  Out-of-scope ids are 404. Audience selectors are re-authorized by
  `assert_can_target` — company-wide and non-delegable roles are refused for
  scoped admins.
- **Lifecycle.** Stored statuses are `draft` → `published` → `archived`.
  Scheduled is `published` with a future `publish_at`. Derived UI states:
  Draft / Scheduled / Live / Expired / Archived.
- **Versioning.** Each row carries `version_family` + `version_number`. Body
  and media edits are allowed only on drafts. Published content is forked via
  **Duplicate as new version**. Publishing version N>1 archives the previous
  live sibling in the family so the library shows one live version.
- **Concurrency.** Writes compare an opaque `updated_at` token; a mismatch is
  HTTP 409.
- **Preview.** Workspace preview reuses the learner detail payload and
  production renderers. Drafts never enter `visible_training_content`.
- **Audit / domain events.** Publish, schedule, unpublish, archive, restore,
  audience, required-state, version-created, progress, attendance, and quiz
  submission changes are audited. Lifecycle go-live also emits catalogued
  domain events (`training.published`, `.scheduled`, `.unpublished`,
  `.archived`, `.restored`). Marking a row required emits
  `training.required_changed`.

## Notifications

Required training that is **live** fans out through `apps.notifications`
(`NotificationType.TRAINING`). Optional content stays in the library only.

| Event | Notifies |
| --- | --- |
| `training.published` | Audience of required content that is in window, except the publisher and learners who already satisfy the version policy |
| `training.scheduled` | Nobody. Catalog forbids notifying about a window that has not opened |
| `training.required_changed` | Same as publish when `is_required` is true and the row is live |

Scheduled required rows become `training.published` via Celery task
`release_scheduled_required_training` the first time `publish_at` has passed.
The producer uses a stable dedupe key (`training.assigned:{id}:{version}`), so
a replay or a later required-toggle does not create a second row for the same
version. Detail is resolved through `visible_training_content` on every read.
