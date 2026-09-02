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
Quizzes and live sessions render informational detail pages until P1-070 ships
interactive progress.

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

`TrainingProgress` is read-only in P1-068. Missing rows mean `not_started`.
Writes and dashboard/onboarding integration land in P1-070. Progress is keyed
to a specific content primary key, so historical versions remain identifiable
after a newer version supersedes them.

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
  audience, required-state, and version-created changes are audited.
  Lifecycle go-live also emits catalogued domain events
  (`training.published`, `.scheduled`, `.unpublished`, `.archived`,
  `.restored`).
