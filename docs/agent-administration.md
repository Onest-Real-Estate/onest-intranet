# Agent administration

The self-service profile at `/profile` is what an agent maintains about
themselves ([docs/profile.md](profile.md)). This document is its mirror: the
half of a profile that only the brokerage may set, and the page that sets it.

The code is `apps/user/administration_fields.py`,
`apps/user/services/agent_administration.py`,
`apps/user/views/administration_views.py`, `AgentAdministrationForm` in
`apps/user/forms.py`, and `frontend/pages/UserAdministration.tsx`.

## Surfaces

| Route | Name | Permission | Purpose |
| --- | --- | --- | --- |
| `GET /operations/users/<id>/administration` | `user_administration` | `user.view_user_administration` | One user's administrative record |
| `POST /operations/users/<id>/administration/submit` | `user_administration_submit` | `user.change_user_administration` | Persist the administered fields |
| `POST /operations/users/<id>/administration/roles` | `user_administration_roles` | `user.change_user_administration` | Grant or revoke one role assignment |
| `POST /operations/users/<id>/account-state` | `user_account_state` | `user.manage_account_state` | Disable or reactivate the account |

These are a separate POST contract from `profile_submit` on purpose. Mixing
privileged inputs into the self-service form would mean one endpoint carrying
two very different grants. Account access is separate again — see below.

The record is reached from the people directory at `/operations/users`
([user-directory.md](user-directory.md)), which owns search, filters, and
scoped counts.

## What an administrator may change

`services.agent_administration.ADMINISTERED_FIELDS` is the single allowlist,
and it is exactly `AgentAdministrationForm.Meta.fields`.

| Field | Owner | Notes |
| --- | --- | --- |
| `office` | Broker administration | High impact — moves scope, and retires the stale office-scoped Agent assignment |
| `agent_status` | Broker administration | High impact — `prospective`, `active`, `on_leave`, `suspended`, `departed` |
| `start_date` | Broker administration | Join date; more than a year out is rejected as a typo |
| `agent_identifier` | Broker administration | Internal ID, uppercased, unique when set |
| `license_verification_state` | Broker compliance | `unverified`, `pending`, `verified`, `rejected` |
| `license_verification_note` | Broker compliance | What was checked, against which record |
| `internal_notes` | Broker administration | Private — see below |

Role and scope assignments are **not** in that list. They go through
`services.role_assignments`, which owns delegation, effective dates, and its
own audit events; the administration page is only a caller. Brokerage
administrators with `web.assign_user_roles` also have the dedicated Assign User
Roles workspace ([role-assignment-administration.md](role-assignment-administration.md)),
linked from this panel when they may open it.

Contract status has no column at all. It is read from the contract domain by
`agent_administration.contract_status()` and reported as unavailable until that
module is connected. A status an administrator can type into a profile is a
status that drifts from the contract it claims to describe.

## What nobody may change here

Email, `is_staff`, `is_superuser`, `is_active`, groups, direct permissions,
onboarding state, and every self-service field are absent from `Meta.fields`,
so `construct_instance` never writes them — a crafted POST carrying
`is_superuser=1` saves the rest and changes nothing about the account.

Nobody administers their own record, superusers included.
`ensure_change_authority` refuses when `actor.pk == target.pk`, which closes
self-promotion at the same door that `ensure_assignment_authority` already
closes for roles.

## Permissions and scope

Three permissions, declared on `User.Meta`:

- `user.view_user_administration` — read the record
  (`0014_agent_administration_permissions`).
- `user.change_user_administration` — write it (same migration).
- `user.manage_account_state` — disable or reactivate the account
  (`0018` / `0019`), granted to **Admins**, **Principal Broker**, and **Broker
  Admin** only.

The first two go to **Admins**, **Region Managers**, and **Branch Managers**. The
permission is the gate; **scope** decides which users it opens:

- Superusers and company-wide Admins: everyone.
- Region Managers: users whose office sits in a region they hold.
- Branch Managers: users in an office they hold.
- A user with **no office** is reachable only company-wide — no scope can be
  said to contain them.

Scope is applied on the queryset (`administered_user_queryset`), never in
Python and never from a client-supplied office. A target outside scope is a
**404**, not a 403: confirming that an id exists is itself a disclosure across
a scope boundary.

Delegation is checked separately from reach:

- `assignable_office_queryset` limits the offices somebody may be moved *into*.
- `delegable_role_options` offers only roles the assignment service would
  accept, so a Branch Manager sees no grant form at all and the `Admins` role
  is never delegable by anybody.

## Field-level reads inside the record

Reaching the page is one grant; two blocks on it need another, and are
**omitted** from the payload rather than blanked:

