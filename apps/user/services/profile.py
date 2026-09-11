"""Self-service profile policy and completeness.

Three questions live here, and every surface that edits a profile needs the
same answer to each:

* which of the profile's own fields the signed-in user is allowed to set,
* how complete their professional profile is, and what is still missing, and
* how each field behaves during first-login onboarding: which section asks for
  it, whether it is required, and who owns its value.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

from django.db import transaction
from django.utils import timezone

from apps.user.models import User
from apps.user.profile_fields import (
    LANGUAGE_NAMES,
    SOCIAL_PLATFORMS,
    SPECIALTY_NAMES,
    normalize_name,
)
from apps.user.roles import AGENT, ROLE_LABELS, SUPERADMIN_LABEL
from apps.user.services.role_assignments import get_effective_role_keys

logger = logging.getLogger(__name__)

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
    BIOGRAPHY: "Biography, languages, and specialties",
    LINKS: "Website and social links",
}


class OnboardingSection(StrEnum):
    """The short sections the first-login profile flow is split into."""

    IDENTITY = "identity"
    CONTACT = "contact"
    CREDENTIALS = "credentials"
    REVIEW = "review"


class FieldOwner(StrEnum):
    """Who is the source of truth for a value shown during onboarding."""

    AGENT = "agent"
    MICROSOFT = "microsoft"
    BROKERAGE = "brokerage"


@dataclass(frozen=True)
class ProfileFieldSpec:
    key: str
    label: str
    section: str
    # Collected during onboarding — an incomplete one is a data problem, not a
    # nudge, and it is never reported as an "optional field you could add".
    required: bool = False
    #: The onboarding section that asks for it. ``None`` leaves the field as
    #: post-onboarding enrichment on ``/profile``.
    onboarding_section: OnboardingSection | None = None
    #: The first ``User.onboarding_version`` the requirement applies to, so a
    #: newly required field can wait for the next onboarding cycle instead of
    #: changing the rules under somebody who is already part-way through.
    required_from_version: int = 0
    owner: FieldOwner = FieldOwner.AGENT
    #: Server-owned helper copy. Availability reasons live here, not in React,
    #: so a policy change does not need a frontend release.
    guidance: str = ""
    #: The form fields this spec covers. ``None`` means just ``key``; an empty
    #: tuple means no form writes the value (the headshot has its own endpoint).
    form_fields: tuple[str, ...] | None = None
    counts_toward_completeness: bool = True

    @property
    def field_names(self) -> tuple[str, ...]:
        return (self.key,) if self.form_fields is None else self.form_fields

    def is_required_for(self, user: User) -> bool:
        return self.required and user.onboarding_version >= self.required_from_version


PROFILE_FIELD_SPECS: tuple[ProfileFieldSpec, ...] = (
    ProfileFieldSpec(
        "headshot",
        "Profile photo",
        PHOTO,
        required=True,
        onboarding_section=OnboardingSection.IDENTITY,
        form_fields=(),
        guidance=(
            "A clear, recent photo of you on your own. It appears beside your "
            "name across the hub."
        ),
    ),
    ProfileFieldSpec(
        "first_name",
        "First name",
        CONTACT,
        required=True,
        onboarding_section=OnboardingSection.IDENTITY,
    ),
    ProfileFieldSpec(
        "last_name",
        "Last name",
        CONTACT,
        required=True,
        onboarding_section=OnboardingSection.IDENTITY,
    ),
    ProfileFieldSpec(
        "preferred_name",
        "Preferred name",
        CONTACT,
        onboarding_section=OnboardingSection.IDENTITY,
        counts_toward_completeness=False,
        guidance=(
            "Only if colleagues and clients call you something other than your "
            "legal first name."
        ),
    ),
    ProfileFieldSpec(
        "phone_number",
        "Phone number",
        CONTACT,
        required=True,
        onboarding_section=OnboardingSection.CONTACT,
    ),
    ProfileFieldSpec(
        "preferred_contact_method",
        "Preferred contact method",
        CONTACT,
        onboarding_section=OnboardingSection.CONTACT,
    ),
    ProfileFieldSpec(
        "street_address",
        "Street address",
        ADDRESS,
        required=True,
        onboarding_section=OnboardingSection.CONTACT,
    ),
    ProfileFieldSpec(
        "city",
        "City",
        ADDRESS,
        required=True,
        onboarding_section=OnboardingSection.CONTACT,
    ),
    ProfileFieldSpec(
        "state",
        "State",
        ADDRESS,
        required=True,
        onboarding_section=OnboardingSection.CONTACT,
    ),
    ProfileFieldSpec(
        "zip_code",
        "ZIP code",
        ADDRESS,
        required=True,
        onboarding_section=OnboardingSection.CONTACT,
    ),
    ProfileFieldSpec(
        "office",
        "Office",
        CREDENTIALS,
        required=True,
        onboarding_section=OnboardingSection.CREDENTIALS,
        owner=FieldOwner.BROKERAGE,
        guidance=(
            "The oNEST office you work from. Its administrator picks up your "
            "setup once you finish."
        ),
    ),
    ProfileFieldSpec(
        "license_number",
        "License number",
        CREDENTIALS,
        onboarding_section=OnboardingSection.CREDENTIALS,
        guidance=(
            "As printed on your real-estate license. Leave it blank if your "
            "license is still being issued."
        ),
    ),
    ProfileFieldSpec(
        "license_state",
        "License state",
        CREDENTIALS,
        onboarding_section=OnboardingSection.CREDENTIALS,
    ),
    ProfileFieldSpec(
        "license_expires_on",
        "License expiration",
        CREDENTIALS,
        onboarding_section=OnboardingSection.CREDENTIALS,
    ),
    ProfileFieldSpec(
        "mls_number",
        "MLS number",
        CREDENTIALS,
        onboarding_section=OnboardingSection.CREDENTIALS,
        guidance=(
            "Only if you already belong to an MLS. Leave it blank rather than "
            "entering a placeholder; you can add it later."
        ),
    ),
    ProfileFieldSpec(
        "nrds_number",
        "NRDS number",
        CREDENTIALS,
        onboarding_section=OnboardingSection.CREDENTIALS,
        guidance="Your 8- or 9-digit NAR member ID, if you are a REALTOR® member.",
    ),
    ProfileFieldSpec(
        "bio",
        "Professional bio",
        BIOGRAPHY,
        onboarding_section=OnboardingSection.CREDENTIALS,
    ),
    ProfileFieldSpec(
        "languages",
        "Languages",
        BIOGRAPHY,
        onboarding_section=OnboardingSection.CREDENTIALS,
    ),
    ProfileFieldSpec("specialties", "Specialties", BIOGRAPHY),
    ProfileFieldSpec(
        "website_url",
        "Website",
        LINKS,
        onboarding_section=OnboardingSection.CREDENTIALS,
    ),
    ProfileFieldSpec(
        "social_links",
        "At least one social link",
        LINKS,
        onboarding_section=OnboardingSection.CREDENTIALS,
        form_fields=tuple(platform.field for platform in SOCIAL_PLATFORMS),
    ),
)

# Profile fields whose audit snapshot is safe to keep. Contact details and the
# photo are excluded — ``apps.audit.service`` redacts them anyway, and there is
# no reason to route a home address through the event stream to find out.
PROFILE_AUDIT_FIELDS: list[str] = [
    "first_name",
    "last_name",
    "preferred_name",
    "state",
    "city",
    "office",
    "mls_number",
    "nrds_number",
    "license_number",
    "license_state",
    "license_expires_on",
    "preferred_contact_method",
    "languages",
    "specialties",
    "website_url",
    "linkedin_url",
    "facebook_url",
    "instagram_url",
    "x_url",
]


def is_field_present(user: User, key: str) -> bool:
    if key == "headshot":
        return bool(user.headshot)
    if key == "office":
        return user.office_id is not None  # ty: ignore[unresolved-attribute]
    if key == "languages":
        return bool(user.languages)
    if key == "specialties":
        return bool(user.specialties)
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
    specs = [spec for spec in PROFILE_FIELD_SPECS if spec.counts_toward_completeness]
    missing = [spec for spec in specs if not is_field_present(user, spec.key)]
    total = len(specs)
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
                "required": spec.is_required_for(user),
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


def specialty_labels(user: User) -> list[str]:
    return [
        SPECIALTY_NAMES[code]
        for code in user.specialties or []
        if code in SPECIALTY_NAMES
    ]


# ---------------------------------------------------------------------------
# Microsoft identity
# ---------------------------------------------------------------------------

MICROSOFT_PROVIDER = "microsoft"


@dataclass(frozen=True)
class MicrosoftLegalName:
    """The given name and surname Microsoft Entra ID holds for the account."""

    first_name: str
    last_name: str

    @property
    def complete(self) -> bool:
        return bool(self.first_name and self.last_name)


def microsoft_legal_name(user: User) -> MicrosoftLegalName | None:
    """Names from the user's linked Microsoft account, or ``None`` without one.

    Graph can send an empty or partial name. Callers treat only a complete
    name as authoritative and let the agent supply the rest.
    """
    from allauth.socialaccount.models import SocialAccount

    extra = (
        SocialAccount.objects.filter(user=user, provider=MICROSOFT_PROVIDER)
        .values_list("extra_data", flat=True)
        .first()
    )
    if extra is None:
        return None
    data = extra if isinstance(extra, dict) else {}
    return MicrosoftLegalName(
        first_name=normalize_name(str(data.get("givenName") or ""))[:150],
        last_name=normalize_name(str(data.get("surname") or ""))[:150],
    )


# ---------------------------------------------------------------------------
# Headshot lifecycle
# ---------------------------------------------------------------------------


class HeadshotStorageUnavailable(Exception):
    """The storage backend could not be reached. The request is safe to retry."""

    message = (
        "Photo storage is unavailable right now. Nothing you entered was lost. "
        "Try again in a minute."
    )


def _storage_failure(user: User, operation: str, exc: Exception):
    # A storage backend's exception text can carry the object key, so only its
    # type is logged: no storage path or filename reaches the log stream.
    logger.warning(
        "Headshot storage %s failed",
        operation,
        extra={"user_id": user.pk, "error_type": type(exc).__name__},
    )
    return HeadshotStorageUnavailable()


def _delete_stored_file(storage, name: str, user_id: int) -> None:
    try:
        storage.delete(name)
    except Exception as exc:
        # An orphaned file costs storage, not correctness; never fail the
        # request that already committed the replacement.
        logger.warning(
            "Superseded headshot could not be deleted",
            extra={"user_id": user_id, "error_type": type(exc).__name__},
        )


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


def replace_headshot(user: User, upload) -> None:
    """Store a validated upload, then retire the previous file.

    The new file is written before the old one is touched, and the old one is
    deleted only after the row commits. A storage outage or a failed save
    therefore leaves the photo the user already had in place.
    """
    had_photo = bool(user.headshot)
    previous_name = user.headshot.name if user.headshot else ""
    storage = user.headshot.storage
    try:
        # ``upload_to`` generates the UUID name; the client filename is dropped.
        user.headshot.save(upload.name, upload, save=False)
    except Exception as exc:
        raise _storage_failure(user, "write", exc) from exc
    new_name = user.headshot.name
    try:
        with transaction.atomic():
            user.save(update_fields=["headshot"])
            _log_headshot_change(user, "user.headshot.updated", had_photo=had_photo)
            if previous_name and previous_name != new_name:
                transaction.on_commit(
                    lambda: _delete_stored_file(storage, previous_name, user.pk)
                )
    except Exception:
        _delete_stored_file(storage, new_name, user.pk)
        raise


def remove_headshot(user: User) -> None:
    """Clear the stored photo. A no-op when there is nothing to remove."""
    if not user.headshot:
        return
    storage = user.headshot.storage
    name = user.headshot.name
    with transaction.atomic():
        user.headshot = None  # ty: ignore[invalid-assignment]
        user.save(update_fields=["headshot"])
        _log_headshot_change(user, "user.headshot.removed", had_photo=True)
        transaction.on_commit(lambda: _delete_stored_file(storage, name, user.pk))


def headshot_is_stored(user: User) -> bool:
    """Whether the recorded photo exists in storage right now.

    Raises ``HeadshotStorageUnavailable`` when storage cannot answer, so a
    caller never mistakes an outage for a missing photo.
    """
    if not user.headshot:
        return False
    try:
        return user.headshot.storage.exists(user.headshot.name)
    except Exception as exc:
        raise _storage_failure(user, "check", exc) from exc
