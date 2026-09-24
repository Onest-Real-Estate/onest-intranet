# Onboarding release, operations, and support

This is the operating manual for the first-login onboarding journey (Microsoft
SSO → profile → office handoff → administrator activation → conditional
training). The contract itself lives in
[onboarding-operations.md](onboarding-operations.md); this page covers
measurement, support, reset and rollback, staging sign-off, and how to extend
the journey without breaking it.

## Release status

Verified by automated tests (CI runs SQLite; the PostgreSQL suites run in the
docker stack — see [Verification](#verification)):

| Scenario | Proven by |
| --- | --- |
| Complete and partial Microsoft claims through the real allauth callback | `test_onboarding_release.py` |
| Upload/replace headshot, save sections, confirm office, reach waiting state | `test_onboarding_release.py`, `test_onboarding_profile.py` |
| Correct Branch Admin receives and opens the scoped case | `test_onboarding_release.py`, `test_onboarding_office_handoff.py` |
| Lofty send unlocks only Lofty's guide; SkySlope send unlocks SkySlope's | `test_onboarding_release.py`, `test_onboarding_next_steps.py` |
| Contract initiation shows as "being prepared" to the agent | `test_onboarding_release.py`, `apps/contract/tests/test_services.py` |
| Refresh, second device, reconnect all read database truth | `test_onboarding_release.py`, `test_onboarding_stream.py` |
| Missing admin, retired office, failed notification, unavailable guide, contract/training outage, Centrifugo outage | `test_onboarding_release.py`, `test_onboarding_stream.py` |
| Failed handoff recovers after support adds a contact, without a false claim | `test_onboarding_release.py` |
| Authorized reset keeps history and re-enters at the derived step | `test_onboarding_release.py`, `test_onboarding_journey.py` |
| Out-of-scope administrator, cross-user, and cross-channel requests denied | `test_onboarding_release.py`, `test_onboarding_stream.py` |
| Double finalize, two admins recording one invitation, two admins initiating one contract | `test_onboarding_concurrency.py` (PostgreSQL only) |

Open decisions that block sign-off are listed under
[Product owner sign-off](#product-owner-sign-off).

## Operational measures

Every measure is an aggregate over tables that already own the fact. Nothing
adds tracking, session replay, or an analytics SDK.
`apps.user.services.onboarding_metrics.journey_health` computes them for a
population the caller has already scoped.

| Where | Who | Scope |
| --- | --- | --- |
| Report **Onboarding journey health** (`/reports/onboardingJourneyHealth`) | `web.view_reports` + `web.view_new_agents` | The viewer's office/region/company, like `onboardingProgress` |
| `manage.py onboarding_health [--office <stable_key>]` | Operators with shell access | Company-wide or one office |
| Log lines `onboarding_error code=…` and `onboarding_live.*` | Log aggregation | Whole deployment |

| Measure | Source | Report row |
| --- | --- | --- |
| Journeys started | `User.last_login` set | `journey / started` |
| Required setup completed | `UserOnboardingCase.required_setup_completed_at` | `journey / required_setup_completed` |
| Activation completed | Composed `activationComplete` | `journey / activation_completed` |
| Median hours to required setup | `required_setup_completed_at − date_joined`; backfilled legacy users excluded | `journey / median_hours_to_required_setup` |
| Drop-off by server-owned step | Composed `currentStep` | `current_step / profile·office·activation·complete` |
| Handoff recorded and outcome | `office_handoff_state`; notification ledger delivery state | `handoff / …`, `handoff_delivery / …` |
| Hours from handoff to invitation sent / ready, per tool | `AgentToolStatus.invitation_sent_at`, `ready_at` vs. the required-setup checkpoint | `tool:<slug> / median_hours_to_invitation`, `median_hours_to_ready` |
| Invitations sent / ready, per tool | `AgentToolStatus` | `tool:<slug> / invitations_sent`, `ready` |
| Guide unlocked | Same as invitation sent: a guide unlocks exactly when its tool's invitation is recorded | `tool:<slug> / invitations_sent` |
| Guide opened / completed | `TrainingProgress.started_at` / `completed_at` on `tool_onboarding` content | `tool:<slug> / guides_opened`, `guides_completed` |
| Contract initiated / sent / signed / active | Composed contract state | `contract / generated·sent·signed·active` |
| Blocked by missing contact or unavailable source | Blocker keys `office_handoff_failed`, `contract_unavailable`, `training_unavailable`, `tools_unavailable` | `journey / blocked_by_missing_contact_or_source`, `blocker / …` |
| Recorded failures by stable code | Audit action `user.onboarding.office_handoff_unavailable` | `failure / …` |
| Rejected requests by stable code | Log `onboarding_error code=<code>` | Log aggregation only |

Rejection codes (`OnboardingErrorCode`):

| Code | Meaning |
| --- | --- |
| `stale_onboarding_version` | A page from before a reset or another session's change |
| `stale_profile_section` | A section changed in another tab since it was loaded |
| `profile_invalid` | A section or review failed server validation |
| `protected_field_rejected` | The request tried to write a protected field |
| `headshot_invalid` | The upload was not an acceptable image |
| `headshot_storage_unavailable` | Storage could not save or confirm the photo (retryable) |
| `admin_action_stale` | A workspace action raced another administrator's change |
| `admin_action_invalid` | A workspace action failed validation or its prerequisites |

Live-update counts (`onboarding_live.published`, `.publish_failed`,
`.unconfigured`, `.source_missing`) are described in
[onboarding-operations.md](onboarding-operations.md#live-journey-invalidation-self-hosted-centrifugo).

**Privacy.** Report rows, command output, and log lines carry counts, medians,
enum values, and stable codes only — never a name, email, phone, address,
license/MLS/NRDS value, headshot path, note, invitation link, or exception
text. `test_onboarding_metrics.py` and `test_onboarding_release.py` assert
this. Keep it true when you add a measure: add a stable code, not a message.

## Support runbook

Every fix below goes through a scoped, audited surface. Never edit onboarding
rows in a database shell, and never paste profile values into a ticket; the
`onboarding_health` output is safe to paste.

### Missing office administrator contact

**Symptom.** The agent's activation center says their office handoff needs
administrator attention; the report shows `blocker / office_handoff_failed`; the
workspace recommends **Retry office handoff**, disabled with "Add a current
Branch Admin contact for this office first."

1. Add a current Branch Admin `OfficeContactAssignment` for the agent's office
   (or its region, or head office — resolution falls back in that order; see
   [onboarding-operations.md](onboarding-operations.md#office-administrator-resolution)).
2. Open the agent in the New Agent List. The recommended action is now
   **Retry office handoff**; run it. It re-publishes the same deduplicated
   handoff event and assigns the resolved admin as owner if the case has none.
3. The state becomes `notified` only after the notification consumer creates
   the notification. If it stays failed, check the domain-event delivery
   ledger for `notifications.deliver` (Django admin → Event deliveries).

Nothing blocks the agent meanwhile: required setup stays released.

### Notification retries

- **Office handoff** — as above.
- **Tool invitation notice** — the tool row offers **Retry notification** when
  the email ledger has a failed or terminal attempt. It requeues delivery and
  never changes the tool state.
- **Contract or training notices** — the workspace's eligible-notice list
  delegates the resend to the owning domain with an idempotency key.
- **Dead domain-event deliveries** — Django admin → Event deliveries → *Replay
  selected deliveries* (`audit.can_replay_events`). Consumers are idempotent,
  so a replay never duplicates a notification.

### Incorrect office

The office is administrative once onboarding scopes it
([profile.md](profile.md#office-is-administrative-for-anyone-it-scopes)).

1. Correct `User.office` through Agent Administration. Open workspace pages
   go stale (409), because the office is part of the journey version.
2. The old confirmation and handoff no longer count for the new office. The
   strict gate stays released, but the handoff reads `pending` and nothing is
   sent to the new office — the agent has not confirmed it.
3. Have staff run **Reset onboarding** (below). The agent reviews and confirms
   the new office, and finalizing hands off to that office's Branch Admin under
   a new onboarding version. The old handoff stays as history.

### Mistaken invitation state

Use the tool row's **Revoke invitation** (or move the tool backwards). A
business reason is required, provenance is cleared, and the audit trail keeps
who recorded the original send and who corrected it. The agent's guide locks
again on the next journey reload. Never edit `AgentToolStatus` directly.

### Stuck contract

| Agent sees | Means | Do |
| --- | --- | --- |
| Waiting for your office administrator | No contract exists | Initiate it from the workspace |
| Being prepared | Draft, in review, or awaiting company signature | Continue in the contract workspace |
| Needs attention | Generation error, or expired/terminated before activation | Fix in the contract workspace; regenerate or issue a new version |
| Unavailable | The contract source could not answer | Check the contract service and logs; nothing to fix on the case |

`unavailable` is reserved for a source that did not answer. A contract the
source *did* return is never reported as unavailable.

### Training guide unavailable

**Symptom.** The agent's row says the guide is not available and points at the
vendor help or request path, after the invitation was recorded.

1. In the training workspace, find `tool_onboarding` content for that tool's
   slug. It must be published, inside its window, addressed to the agent, and
   playable (a ready primary recording or an approved embed).
2. Publish or fix it; the guide appears on the agent's next journey load. No
   onboarding state changes.

### Centrifugo outage

Live updates are hints, never truth. With Centrifugo down the dialog keeps
working, says updates are delayed after a prolonged failure, and **Check for
updates** reloads the journey from the database. Restore the service, then
replay dead `user.onboarding_stream` deliveries. Watch
`onboarding_live.publish_failed` return to zero. See
[onboarding-operations.md](onboarding-operations.md#live-journey-invalidation-self-hosted-centrifugo).

## Reset and replay

**Reset** is a staff-only Django admin action (*Reset onboarding for selected
users*, scoped by `user_admin_reset_onboarding`). It calls
`reset_required_setup`, which increments `onboarding_version` and clears only
this cycle's checkpoints. The agent re-enters the strict gate at the earliest
incomplete step with every saved value kept, and must review and confirm again.

| Fact | After reset |
| --- | --- |
| Profile values, headshot | Kept |
| `profile_completed`, office confirmation, `required_setup_completed_at` | Cleared (recalculated when the agent finishes again) |
| `onboarding_version` | Incremented; old pages get 409 |
| Previous handoff, its notification and delivery rows | Kept as history; a new cycle hands off again under the new version |
| Case owner, tasks | Kept |
| Tool states and invitation provenance | Kept |
| Contracts | Kept |
| Training progress | Kept |
| Audit events and domain events | Kept (append-only) |
| Journey, current step, blockers, activation | Recalculated on every read |

**Replay** of a domain event is always safe: every consumer is idempotent
(notification dedupe keys, per-consumer delivery rows, the monotonic live
cursor). A replay for an older office or onboarding cycle never changes the
current case.

## Staging checklist

Use one test account per role, all Microsoft SSO, on the staging tenant.
Record pass/fail with the date; attach the `onboarding_health --office <key>`
output, never screenshots showing another person's profile values.

| Test user | Role and scope | Setup |
| --- | --- | --- |
| `stg-agent` | `realtor`, no office yet | Fresh Entra account never signed in to staging |
| `stg-branch-admin` | `branch_admin`, office A | Primary Branch Admin `OfficeContactAssignment` on office A |
| `stg-branch-manager` | `branch_manager`, office A | Holds `manage_new_agent_onboarding` and contract grants |
| `stg-regional-admin` | `regional_admin`, office A's region | Read-only onboarding reach |
| `stg-company-admin` | `system_admin`, company | Full onboarding and contract grants |
| `stg-other-manager` | `branch_manager`, office B | Out-of-scope control |

1. `stg-agent` signs in → the setup dialog opens over the dashboard; direct URLs
   redirect back; legal name is locked if Entra sent a full name.
2. Upload, replace, and remove the headshot; save each section; confirm office
   A; finish review → the activation center says the office has it.
3. `stg-branch-admin` gets the in-app handoff notification and email; opening
   it lands on that agent's workspace.
4. `stg-branch-manager` records the Lofty invitation → the agent's Lofty guide
   unlocks live (or after **Check for updates**); SkySlope stays locked.
5. Record SkySlope → its guide unlocks. Play both guides; captions or a
   transcript are available.
6. `stg-company-admin` initiates the contract → the agent sees "Being prepared".
7. Sign in as `stg-agent` on a second device and in a private window → same
   state. Disconnect the network for a minute, reconnect → the dialog catches up.
8. `stg-other-manager` opens the agent's workspace URL → 404.
   `stg-regional-admin` can open it but gets no mutation controls.
9. Remove office A's Branch Admin contact, onboard a second agent → handoff
   failed; re-add the contact; **Retry office handoff** → notified.
10. Stop Centrifugo → the dialog still works and says updates are delayed.
11. Reset `stg-agent` from Django admin → strict gate returns with values kept;
    the tool, contract, and audit history is unchanged.
12. Open **Onboarding journey health** as `stg-branch-manager`: office A only,
    no names or emails.

Accessibility checks for the same pass are listed under
[Accessibility and responsive gate](#accessibility-and-responsive-gate).

## Rollback

The release adds no destructive migration, so rolling back application code
never loses data.

- **Profile data** lives on `User` and is written by both the old and new
  flows. Rolling back keeps everything submitted.
- **Case, tool, contract, training, notification, and audit rows** are
  append-only or additive. Older code ignores columns and events it does not
  know.
- **Do not reverse migrations** to roll back. Reversing the tool-catalog seed
  deletes only rows without recorded progress, but reversing schema migrations
  would drop columns that hold history. Roll back by deploying the previous
  image only.
- **Live updates** can be switched off without a deploy by unsetting the four
  `CENTRIFUGO_*` variables; the dialog falls back to manual refresh.
- After a rollback, agents mid-flow keep their saved sections: section saves
  write `User` directly and never depend on the new release's tables.

## Product owner sign-off

These are product decisions, not engineering defaults. Record the answer in the
issue and in the affected doc before release.

1. **Who may record invitations.** The handoff notifies the office's Branch
   Admin, but the `branch_admin` and `regional_admin` role bundles hold
   `web.view_new_agents` only, not `web.manage_new_agent_onboarding`. Today the
   notified admin can open the case but cannot record an invitation; a Branch
   Manager or company admin must. Either grant the manage permission to
   Branch/Regional Admin (a role-bundle change plus a data migration), or route
   the handoff to a role that can act.
2. **Captions and transcripts for activation videos.** Uploaded training video
   has no caption track yet (deferred), and there is no authoring surface for
   transcripts. Until one ships, the content policy must be: activation guides
   are provider embeds with captions enabled, checked during staging step 5.
3. **Required fields** (MLS, NRDS, license): universal, conditional by
   office/state, or "not issued yet". The server policy is
   `ProfileFieldSpec.required` / `required_from_version`.
4. **Office fallback** when an office has no Branch Admin: the implemented
   chain is office → region → head office, then IT Support copy.
5. **Copy** in `frontend/lib/onboarding/copy.ts` and the journey presentation
   tables, and the approved Lofty/SkySlope guide content.

## Accessibility and responsive gate

Automated: `OnboardingDialog.test.tsx`, `OnboardingProfileFlow.test.tsx`,
`NextSteps.test.tsx`, and `OnboardingWorkspace.test.tsx` run axe and cover
dialog naming, focus return, error summaries, step announcements, and live-region
updates. Manual, per release, at each of 360 px, 768 px, 1280 px, and 200 %
zoom, in light and dark, with forced colors and reduced motion:

- Complete the whole flow with the keyboard only: upload, office selection,
  review, the strict dialog (no escape), closing the released dialog, and
  opening a guide.
- A screen reader announces the dialog name, the current step, the error
  summary, progress, and a live guide unlock.
- Focus is always visible, returns to the status entry when the activation
  center closes, and moves to the new section heading after a save.
- Long names and long office addresses wrap; nothing is clipped. Missing
  optional content (no guide, no address) reads as an honest empty state.
- On a phone, the dialog is a full-height sheet inside the safe area; the
  footer stays reachable above the virtual keyboard and browser chrome;
  touch targets are at least 44 px.

## Extension seams

Each seam below is the only place that needs to change. If a change needs a
vendor-specific branch in React, it is in the wrong place.

**Onboarding field.** Follow [profile.md](profile.md#adding-a-field): model field
and normalizer, `SelfProfileForm`, a `ProfileFieldSpec` with
`onboarding_section` and, to require it only for new cycles,
`required_from_version`. Existing completed agents are not re-gated.

**Office contact role.** Add an `OfficeContactAssignment.AssignmentType`, then
extend `resolve_office_administrator` in `apps/user/services/onboarding_office.py`
(or add a sibling resolver) with its own fallback chain. The handoff event
already carries `recipient_id`, so producers and the workspace need no change.

**Tool.** Add a catalog row at `/operations/tool-catalog`
(`web.manage_onboarding_tools`). It appears in My Tools, the workspace, and the
activation center with no deploy. See
[onboarding-tools.md](onboarding-tools.md#managing-the-catalog).

**Invitation adapter.** A vendor API that can prove delivery plugs in behind
`apps.onboarding_tools.services.workspace_capabilities` and
`perform_workspace_action`: expose a new `ToolWorkspaceAction` capability, and
write state through `set_state` so audit, the `onboarding_tool.state_changed`
event, the agent notice, and live updates follow automatically. Never store a
vendor link or token.

**Training guide.** Publish a `tool_onboarding` item with the tool's slug and a
playable recording or embed. See
[training.md](training.md#tool-onboarding-guides).

**Milestone source.** Add a bulk adapter returning typed states for the whole
user batch (no per-user queries), compose it in
`apps.user.services.onboarding_state`, publish a registered domain event from
the owning write service, map it to a `SourceKey` in
`onboarding_stream.EVENT_SOURCES`, and add one source function to
`NEXT_STEP_SOURCES` in `frontend/lib/onboarding/next-steps.ts`. Add its blocker
key to `SOURCE_BLOCKER_KEYS` in `onboarding_metrics.py` if an unavailable
source should count as blocking.

**Notification template.** Register the event in `apps/audit/catalog.py`, add a
producer to `EVENT_PRODUCERS` with a record-identity dedupe key, and ship a
source resolver. See [notifications.md](notifications.md#producing).

## Verification

```bash
# CI gate (SQLite)
uv run ruff check . && uv run ruff format --check . && uv run ty check \
  && uv run python manage.py makemigrations --check --dry-run \
  && pnpm typecheck && pnpm exec biome check . && uv run pytest && pnpm test

# PostgreSQL row-lock and race tests (docker stack; filesystem storage, because
# the headshot tests patch local storage and the dev stack defaults to RustFS)
make up
docker compose --env-file .env -f deployment/compose.dev.yaml exec -e USE_S3=0 \
  web uv run pytest --create-db \
  apps/user/tests/test_onboarding_concurrency.py \
  apps/user/tests/test_onboarding_administration.py \
  apps/user/tests/test_onboarding_release.py
```

`test_onboarding_concurrency.py` skips on SQLite. The compile-time guards
`test_case_lock_compiles_to_valid_postgresql` and
`test_agent_lock_compiles_to_valid_postgresql` run in CI and fail if a lock on
a nullable join loses its `of=("self",)`.
