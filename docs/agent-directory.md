# Agent directory

The Agent Directory is the authenticated peer lookup for ONEST personnel —
find a colleague by name, office, region, role, license state, specialty, or
language. It is **not** the Operations Users directory; that surface is for
administrators and is documented in [user-directory.md](user-directory.md).

Code: `apps/user/services/agent_directory.py`,
`apps/user/views/agent_directory_views.py`,
`frontend/pages/AgentDirectory.tsx`, and
`frontend/pages/AgentDirectoryDetail.tsx`.

## Surfaces

| Route | Name | Access | Purpose |
| --- | --- | --- | --- |
| `GET /hub/agent-directory` | `agent_directory` | Authenticated | Search, filter, browse cards |
| `GET /hub/agent-directory/<id>` | `agent_directory_detail` | Authenticated | One allowlisted person |
| `GET /hub/agent-directory/<id>/headshot` | `agent_directory_headshot` | Authenticated | Stream a gated headshot |

There is no separate `view_agent_directory` permission. Privacy is enforced by
visibility and field allowlisting in the service layer.

## Visibility before search

`directory_visible_queryset()` is the only set the directory acknowledges:

- `is_active=True`
- `agent_status` in `{active, on_leave}`

Prospective, suspended, departed, and disabled accounts never appear in search,
filters, pagination totals, detail routes, or headshot streams. An out-of-policy
id is **404**, not 403 — a 403 would confirm the row exists.

Audience is **company-wide** among that visible set. Office and region filters
only narrow; they never widen beyond visibility.

## Field allowlist

Rows **omit** keys that are not directory-visible rather than sending `null`.

| Included | Source |
| --- | --- |
| Preferred display name | `preferred_name` / legal name fallback |
| Roles | Live role assignment labels |
| Office / region | Primary office presentation |
| Work phone / work email | `phone_number`, SSO `email` |
| Specialties / languages | Closed-set codes with labels |
| License state | Singular `license_state` (label only) |
| Headshot | Gated `headshotPath` route only |

Never included: home address, private notes, agent ID, agent status, account
state, permissions, contract standing, onboarding, MLS/NRDS, license number or
verification, social URLs, bio, or raw media URLs (`headshotUrl`).

## Headshots

Directory props never include permanent public media URLs. Cards and detail
pages receive `headshotPath` pointing at `agent_directory_headshot`, which
re-checks visibility before streaming. Image-failure UI falls back to a
non-photo placeholder when the stream errors.

## Contact actions

`tel:` and `mailto:` links are **external** contact methods (device phone /
mail app). Labels say “Call work phone” / “Email” so assistive technology does
not imply an in-hub messaging channel.

## Filters and URL state

Every filter value is validated against a closed set and silently dropped when
unrecognized. Query state lives in the URL (`q`, `office`, `region`, `role`,
`licenseState`, `specialty`, `language`, `view`, `page`) via the shared
`buildListUrl` helper.

## Profile seam

Agents maintain specialties on My Profile (same closed set the directory
filters on). See [profile.md](profile.md).
