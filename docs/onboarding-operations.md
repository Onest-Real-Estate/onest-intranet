# Agent onboarding journey

The agent onboarding journey is a presentation contract composed by
`apps.user.services.onboarding_state`. It is the only place that decides the
agent-facing current step, next action, blockers, required-setup gate, and
activation completion. Dashboard, onboarding, New Agent List, user
administration, and future assistant surfaces consume this contract instead of
reconstructing status rules.

The JSON contract is camelCase and currently has `schemaVersion: 1`. Its
`version` is an opaque concurrency token. Clients must return that token when a
write supports `expected_version`; they must never parse or manufacture it.

## Source ownership

| Fact | Source owner | Stored on the onboarding case? |
| --- | --- | --- |
| Profile details and compatibility completion flag | `User` | No |
| Microsoft identity | django-allauth `SocialAccount` | No |
| Selected office | `User.office` and office hierarchy | No |
| Office confirmation checkpoint (office, onboarding version, timestamp) | onboarding composition | Yes |
| Office handoff delivery outcome | onboarding composition | Yes |
| Office administrator and public office details | `OfficeContactAssignment` and `Office` | No |
| In-app and outbound delivery attempts | notifications domain | No |
| Contract generation, delivery, signature, activation | contract domain | No |
| Required training progress | training domain | No |
| Applicable tools and provisioning progress | onboarding-tools domain | No |
| Operational owner and blocking tasks | onboarding operations | Yes |

The composer uses bulk adapters named `bulk_agent_onboarding_states(users)`.
Adapters return an honest `unavailable` source state when a source cannot
provide a fact. Unavailability never fabricates progress and never prevents the
profile/office gate from releasing.

## Stable states

| Part | Allowed values |
| --- | --- |
| Profile | `not_started`, `in_progress`, `complete` |
| Office | `not_selected`, `selected`, `confirmed` |
| Office handoff | `pending`, `notified`, `notification_failed` |
| Contract | `generated`, `sent`, `signed`, `active`, `blocked`, `unavailable` |
| Tool source | `available`, `unavailable` |
| Tool progress | `complete`, `pending`, `blocked`, `unavailable` |
| Tool invitation | `not_applicable`, `pending`, `sent`, `unavailable` |
| Admin tool shelf | `waiting`, `invitation_sent`, `ready`, `blocked`, `not_applicable` |
| Admin tool action | `mark_invitation_sent`, `revoke_invitation`, `mark_ready`, `mark_blocked`, `retry_notification` |
| Admin contract action | `initiate_contract`, `open_contract` |
| Current step | `profile`, `office`, `activation`, `complete` |
| Next action | `complete_profile`, `confirm_office`, `set_up_tool`, `wait_for_office`, `wait_for_activation`, `none` |

Every stored state is a Django `TextChoices`; every composed or compared state
is a typed enum. Labels travel beside stable values so clients do not duplicate
business wording.

## Transition table

