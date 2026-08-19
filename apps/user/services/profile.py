"""Self-service profile policy and completeness.

Two questions live here, both of which the view and the page need the same
answer to:

* which of the profile's own fields the signed-in user is allowed to set, and
* how complete their professional profile is, and what is still missing.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.utils import timezone

from apps.user.models import User
from apps.user.profile_fields import LANGUAGE_NAMES, SOCIAL_PLATFORMS
from apps.user.roles import AGENT, ROLE_LABELS, SUPERADMIN_LABEL
from apps.user.services.role_assignments import get_effective_role_keys

# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

PHOTO = "photo"
CONTACT = "contact"
ADDRESS = "address"
CREDENTIALS = "credentials"
BIOGRAPHY = "biography"
LINKS = "links"

SECTION_LABELS: dict[str, str] = {
    PHOTO: "Profile photo",
    CONTACT: "Contact details",
    ADDRESS: "Mailing address",
    CREDENTIALS: "Office and credentials",
    BIOGRAPHY: "Biography and languages",
    LINKS: "Website and social links",
}


@dataclass(frozen=True)
class ProfileFieldSpec:
    key: str
    label: str
    section: str
    # Collected during onboarding — an incomplete one is a data problem, not a
    # nudge, and it is never reported as an "optional field you could add".
    required: bool = False


PROFILE_FIELD_SPECS: tuple[ProfileFieldSpec, ...] = (
    ProfileFieldSpec("headshot", "Profile photo", PHOTO),
    ProfileFieldSpec("first_name", "First name", CONTACT, required=True),
    ProfileFieldSpec("last_name", "Last name", CONTACT, required=True),
    ProfileFieldSpec("phone_number", "Phone number", CONTACT, required=True),
    ProfileFieldSpec("preferred_contact_method", "Preferred contact method", CONTACT),
    ProfileFieldSpec("street_address", "Street address", ADDRESS, required=True),
    ProfileFieldSpec("city", "City", ADDRESS, required=True),
    ProfileFieldSpec("state", "State", ADDRESS, required=True),
    ProfileFieldSpec("zip_code", "ZIP code", ADDRESS, required=True),
    ProfileFieldSpec("office", "Office", CREDENTIALS, required=True),
    ProfileFieldSpec("license_number", "License number", CREDENTIALS),
    ProfileFieldSpec("license_state", "License state", CREDENTIALS),
    ProfileFieldSpec("license_expires_on", "License expiration", CREDENTIALS),
    ProfileFieldSpec("mls_number", "MLS number", CREDENTIALS),
    ProfileFieldSpec("nrds_number", "NRDS number", CREDENTIALS),
    ProfileFieldSpec("bio", "Professional bio", BIOGRAPHY),
    ProfileFieldSpec("languages", "Languages", BIOGRAPHY),
    ProfileFieldSpec("website_url", "Website", LINKS),
    ProfileFieldSpec("social_links", "At least one social link", LINKS),
)


def _is_present(user: User, key: str) -> bool:
    if key == "headshot":
        return bool(user.headshot)
    if key == "office":
        return user.office is not None
    if key == "languages":
        return bool(user.languages)
    if key == "license_expires_on":
        return user.license_expires_on is not None
    if key == "social_links":
        return any(getattr(user, platform.field) for platform in SOCIAL_PLATFORMS)
    return bool(getattr(user, key, ""))


def profile_completeness(user: User) -> dict:
    """Percent complete plus the specific fields that are still empty.

    Reported for information only: a low score never blocks a user whose
    onboarding is already finished.
    """
    missing = [spec for spec in PROFILE_FIELD_SPECS if not _is_present(user, spec.key)]
    total = len(PROFILE_FIELD_SPECS)
    completed = total - len(missing)
    return {
        "completed": completed,
        "total": total,
        "percent": round(completed * 100 / total) if total else 100,
        "missing": [
            {
                "key": spec.key,
                "label": spec.label,
                "section": spec.section,
                "sectionLabel": SECTION_LABELS[spec.section],
                "required": spec.required,
            }
            for spec in missing
        ],
    }


def can_self_assign_office(user: User) -> bool:
    """Whether this user may move themselves between offices.

    An agent's office is a contact detail. For anyone carrying a management
    role or staff access it is part of what their authorization is scoped to,
    so moving it is an administrative action, not a self-service one.
    """
    if user.is_staff or user.is_superuser:
        return False
    return not (set(get_effective_role_keys(user)) - {AGENT})


def role_labels(user: User) -> list[str]:
    labels = [ROLE_LABELS.get(key, key) for key in get_effective_role_keys(user)]
    if user.is_superuser:
        labels.insert(0, SUPERADMIN_LABEL)
    return labels


def license_status(user: User) -> dict | None:
    """Expiry state for the stored license, or ``None`` when no date is set."""
    if user.license_expires_on is None:
        return None
    today = timezone.localdate()
    days = (user.license_expires_on - today).days
    if days < 0:
        return {"state": "expired", "days": days, "tone": "destructive"}
    if days <= 60:
        return {"state": "expiring", "days": days, "tone": "warning"}
    return {"state": "current", "days": days, "tone": "success"}


def language_labels(user: User) -> list[str]:
    return [
        LANGUAGE_NAMES[code] for code in user.languages or [] if code in LANGUAGE_NAMES
    ]


# ---------------------------------------------------------------------------
# Headshot lifecycle
# ---------------------------------------------------------------------------


def _log_headshot_change(user: User, action: str, *, had_photo: bool) -> None:
    from apps.audit.service import AuditTarget, actor_from_user, log_event

    # Deliberately no filename, no URL, no bytes: the audit trail records that
    # the photo changed and who changed it, not the image itself.
    log_event(
        action,
        actor=actor_from_user(user),
        target=AuditTarget(
            target_type=User._meta.label_lower,
            target_id=str(user.pk),
            target_label=user.email,
        ),
        before={"has_photo": had_photo},
        after={"has_photo": action != "user.headshot.removed"},
        office_id=(user.office.stable_key if user.office else ""),
    )


def replace_headshot(user: User, upload) -> str:
    """Store a validated upload, discarding whatever was there before."""
    had_photo = bool(user.headshot)
    if user.headshot:
        user.headshot.delete(save=False)
    user.headshot = upload
    user.save(update_fields=["headshot"])
    _log_headshot_change(user, "user.headshot.updated", had_photo=had_photo)
    return user.headshot.url


def remove_headshot(user: User) -> None:
    """Delete the stored photo. A no-op when there is nothing to delete."""
    if not user.headshot:
        return
    # ``FieldFile.delete`` clears the model attribute as well as the stored file.
    user.headshot.delete(save=False)
    user.save(update_fields=["headshot"])
    _log_headshot_change(user, "user.headshot.removed", had_photo=True)
