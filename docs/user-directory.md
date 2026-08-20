# User directory

The Users destination under Operations (`/operations/users`) is the product
answer to "find this person and sort them out" — the surface that exists so
nobody needs unrestricted Django admin to do routine people work.

The code is `apps/user/services/user_directory.py`,
`apps/user/services/account_state.py`, `apps/user/views/directory_views.py`,
and `frontend/pages/UserDirectory.tsx`. The record a row opens into is
documented in [agent-administration.md](agent-administration.md).

## Surfaces

| Route | Name | Permission | Purpose |
| --- | --- | --- | --- |
| `GET /operations/users` | `admin_users` | `web.view_users` | Scoped directory: search, filter, review |
| `GET /operations/users/<id>/administration` | `user_administration` | `user.view_user_administration` | One user's administrative record |
| `POST /operations/users/<id>/account-state` | `user_account_state` | `user.view_user_administration` + `user.manage_account_state` | Disable or reactivate one account |

The directory replaced the thin picker that used to live at
`/operations/users/administration`. There is one people list, and the record
is reached from it.

## Scope comes first, always

`directory_queryset()` is `administered_user_queryset()` — the actor's own
office and region grant, resolved from `get_effective_access`, applied in SQL.
Search, filters, sorting, counts, and pagination all run **inside** that
queryset:

- a crafted `office=` or `region=` id intersects an already-narrowed set and
  returns an empty page, never a wider one, and never reveals whether the id
  exists;
- `summary` (total / active / disabled / onboarding incomplete) is computed
  from the same scoped queryset, so the counts cannot be used to probe for
  people outside it;
- an out-of-scope id typed straight into `/operations/users/<id>/administration`
  is a **404**, not a 403 — a 403 would confirm the row exists.

An actor with no scope at all gets an empty directory and an empty summary,
with wording that says so.

## Field-level permissions

Reaching the directory is one grant; reading a column is another. Rows **omit**
the keys a reader may not have rather than sending `null` — a key that is
present but empty still tells you the field exists.

| Bundle | Permission | Columns |
| --- | --- | --- |
| Identity | `web.view_users` | Name, email, office, region, account state, last sign-in, onboarding |
| Administration | `user.view_user_administration` | Agent status, agent ID, start date |
| Contract | `web.view_agent_contracts` | Contract standing |
| Notes | `user.change_user_administration` | Operational notes (record page only) |

Consequences worth stating out loud:

- **IT support visibility does not imply contract visibility.** Holding
  `web.view_users` lets somebody look people up; it never carries contract,
  commission, client, or transaction data with it.
- Search matches an **agent ID** only for readers who may see agent IDs.
  Otherwise a hidden identifier could be recovered one character at a time.
- The **agent-status filter** is not honoured without the administration grant,
  and the option list is not sent. A reader who cannot see a column must not be
  able to partition the directory by it either.
- **Sorting** by a hidden column falls back to name rather than erroring.

The page mirrors all of this through `visible` and `canOpenRecord`, which
decide whether a column, a filter, or a row action exists at all. That mirror
is a courtesy; the server payload is the control.

## Filters

Every value is validated against a closed set and silently dropped when it is
not recognized — never echoed back, never passed to the ORM.

| Filter | Values | Where it runs |
| --- | --- | --- |
| `q` | Free text | Name, email, display/preferred name (+ agent ID when permitted) |
| `office`, `region` | Scoped office ids | SQL, intersected with scope |
| `role` | Catalog role code | Live (`scheduled` / `active`) assignments only |
| `status` | Agent status | SQL, administration grant required |
| `account` | `active`, `disabled` | SQL |
| `onboarding` | `complete`, `in_progress`, `not_started` | SQL |
| `contract` | Contract domain values | Contract domain, when connected |
| `lastLogin` | `7d`, `30d`, `90d`, `over_90d`, `never` | SQL |

**Directory onboarding state is deliberately coarser** than the New Agent
List's. This one asks only whether the person finished the hub's own profile
flow (`profile_completed`, plus whether they have ever signed in). The New
Agent List asks the contract and training domains. Two names for two questions
beats one name that means different things on two pages.

**The contract filter is rendered disabled with its reason** while the contract
domain is not connected, rather than silently absent — nobody should read "no
contract filter" as "no contracts".

## Account access

Disabling somebody is not "changing a field", so it does not travel on the
record form:

- its own permission, `user.manage_account_state`, granted by default to System
  Admin, Principal Broker, and Broker Admin only;
- its own endpoint and its own form (`AccountStateForm`) — never a `ModelForm`,
  because `is_active` reached through a generic model form is one crafted field
  away from `is_staff`;
- its own confirmation, which will not submit without a business reason;
- the same optimistic-concurrency token as the record form, so a stale page
  gets a 409 instead of overwriting somebody else's decision.

Nobody changes their own account access, superusers included.

**Enforcement.** Disabling ends every unexpired session belonging to that user,
inside the same transaction as the flag, so the person is signed out
immediately rather than whenever their cookie expires. Django keeps no
user → session index, so the sweep decodes live session rows and matches
`_auth_user_id`; a row that will not decode is treated as "not this user"
rather than raising. Deletion goes through the **configured session engine**,
not `Session.objects.delete()` — under `cached_db` (what this project runs
whenever Redis is configured) a read is served from the cache first, so
dropping the database row alone would leave a working session in Redis until
it expired on its own. Reactivating restores the ability to sign in; it does
not resurrect the old sessions.

**Idempotence.** Disabling an already-disabled account changes nothing, writes
no second lifecycle event, and does not bump provenance. A repeated submit must
not read as a second decision in the trail.

**Trail.** Every change emits `user.account.disabled` or
`user.account.reactivated` with before/after, the business reason, the office
and region, and `sessions_revoked` in metadata — plus the
`user.account.state_changed` domain event, dispatched after commit. Denials
emit `security.account_state.denied`. All four actions surface in the record's
recent-activity panel.

## Concurrency

The directory is a read surface and needs no token. Both write surfaces on the
record — the administration form and account access — carry
`administration_updated_at` as `expected_version`. A mismatch is a **409** with
the newer values rendered and the message "somebody else changed this record",
not a 422: nothing the administrator typed is wrong.

## States the page must keep

Empty scope, no results after filtering, a disabled account, a read-only
reason where a control would be, a disabled filter with its reason, and a
stale-edit conflict all have their own wording. "Nobody in your scope yet" and
"Nobody matches" are different sentences because they need different actions.