| From | Action | To | Preconditions and effects |
| --- | --- | --- | --- |
| Profile `not_started`/`in_progress` | Save one profile section | Profile `in_progress` or unchanged | Valid section values, current `onboarding_version` and section revision. Never sets the compatibility flag. See [profile.md](profile.md#first-login-onboarding). |
| Office `selected` | Confirm the office | Office `confirmed` | The office is still active and assignable, the confirmation names that exact office, and the onboarding version is current. Changing the selection or resetting onboarding invalidates confirmation. The office address never writes to home/mailing fields. |
| Profile `not_started`/`in_progress` | Confirm the reviewed profile | Profile `complete`; office remains `confirmed` | Explicit review confirmation, every required field valid under today's rules, a stored headshot, and an office confirmation for the current office/version. Sets the compatibility flag and required-setup checkpoint, creates/reuses the case, preserves an explicit owner, and publishes `user.onboarded` plus the handoff intent once. |
| Office handoff `pending` | Notification consumer records the in-app handoff | `notified` | The resolved recipient still has server-side scope to the case. The notification dedupe key is user/onboarding-version/office. Outbound providers record queued, sent, retryable, suppressed, and terminal outcomes in the notification ledger. |
| Office handoff `pending` | Recipient is unavailable or no longer authorized | `notification_failed` | The outbox consumer records the failure and retries. The agent sees support escalation copy, never a false delivery claim. |
| Office handoff `notification_failed` | Retry successfully | `notified` | Authorized scoped administrator and current version. |
| Office handoff `notified` | Any handoff transition | — | Rejected; delivered history is not rewound. |
| Tool waiting/requested | Mark invitation sent | `invitation_sent` | Required setup is complete; the tool remains active and applicable to the agent's current office; actor retains onboarding-management permission and scope; current journey version. Records sender/timestamp and publishes one agent-notice intent after commit. |
| Tool invitation/in progress/ready | Correct invitation record | `requested` | Same live permission, scope, office, applicability, and version checks, plus a required safe business reason. Clears current invitation provenance without erasing audit history. |
| Applicable tool | Mark ready or blocked | `ready` or `blocked` | Action is offered by the tool source capability; moving backward or blocking requires a reason. Repeated identical state is a no-op. |
| Failed invitation delivery | Retry agent notice | Delivery `pending` | Exact agent/onboarding-cycle/tool notification and a failed or terminal email ledger row. Tool state is unchanged. |
| No contract | Initiate contract | Contract `draft` | Required profile and current office confirmation are complete; actor retains onboarding-management and contract-management permission and scope; current journey version. Delegates to the contract service. An existing contract is returned unchanged. |
| Any required-setup state | Administrative reset | Correct derived profile/office step | Staff or superuser. Increments `User.onboarding_version`; clears only the profile compatibility flag and this cycle's required-setup checkpoints. |

Repeating a completed transition is a no-op: it produces no duplicate audit
event or domain event. A stale token is rejected before lifecycle state is
committed. Reset preserves contract, training, tool, handoff, task, and audit
history; the composer re-enters the earliest incomplete required step.

## Office administrator resolution

`apps.user.services.onboarding_office` is the reusable office-summary and
contact-role adapter. It lists only active, assignable offices in configured
hierarchy order and exposes only public office fields. Parking, access, and
other internal instructions never enter onboarding.

For the selected office, one current Branch Admin is resolved in this
product-owned order:

1. primary current Branch Admin on the selected office;
2. first current Branch Admin there, ordered deterministically by email and id;
3. primary/first current Branch Admin on the selected office's region;
4. primary/first current Branch Admin on the company/head-office node.

Future, expired, inactive-user, unrelated-office, and non-Branch-Admin
assignments are excluded in the query. There is no separate out-of-office
availability source today; a future source plugs into this adapter rather than
being copied onto the case. With no valid recipient, required setup still
completes, the handoff becomes `notification_failed`, and the payload gives an
honest IT Support escalation path.

The default-owner policy is `resolved_office_admin`: it assigns the resolved
recipient only when the case has no owner. An existing explicit owner is never
replaced. The notification uses the typed scoped onboarding-workspace action;
that destination rechecks capability and office scope, so the link grants no
access by itself.

## Administrator workspace contract

`/operations/new-agents/<id>` is the single scoped action surface. Read access
requires `web.view_new_agents`; mutations require
`web.manage_new_agent_onboarding`, and contract initiation additionally
requires `contract.manage_agent_contracts`. The target queryset applies the
actor's effective office/region/company scope before lookup, so an unknown and
an out-of-scope id both return 404. Source services repeat permission and scope
checks inside the write transaction, and self-management is refused.

The detail payload contains the submitted profile allowlist, current confirmed
office and resolved Branch Admin, source-derived contract and training facts,
operational blockers and activity, and catalog tools enriched with source-owned
capabilities. Sensitive profile fields appear only with
`user.view_user_administration`; the headshot streams through the same scoped
policy rather than exposing a storage path. Tool controls are rendered by
capability code, not by vendor name, so a new catalog tool needs no workspace
branch.

The composer selects exactly one `recommendedAction`. Every POST carries the
opaque `journeyVersion`, whose inputs include onboarding cycle, current office,
and case update time. The service locks the user and case, compares the token,
then rechecks the live catalog and confirmed office. A concurrent action or an
office change therefore returns 409 before overwriting work. Validation errors
return the shared 422 `fields`/`form` contract; authorization lost between
render and submit returns 403.

Recent activity combines case lifecycle entries with tool-source audit entries.
It exposes actor, action, safe changed-field names, and timestamp only. Free-text
reasons, home address, phone, license/MLS/NRDS values, headshot paths, vendor
URLs, and contract terms never enter the workspace activity payload.

## Derived completion

`requiredSetupComplete` releases the strict gate. Existing users with
`User.profile_completed=True` are backfilled with a required-setup checkpoint
and remain released, including legacy records without a current office.

`activationComplete` is separate. It requires released setup, a successful
office handoff, an active contract, complete required training, all applicable
required tools ready, no blocking operational task, and an active account.
Unavailable downstream sources keep activation incomplete but do not reopen the
strict profile/office gate.

The server selects `currentStep` and `nextAction`; clients display those values
and do not infer them from individual milestones.

## Access policy

| User | Dashboard | Other protected routes | Journey dialog |
| --- | --- | --- | --- |
| Incomplete ordinary Agent | Shell, greeting, journey, and setup-dialog profile props only | Redirect to dashboard, except onboarding self-service, headshot, and logout | Required, non-dismissible |
| Completed Agent | Full authorized dashboard | Normal route policies | Activation center: opens once per login while activation is incomplete, or on request |
| Administratively reset Agent | Same as incomplete Agent at the correctly derived step | Same strict gate | Required |
| Staff or superuser | Normal route policies | Normal route policies | Never forced |
| User without an effective Agent role | Normal route policies | Normal route policies | Never forced |
| Anonymous user | Login policy | Login policy | Not applicable |

The visual overlay is not an authorization boundary. Middleware enforces the
same policy on direct URLs. While the strict gate is active, the dashboard view
does not register deferred widget props and shared Inertia data substitutes
empty navigation features plus null office and notification state. Logout stays
available through the shell and posts through Inertia.

## Dashboard setup dialog

Onboarding is a dialog over `/dashboard`, owned by
`frontend/components/onboarding/OnboardingDialog.tsx`. The server decides what
it may show; the dialog renders `onboardingJourney` and never infers progress.

| Dashboard prop | Present when | Contents |
| --- | --- | --- |
| `onboardingJourney` | Agent journey applies | The canonical journey payload above |
| `onboardingProfile` | Strict gate active | The profile flow at `?section=` (validated), else the first unfinished section |
| `onboardingActivation` | Gate released | Lazy: `autoOpen` and the public office summary |

- **Strict.** No close button, Escape, or outside click. Sign out stays in the
  dialog header and warns over unsaved edits. No deferred widget provider is
  registered, so neither a full visit nor a partial reload can serialize widget
  data. Section saves redirect to `dashboard?section=<next>` and 409/422
  responses re-render the dashboard with the dialog, so the dialog stays
  mounted (`preserveState`) and moves focus to the new section heading.
- **Released.** The same dialog becomes the dismissible activation center.
  `autoOpen` is true when `?onboarding=open` is requested, or on the first
  full dashboard visit of a login session while activation is incomplete. The
  session key `onboarding_activation_prompted_version` stores the onboarding
  cycle that already prompted, so an administrative reset or new login prompts
  once more and ordinary navigation never does. The prop is lazy, so a partial
  reload that does not request it cannot spend the prompt. A persistent
  dashboard status entry reopens the center and receives focus when it closes.
- **Compatibility.** `GET /onboarding` redirects to `dashboard?onboarding=open`,
  carrying a valid `section` for incomplete Agents. Users outside the Agent
  journey go to their profile (or the dashboard once complete).
- **Copy.** Dialog wording lives in `frontend/lib/onboarding/copy.ts`. Status
  wording about handoff, contract, tools, and blockers comes from the journey
  payload, so the client never claims delivery the server has not recorded.
- **Next steps.** `frontend/lib/onboarding/stages.ts` composes the list from
  `NEXT_STEP_SOURCES`. A new milestone adds one source function over the
  journey payload; the profile form and access policy do not change.

## Query and privacy contract

The composer calls each domain once with the complete user batch. Tool catalog,
audiences, office ancestry, and agent status rows are loaded in four bounded
queries; there is no query per user, tool, or milestone. Administrative callers
prefetch onboarding cases, tasks, and compatibility tool rows before composing.

Lifecycle audit and domain events contain identifiers and enum transitions
only. They must not contain home address, phone number, headshot path,
invitation URL, or other sensitive profile values. Read-only composition emits
no event.

New milestones should be implemented as a source-owned bulk adapter and added
to the catalog-driven composition. This is deliberately not a generic workflow
engine.