| Block | Needs | Why |
| --- | --- | --- |
| `values.internalNotes` and its field spec | `user.change_user_administration` | Reading somebody's operational note is not implied by being allowed to look them up |
| `contractStatus` | `web.view_agent_contracts` | Contract standing belongs to the contract domain; administering a record is not reading their contract |

A key that is present but empty would still confirm the field exists, so the
key is absent and the page renders no card at all.

## Account access

Disabling and reactivating live in `services/account_state.py`, not here.
`is_active` is not an administered field, does not appear in
`AgentAdministrationForm`, and cannot ride along on a record save. The service
is explicit, idempotent, session-invalidating, and audited; the policy is
documented in [user-directory.md](user-directory.md#account-access). The record
page renders it as its own panel with its own confirmation and a required
business reason.

## Confirmation and access impact

`HIGH_IMPACT_FIELDS` (`office`, `agent_status`) cannot be submitted without
passing through `AccessChangeDialog`, which lists the old value, the new value,
and what the change does — including that an office move retires the Agent
assignment in the old office. The dialog is a courtesy to the person using the
page; the server does not depend on it.

## Concurrency

`user.administration_updated_at` doubles as an optimistic-concurrency token.
The page renders it as `expected_version` and posts it back; a mismatch means
somebody else saved first, and the request returns **409** with the newer
values and a form-level message rather than overwriting them. The write itself
takes `select_for_update` on the row.

## Recalculating access

Effective access is computed per request, so a role or office change is live on
the target's next request. `invalidate_permission_cache` additionally drops
Django's per-instance `_perm_cache` / `_group_perm_cache` and the shell's
cached access context, so an in-process instance cannot keep answering from a
cache filled before the move.

## Edge cases

| Case | Behavior |
| --- | --- |
| Office closed under a seated user | Stays selectable and saveable; moving anybody *into* it is refused. `User.clean` only rejects a *move* into a closed office |
| Future-dated assignment | Created `scheduled`; grants nothing until `starts_at` |
| Multiple roles on the actor | Scopes union; they never narrow each other |
| Last live assignment of a working agent | Revocation refused — assign a replacement, or set the status to `suspended`/`departed` first |
| Assignment belonging to another user | 404; the id is matched against the target |

## Privacy: operational notes

`internal_notes` is the one field with an explicit privacy policy:

1. It is never part of the payload an agent receives. `administration_summary`
   — the block rendered read-only on `/profile` — does not contain it.
2. Its **text** is never written to the audit trail. `_audit_snapshot` records
   `internal_notes_present: true|false` and nothing else, so the trail still
   shows that notes changed, who changed them, and when.
3. It is visible only to administrators who already hold the change permission
   for that user.

## Audit

| Action | When |
| --- | --- |
| `user.administration.updated` | A successful save, with a before/after diff over `AUDIT_VALUE_FIELDS` |
| `security.user_administration.denied` | A denied view, change, self-administration attempt, or out-of-delegation office |
| `user.license_verification.reset` | An agent edited their own license, invalidating a broker verification |
| `user.account.disabled` / `.reactivated` | An account was closed or reopened, with the reason and the session count |
| `security.account_state.denied` | A denied or self-directed account-access attempt |
| `user.role_assignment.created` / `.revoked` | From the assignment service, unchanged |

The first four actions are what the record's **recent activity** panel renders;
`administration_history` filters on exactly that closed list, and on events
whose audit target is the user row itself. Role assignments are their own
target type with their own panel.

Denial events are written **outside** the transaction that would roll them
back. That is load-bearing, not incidental: a denial recorded inside the atomic
block disappears with the exception it exists to explain.

## The agent's own view

`/profile` renders `identity.administrative` read-only in
`ProfileAdministrativePanel`: agent status, start date, agent ID, license
verification, and contract status. Two independent guards keep it read-only:

1. No control exists on the page.
2. `_PROTECTED_FIELDS` in `apps/user/views/auth_views.py` includes every name in
   `ADMINISTERED_FIELDS`, so `profile_submit` returns **403** and records
   `security.profile.protected_field_rejected` if one appears in a POST.

An agent editing their own `license_number`, `license_state`, or
`license_expires_on` resets the verification to `unverified`. Otherwise an
agent could carry a broker's verification of an old license onto a new number
nobody checked.

## Adding an administrative field

1. Add the model field, its normalizer in `administration_fields.py`, and a
   migration.
2. Add it to `ADMINISTERED_FIELDS` — that alone protects it on `/profile`.
3. Add an `AdminFieldSpec`, and to `AUDIT_VALUE_FIELDS` only if the value is
   safe to keep in the trail.
4. Add the declared field to `AgentAdministrationForm` and the prop to
   `ADMINISTRATION_FIELD_MAP`.
5. Add the control to `frontend/pages/UserAdministration.tsx` and the label to
   its `ERROR_LABELS`.
6. Cover authorization, scope, and a rejection case in
   `apps/user/tests/test_agent_administration.py`.
