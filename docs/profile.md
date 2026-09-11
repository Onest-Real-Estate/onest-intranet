# Agent profile

The self-service profile at `/profile` is where a signed-in user maintains
everything about themselves that is not owned by Microsoft or by an
administrator. This document is the contract; the code is
`apps/user/profile_fields.py`, `apps/user/forms.py`,
`apps/user/services/profile.py`, and `frontend/pages/Profile.tsx`.

## What a user may change

The single allowlist is `SelfProfileForm.Meta.fields`, re-exported as
`apps.user.forms.SELF_EDITABLE_FIELDS`. Nothing outside it can be written
through `profile_submit`.

| Section | Fields |
| --- | --- |
| Contact | `first_name`, `last_name`, `preferred_name`, `phone_number`, `preferred_contact_method` |
| Address | `street_address`, `city`, `state`, `zip_code` |
| Credentials | `office`¹, `mls_number`, `nrds_number`, `license_number`, `license_state`, `license_expires_on` |
| Biography | `bio`, `languages`, `specialties` |
| Links | `website_url`, `linkedin_url`, `facebook_url`, `instagram_url`, `x_url` |
| Photo | `headshot`, through its own endpoint |

¹ Only when `services.profile.can_self_assign_office()` is true — see below.

Specialties are a closed set (see `SPECIALTY_CHOICES` in `profile_fields.py`)
and appear in the peer [agent directory](agent-directory.md).

## What a user may not change

Email, roles, permissions, account status, staff flags, onboarding state, and
internal identifiers are all read-only. So is everything in
`services.agent_administration.ADMINISTERED_FIELDS` — agent status, start date,
agent ID, license verification, and operational notes — which the brokerage
maintains from its own page; see [agent-administration.md](agent-administration.md).
Two independent guards enforce this:

1. They are absent from the form's `Meta.fields`, so `construct_instance`
   never writes them.
2. `apps.user.views.auth_views._PROTECTED_FIELDS` rejects the whole request
   with **403** if any of those names appears in the POST at all, and records a
   `security.profile.protected_field_rejected` audit event carrying the
   rejected field *names* and none of their values. It is built from
   `ADMINISTERED_FIELDS`, so a new administrative field is protected here
   without anyone having to remember to add it.

The values an agent may *read* about their administrative record arrive as
`identity.administrative` and render in `ProfileAdministrativePanel`.
Operational notes are not part of that payload at all.

`profile` and `profile_submit` only ever read `request.user`. There is no user
identifier in the URL, the form, or the payload, so no request shape can read
or write another user's record.

### Office is administrative for anyone it scopes

`can_self_assign_office()` returns false for staff, superusers, and anyone
holding a role other than Agent. Their office determines what they can see
across the hub, so moving it is an administrative act. For those users:

- the `office` field is removed from the bound form,
- `office` joins the protected set, so submitting it returns 403,
- `offices` ships empty and the page renders the office read-only with an
  explanation of who to ask.

When an agent *does* move office,
`services.role_assignments.sync_default_agent_assignment` revokes the stale
office-scoped Agent assignment before creating the new one. Leaving both live
would quietly widen that agent's scope to two offices. The same function runs
when an administrator moves somebody from the administration page.

## Normalization

Every value goes through one function, called from both the model's
`clean_fields()` and the form's `clean_<field>()`, so a value written by
onboarding and the same value written here cannot drift:

| Value | Rule |
| --- | --- |
| Phone | `(XXX) XXX-XXXX` (`us.normalize_us_phone`) |
| ZIP | 5-digit or ZIP+4 (`us.normalize_us_zip`) |
| NRDS | 8–9 digits, punctuation stripped (`us.normalize_nrds`) |
| License number | Trimmed, whitespace collapsed, uppercased |
| URLs | Bare hosts upgraded to `https://`; host lowercased; credentials, non-web schemes, and >255 characters rejected |
| Social URLs | Additionally checked against the owning platform's host allowlist |
| Bio | CRLF normalized, blank-line runs capped, 1500-character limit |
| Languages | Deduplicated, ordered, validated against `LANGUAGE_CHOICES`, max 10 |
| Blank | Always the empty string (or `NULL` for the license date), never `None` in a `CharField` |

Editing `license_number`, `license_state`, or `license_expires_on` resets the
brokerage's `license_verification_state` to `unverified` and writes a
`user.license_verification.reset` event: a verification belongs to the license
that was checked, not to whatever number replaces it.

Normalization happens in `clean_fields()` rather than `clean()` because
`full_clean()` runs field validators first: normalizing any later would let
`URLField`'s validator reject `example.com` before it was upgraded.

## Adding a field

1. Add the model field, the normalizer in `profile_fields.py`, and a migration.
2. Add it to `SelfProfileForm` (declared field + `Meta.fields`) and to
   `SELF_PROFILE_FIELD_MAP` so the camelCase prop exists.
3. Add a `ProfileFieldSpec` in `services/profile.py` if it counts toward
   completeness.
4. Add the control to the matching section in
   `frontend/components/profile/ProfileFormSections.tsx` and the label to
   `ERROR_LABELS` in `frontend/pages/Profile.tsx`.
5. Cover normalization, persistence, and a rejection case in
   `apps/user/tests/test_profile_fields.py` and `test_profile.py`.

## Photo

The headshot is the one thing that does not save with the form. It posts to
`POST /account/headshot` (route name `headshot_upload`), shared by onboarding
and the profile page, which validates with Pillow, stores under a UUID name
from `headshot_upload_path` (the browser's filename is never trusted), and
returns JSON so the page can show progress, a preview, and a server error in
place. `remove=1` on the same endpoint deletes the stored photo and is
idempotent. Both outcomes emit `user.headshot.updated` /
`user.headshot.removed` audit events recording only that a photo changed —
never the file, its name, or its URL.

## Completeness

`services.profile.profile_completeness()` scores the fields in
`PROFILE_FIELD_SPECS` and returns the ones still empty, tagged `required` when
they belong to onboarding. It is reporting, never a gate: a user whose
onboarding is complete keeps full access at any score.

## Audit

A successful save writes `user.profile.updated` with a before/after diff over
`_PROFILE_AUDIT_FIELDS`. Home address, phone, email, and the photo are
excluded, and `apps.audit.service.redact` would strip them regardless.
