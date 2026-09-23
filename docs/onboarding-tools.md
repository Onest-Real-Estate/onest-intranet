# Agent tool catalog

What a new agent needs set up, where to get each one, and how far they have got.
Lives in `apps/onboarding_tools`.

## Why this is data

The list used to be four values in a `TextChoices` enum. That shape cannot
express this catalog:

- it is ~23 tools across three groups, and it grows;
- it changes whenever a vendor does;
- **the MLS and association entries depend on where the agent works.** SmartMLS
  and CT Realtors belong to Connecticut; an agent in Virginia needs neither.

Every one of those facts would otherwise be a deploy. So the catalog is a table,
modelled on `web.QuickAccessLink`, which learned the same lesson: *"The panel
used to be a tuple… changing it meant a deploy."*

## Every tool says how to get it

This is what makes the catalog worth having rather than a list of names. Each
row carries either:

- **`setup_steps`** — an ordered list of plain strings the agent follows now, or
- **`contact_label`** — who at oNEST turns it on ("your branch admin", "IT
  support"), optionally with `request_path` pointing at the IT support form.

`provisioning` names which case applies: `self_serve`, `onest`, or `both` (the
agent signs up, oNEST then activates). A **database constraint refuses a row
with neither steps nor a contact** — a checklist that says "you need HiHello"
without saying how to get it has moved the problem, not solved it.

`contact_label` is free text on purpose: it is "your branch admin" as often as a
named person, and modelling it as a user would break the moment somebody leaves.

## Location

`OnboardingTool.objects.for_office(office)` resolves what applies:

1. `company_wide` tools always apply.
2. Otherwise the tool names offices or regions in
   `OnboardingToolOfficeAudience`. `include_descendants` covers every branch
   beneath a node, so SmartMLS attaches **once** to Connecticut.

An agent with **no office** gets only the company-wide set. Guessing an
association from a blank field would tell somebody to join the wrong MLS.

Cost is one query for the catalog, one for the agent's statuses, plus a walk up
the office tree. That walk is O(tree depth) and **not** O(tools) — the cost does
not grow as the catalog does.

## Progress

`AgentToolStatus` holds one agent's state on one tool:
`not_started · requested · invitation_sent · in_progress · ready · blocked ·
not_applicable`.

- **Rows are created lazily.** A tool with no row reads as "not started", so
  adding a tool to the catalog does not write a row for every agent.
- **`ready` and `ready_at` travel together**, enforced by a constraint, so any
  figure asking "when did this agent become workable" has one answer.
- **`not_applicable` counts as settled.** Somebody excused from a tool is not
  outstanding work.
- **`is_required=False` tools are excluded from the figure.** Facebook and
  Instagram are available, not expected; counting them would make 100%
  unreachable.

### The invitation checkpoint

`requested` and `invitation_sent` exist because "in progress" could not answer
the question activation depends on: *has the office actually sent this agent
their Lofty or SkySlope invitation, and when?* A note cannot be queried, and
audit history is not a state machine.

`invitation_sent_at` and `invitation_sent_by` are columns, not prose. Two
constraints keep them honest: `invitation_sent` requires a timestamp, and a
named sender requires one too — the reverse is allowed, because deleting the
sender's account must not erase the fact that it was sent. Nothing about the
vendor account is stored: no password, invitation link, token, or email body.

### Which moves are allowed

Skipping *forward* is ordinary — a self-serve tool goes straight to `ready`.
Two rules are enforced server-side by `services.validate_transition`:

- `requested` and `invitation_sent` are refused for a `self_serve` tool.
  Nobody sends an invitation for an account the agent creates.
- Moving **back** down `not_started → requested → invitation_sent →
  in_progress → ready`, or out of a settled state, requires a business reason
  in `note`. That is the correction path for somebody who marked an invitation
  sent by mistake: the agent was told it was sent, so the reversal is recorded
  against whoever made it. Dropping back behind the invitation clears its
  provenance; states after it keep it.

Every accepted change writes an audit entry and publishes
`onboarding_tool.state_changed`, carrying the tool slug, agent, office, the
enum transition, the actor, and the invitation timestamp — never the note.

The New Agent workspace asks this source for a generic capability list rather
than branching on Lofty, SkySlope, or any other slug. Provisioning mode,
current state, completed setup, delivery outcome, and the actor's live grant
determine which of `mark_invitation_sent`, `revoke_invitation`, `mark_ready`,
`mark_blocked`, and `retry_notification` is enabled. The write path resolves
the current applicable catalog row again after locking; an inactive tool or an
office move cannot be acted on from a stale page.

Recording `invitation_sent` produces one mandatory notification for the target
agent, keyed by agent/onboarding-version/tool/transition. It says which tool to
look for in Microsoft Outlook and links through the typed dashboard onboarding
action. It never stores or sends a vendor invitation URL. In-app truth survives
an outbound provider failure; email/Microsoft attempts remain in the
notifications ledger and an authorized administrator can explicitly requeue a
failed attempt without changing the tool state.

## One source of truth

`user.OnboardingToolSetup` was a second, enum-shaped copy of this: four tools,
read by the operational composer while My Tools read the catalog, and the two
disagreed. Every read and write now goes through this app —
`onboarding_state`, the New Agent List, the dashboard, and My Tools — and
`onboarding_tools/migrations/0004` folds the legacy rows in, mapping
`microsoft365 → office-365` and `not_required → not_applicable`. Where both
sides held a row, the further-along state survives and ties go to the more
recently updated one. `dotloop` has no catalog row (the brokerage retired it),
so those rows are left alone rather than invented into a tool nobody uses.

The legacy model still exists and still holds its rows: nothing reads or writes
it, and it is kept for one release so a rollback loses nothing. Removing the
table is a follow-up migration once this has shipped and been verified in
production.

### Who may change it

`services.set_state` requires `web.manage_new_agent_onboarding` — the grant that
already runs onboarding. There is deliberately **no new permission**: the people
who do this work already hold it, and a second grant is one more thing to forget.

The office handoff notifies the office's **Branch Admin**, whose default role
bundle holds `web.view_new_agents` but not this grant: today they can open the
case, while a Branch Manager or company admin records the invitation. Whether
Branch and Regional Admins should hold it is an open product decision; see
[onboarding-support.md](onboarding-support.md#product-owner-sign-off).

**Self-management is refused**, matching the New Agent List. An agent marking
their own Office 365 "ready" tells nobody anything, and the figure would stop
meaning "IT confirmed this works".

### The agent's own mark

`AgentToolStatus.agent_confirmed_at` is the agent ticking "I have this" on
`/my-tools`. It is a **separate fact from `state`**, not a way round the rule
above: the agent sets it, only on their own row, through
`POST /my-tools/<slug>/have` (`services.set_agent_confirmation`), and only for a
tool on their own resolved checklist — a slug for another office's MLS is a 404.
It never moves `state`, `ready_at`, or the readiness figure, so "Ready" still
means somebody at oNEST confirmed it. Staff see the tick beside the state on the
per-agent page. Each change writes an `onboarding_tool.agent_confirmed` /
`agent_unconfirmed` audit entry; a repeated tick is a no-op.

### Who may watch it

`AgentToolStatus.objects.for_reader(user, access=…)` is the ordinary office-tree
reach, with no extra grant:

| Reader | Sees |
| --- | --- |
| Any agent | Their own |
| Branch manager | Their branch |
| Regional | Their region |
| Broker / admin | The brokerage |

If you may already see the agent in the directory, you may see whether their
email works.

## Relationship to IT Support

`apps/it_support` has a **New agent setup** category and an `about_user` field:
that is the *request* asking IT to do the provisioning. The **checklist is here**
and nowhere else. Two sources of truth would disagree within a week.

## Seeding

`migrations/0002_seed_catalog` writes the initial rows from
`apps.onboarding_tools.catalog`. It is idempotent by slug and **never updates an
existing row** — an administrator who corrected a contact name should not have
that overwritten by a redeploy. Reversing it deletes only rows nobody has
recorded progress against.

Office slugs the deployment does not have are skipped rather than failing the
migration: the seed must not depend on one brokerage's office tree.

## Managing the catalog

`/operations/tool-catalog` behind **`web.manage_onboarding_tools`**.

That is a **separate grant from `manage_new_agent_onboarding`** on purpose: a
branch manager runs onboarding for their branch, and deciding what every office
in the brokerage needs is a different, wider decision. Holding one does not
imply the other.

Editing happens in a **side sheet** over the list rather than on a separate
page, so "does this read right next to its neighbours" stays answerable while
editing.

### The guide editor

Steps are edited as an ordered list of fields, not a textarea split on newlines.
The textarea looks simpler right up to the moment somebody pastes a wrapped
sentence and silently gains two steps. Each step posts as a repeated `step`
value, read with `getlist`, so the form still works as a plain POST.

A guide is capped at 12 steps. Longer than that is a document, and the tool
should link to it instead.

### What a save enforces

- **Steps or a contact.** The form raises it on the field so the writer knows
  what to fix; the database constraint catches it regardless.
- **A location-specific tool must name somewhere.** Otherwise it applies to
  nobody and silently disappears from every checklist.
- **Office choices are the editor's own scoped set**, so a posted id outside it
  fails validation rather than being quietly accepted.
- **Audience rows are replaced wholesale**, never diffed. Reconciling a partial
  edit is how an office quietly survives being unticked.
- **Reordering only touches rows already in that group**, so a crafted post
  cannot drag a marketing tool onto the company shelf.

Every save and reorder writes an audit event.

### Identifier and links

- **The identifier is derived from the name** when left blank and **locked once
  saved**: training items join on it through `tool_code`, and audit history
  names it. The form disables the field on edit, so a posted change is ignored.
- **`request_path` is an in-app path only** (`/…`, never `//host`,
  `javascript:`, or another site). It renders as the Support link on every
  agent's card, so it is validated rather than trusted.

### What each row reads (`catalog_admin.py`)

Bounded queries whatever the catalog size (a test pins that adding a tool adds
none):

- **Health** — `ToolHealth` gaps on active rows: `no_audience`, `no_training`
  (no *published* item tagged with the slug), `no_open_link`. Only the first two
  put a row on **Needs attention**; a missing open link is named on the row but
  would otherwise flag nearly the whole catalog.
- **Training** — per-tool counts across all non-archived items, plus up to three
  items from the reader's own `manageable_queryset`, so an edit link never 404s.
- **Adoption** — ready, blocked, and *ticked but not yet confirmed* counts from
  `AgentToolStatus.for_reader`, i.e. only agents within the reader's reach. The
  summary's "Agent ticks to confirm" links to the readiness queue; the per-agent
  page offers **Confirm ready** on exactly those rows.

Search (`q`) and status (`show`: all · attention · active · inactive) live in the
URL. Reordering is offered only on the unfiltered list, because moving a row
relative to neighbours the administrator cannot see is not a decision they can
make. The editor is a side sheet opened by `?edit=<slug>` / `?edit=new`, posted
through Inertia with the page's validation contract.

## Surface

| Route | Who | What |
| --- | --- | --- |
| `/my-tools` | Everyone | Your own checklist and every setup guide |
| Dashboard setup dialog | Agent journey | Next steps: inbox guidance, contract, and per-tool activation guides |
| `/operations/tool-readiness` | `web.view_new_agents` | How far the people you cover have got |
| `/operations/tool-readiness/<id>` | Same, scoped | One agent's checklist, editable |

`/my-tools` and the per-agent page are the **same component**. What differs is
`canManage`, which the server decides — and which is false for an administrator
looking at their own rows, because self-attestation would make the figure
meaningless.

### Layout

Cards in container-query columns, grouped by shelf, with the checkbox leading
each card because checking off is the page's job. A ruled summary strip above
them fills one segment per counted tool (required and not excused), in catalog
order, and keeps "Confirmed by oNEST" apart from the agent's own count.

### Card actions

Each card on `/my-tools` carries the agent's tick plus three ways to get
unstuck:

- **Training** — the tool's current activation guide from
  `training.tool_guides.activation_guides_for`, resolved once for the whole
  checklist and for the *reader*, so the button never links to an item they
  cannot open. No offerable guide, no button.
- **Support** — the row's `request_path` when an administrator set one,
  otherwise `/support/it?tool=<slug>`, which opens the IT form with the subject
  and category filled in. Only a live catalog slug is honoured and only the
  tool's own name is written into the draft.
- **Setup** — the steps and contact, in a dialog.

A blocked row shows its note **to the agent**, not only to staff: the reason you
are stuck is the one thing you most need. Only the control that changes the state
is restricted.
