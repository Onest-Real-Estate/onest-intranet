# Training & Learning

The training library at `/training-learning` is the consumer surface for
brokerage training content. Every read path — the library, detail page, media
download, and global search — uses the same audience predicate in
`apps.training.audience`.

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
There are no presigned or public URLs.

## Progress

`TrainingProgress` is read-only in P1-068. Missing rows mean `not_started`.
Writes and dashboard/onboarding integration land in P1-070.

## Administration

Content authoring is P1-069 (`/operations/training`). Until then, tests and
seeds create published rows directly.
