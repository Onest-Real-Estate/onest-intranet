# Operational onboarding and New Agent List

The New Agent List at `/operations/new-agents` is the scoped operations queue
for activation. It does not replace profile, Microsoft SSO, contract, or
training records. `apps.user.services.onboarding_state` is the only service
allowed to combine those records into an onboarding status; the dashboard
metric, user-administration detail, list, workspace, and future assistant tools
consume that contract.

## Population and scope

A user remains in the queue when they joined or started within the trailing 90
days, their required profile is incomplete, or they have open operational work.
The actor's company, region, or office scope is applied in SQL before search,
filters, counts, source adapters, or serialization. An out-of-scope direct ID
returns 404, and a crafted office or assignee filter can only narrow the already
scoped queryset.

`web.view_new_agents` permits reading the queue and detail.
`web.manage_new_agent_onboarding` separately permits owner, task, tool-state,
and eligible-notice actions. Admins, Region Managers, and Branch Managers
receive both grants; their effective assignments still determine reach. Self
management is refused.

## State contract

The service emits these source-owned milestones:

| Milestone | Source | Writable here |
| --- | --- | --- |
| Required profile complete | `User.profile_completed` | No |
| Microsoft login connected | allauth Microsoft `SocialAccount` | No |
| Contract generated, signed, active | bulk contract adapter | No |
| Required training complete | bulk training adapter | No |
| Approved tool setup | `OnboardingToolSetup` | Yes, fixed states only |

Contracts implement `apps.contract.services.bulk_agent_onboarding_states(users)`
and training implements the equivalent function in `apps.training.services`.
The adapter must return the typed dataclasses from
`services.onboarding_state`, perform one bulk read, and never fall back to a
per-user query. Until a source exists its milestones report `unavailable`; the
UI never substitutes sample progress.

Overall status is deterministic:

1. `blocked` when the account is inactive, office/start date is missing, a
   required source is blocked or unavailable, an approved tool is blocked, or
   an open operational task is marked as an activation blocker.
2. `ready` when every required source/tool milestone is complete and no
   operational task remains open.
3. `in_progress` when at least one milestone is complete.
4. `not_started` otherwise.

Source updates are read on every request; onboarding state has no shared cache.
Operational mutations use the case's `updated_at` as an optimistic-concurrency
token and return HTTP 409 with the last editor when stale.

## Actions and events

Owner assignment, task creation/resolution, and tool updates use explicit
service functions—never a generic user `ModelForm`. Each is idempotent when the
requested state already matches, emits an append-only audit event, and publishes
a registered domain event transactionally. Notice resends are offered only by
the source adapter and delegate to `resend_onboarding_notice`; that service must
re-check its own permission and deduplicate on `(source, notice,
idempotency_key)`.

Correction links are emitted server-side only when the actor holds the source
workflow's permission. Contract and training data never become visible merely
because somebody can coordinate onboarding.

## Privacy and retention

The workspace does not collect general notes. Operational task titles are
limited to 200 characters and must not contain client, contract, commission,
medical, credential, or other sensitive details. Resolved task titles are kept
for two years for operational accountability, then removed with:

```bash
uv run python manage.py purge_onboarding_tasks --commit
```

Without `--commit` the command is a dry run. Every committed purge records an
aggregate audit event; existing append-only audit/domain events remain under
their own retention policy.
