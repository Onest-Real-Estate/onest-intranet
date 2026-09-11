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
| Office confirmation checkpoint | onboarding composition | Yes |
| Office handoff delivery outcome | onboarding composition | Yes |
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
| Current step | `profile`, `office`, `activation`, `complete` |
| Next action | `complete_profile`, `confirm_office`, `set_up_tool`, `wait_for_office`, `wait_for_activation`, `none` |

Every stored state is a Django `TextChoices`; every composed or compared state
is a typed enum. Labels travel beside stable values so clients do not duplicate
business wording.

## Transition table

| From | Action | To | Preconditions and effects |
| --- | --- | --- | --- |
| Profile `not_started`/`in_progress` | Submit required profile and office data | Profile `complete`; office `confirmed` | Valid profile, selected office, current version. Sets the compatibility flag and required-setup checkpoint atomically. |
| Office handoff `pending` | Record successful notification | `notified` | Authorized scoped administrator and current version. |
| Office handoff `pending` | Record delivery failure | `notification_failed` | Authorized scoped administrator and current version. |
| Office handoff `notification_failed` | Retry successfully | `notified` | Authorized scoped administrator and current version. |
| Office handoff `notified` | Any handoff transition | — | Rejected; delivered history is not rewound. |
| Any required-setup state | Administrative reset | Correct derived profile/office step | Staff or superuser. Increments `User.onboarding_version`; clears only the profile compatibility flag and this cycle's required-setup checkpoints. |

Repeating a completed transition is a no-op: it produces no duplicate audit
event or domain event. A stale token is rejected before lifecycle state is
committed. Reset preserves contract, training, tool, handoff, task, and audit
history; the composer re-enters the earliest incomplete required step.

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
| Incomplete ordinary Agent | Shell, greeting, and journey only | Redirect to dashboard, except onboarding self-service, headshot, and logout | Required |
| Completed Agent | Full authorized dashboard | Normal route policies | Not required; activation progress remains available |
| Administratively reset Agent | Same as incomplete Agent at the correctly derived step | Same strict gate | Required |
| Staff or superuser | Normal route policies | Normal route policies | Never forced |
| User without an effective Agent role | Normal route policies | Normal route policies | Never forced |
| Anonymous user | Login policy | Login policy | Not applicable |

The visual overlay is not an authorization boundary. Middleware enforces the
same policy on direct URLs. While the strict gate is active, the dashboard view
does not register deferred widget props and shared Inertia data substitutes
empty navigation features plus null office and notification state. Logout stays
available through the shell and posts through Inertia.

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
