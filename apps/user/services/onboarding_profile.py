"""Resumable first-login profile: section policy, saves, and finalization.

Onboarding asks for the profile in short sections. Each section posts on its
own, is validated by the same form declarations ``/profile`` uses
(``OnboardingProfileSectionForm``), and is saved as soon as it is valid, so an
agent who leaves part-way resumes from what the server holds. Nothing here sets
``User.profile_completed`` except ``finalize_profile``, which re-checks every
required fact against the current rules — the stored headshot included —
before it releases the gate.

Two tokens keep concurrent tabs honest without a new column:

* ``onboarding_version`` changes when an administrator resets onboarding, and
  every write refuses a page rendered for an older cycle;
* a section ``revision`` fingerprints that section's stored values, so a stale
  tab cannot silently overwrite what a newer tab saved. A resubmission that
  would change nothing is accepted as a no-op whatever its revision, which is
  what makes a double submit harmless.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.formats import date_format

from apps.user.forms import (
    SELF_PROFILE_FIELD_MAP,
    OnboardingProfileSectionForm,
    form_errors,
    profile_initial,
)
from apps.user.headshot import MAX_BYTES, MIN_DIM
from apps.user.models import Office, User, UserOnboardingCase
from apps.user.profile_fields import (
    BIO_MAX_LENGTH,
    LANGUAGE_NAMES,
    MAX_LANGUAGES,
    PREFERRED_CONTACT_CHOICES,
    SOCIAL_PLATFORM_BY_FIELD,
    contact_method_options,
    language_options,
    social_platform_options,
)
from apps.user.services.onboarding_office import (
    DEFAULT_OWNER_POLICY,
    OFFICE_CONFIRMATION_FIELD,
    OFFICE_HANDOFF_EVENT,
    DefaultOnboardingOwnerPolicy,
    office_confirmation_is_current,
    office_confirmation_payload,
    resolve_office_administrator,
)
from apps.user.services.profile import (
    PROFILE_AUDIT_FIELDS,
    PROFILE_FIELD_SPECS,
    FieldOwner,
    MicrosoftLegalName,
    OnboardingSection,
    ProfileFieldSpec,
    can_self_assign_office,
    headshot_is_stored,
    is_field_present,
    microsoft_legal_name,
)
from apps.user.us import US_STATE_CHOICES
from apps.web.contracts import empty_validation_errors

LEGAL_NAME_FIELDS = ("first_name", "last_name")
LICENSE_FIELDS = ("license_number", "license_state", "license_expires_on")
LIST_FIELDS = ("languages", "specialties")
REVIEW_CONFIRMATION_FIELD = "confirm_review"
ONBOARDING_OFFICE_REASON = "Office set during onboarding."

_STATE_NAMES = dict(US_STATE_CHOICES)
_CONTACT_METHOD_LABELS = dict(PREFERRED_CONTACT_CHOICES)


class ProfileSectionStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"


@dataclass(frozen=True)
class SectionDefinition:
    code: OnboardingSection
    label: str
    description: str


SECTION_DEFINITIONS: tuple[SectionDefinition, ...] = (
    SectionDefinition(
        OnboardingSection.IDENTITY,
        "Identity and photo",
        "Confirm who you are and add a professional headshot.",
    ),
    SectionDefinition(
        OnboardingSection.CONTACT,
        "Contact and home address",
        "How the brokerage reaches you, and where paperwork should go.",
    ),
    SectionDefinition(
        OnboardingSection.CREDENTIALS,
        "Professional credentials",
        "Your office, license, and memberships, plus an optional introduction.",
    ),
    SectionDefinition(
        OnboardingSection.REVIEW,
        "Review and confirm",
        "Check your details exactly as they will be saved.",
    ),
)

#: The sections that post values. Review only confirms.
EDITABLE_SECTIONS: tuple[OnboardingSection, ...] = (
    OnboardingSection.IDENTITY,
    OnboardingSection.CONTACT,
    OnboardingSection.CREDENTIALS,
)


class ProfileAlreadyFinalized(Exception):
    """The profile was completed, possibly by another tab, before this write."""


class StaleOnboardingVersion(Exception):
    message = (
        "Your onboarding was restarted since this page loaded. We reloaded the "
        "latest steps; please check this section and continue."
    )


class StaleProfileSection(Exception):
    message = (
        "This section was changed in another tab or window since you opened it. "
        "Check the details below; saving again will replace that change."
    )


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProfileFlowContext:
    """Per-user facts that shape the flow, resolved once per request."""

    user: User
    microsoft_name: MicrosoftLegalName | None
    office_editable: bool
    office_confirmed: bool

    @property
    def legal_name_locked(self) -> bool:
        return self.microsoft_name is not None and self.microsoft_name.complete

    def owner(self, spec: ProfileFieldSpec) -> FieldOwner:
        if spec.key in LEGAL_NAME_FIELDS and self.legal_name_locked:
            return FieldOwner.MICROSOFT
        return spec.owner

    def read_only(self, field_name: str) -> bool:
        if field_name in LEGAL_NAME_FIELDS:
            return self.legal_name_locked
        if field_name == "office":
            return not self.office_editable
        return False


def flow_context(user: User) -> ProfileFlowContext:
    case = getattr(user, "onboarding_case", None)
    return ProfileFlowContext(
        user=user,
        microsoft_name=microsoft_legal_name(user),
        # Onboarding has to be finishable: somebody with no office yet may pick
        # one even where the profile page treats an office as administrative.
        office_editable=(
            can_self_assign_office(user) or user.office_id is None  # ty: ignore[unresolved-attribute]
        ),
        office_confirmed=office_confirmation_is_current(user, case),
    )


def section_specs(section: OnboardingSection) -> tuple[ProfileFieldSpec, ...]:
    return tuple(
        spec for spec in PROFILE_FIELD_SPECS if spec.onboarding_section == section
    )


def _spec_fields(spec: ProfileFieldSpec) -> tuple[str, ...]:
    """Every name a spec contributes to payloads, including upload-only values."""
    return spec.field_names or (spec.key,)


def section_field_names(
    context: ProfileFlowContext, section: OnboardingSection
) -> tuple[str, ...]:
    """The form fields the user may write in this section."""
    return tuple(
        name
        for spec in section_specs(section)
        for name in spec.field_names
        if not context.read_only(name)
    )


def required_field_names(
    context: ProfileFlowContext, section: OnboardingSection
) -> tuple[str, ...]:
    return tuple(
        spec.key
        for spec in section_specs(section)
        if spec.form_fields is None
        and spec.is_required_for(context.user)
        and not context.read_only(spec.key)
    )


def missing_required(
    context: ProfileFlowContext,
    sections: tuple[OnboardingSection, ...] = EDITABLE_SECTIONS,
) -> list[ProfileFieldSpec]:
    return [
        spec
        for section in sections
        for spec in section_specs(section)
        if spec.is_required_for(context.user)
        and not is_field_present(context.user, spec.key)
    ]


def section_status(
    context: ProfileFlowContext, section: OnboardingSection
) -> ProfileSectionStatus:
    if (
        section == OnboardingSection.CREDENTIALS
        and not context.office_confirmed
        and getattr(context.user, "office_id", None)
    ):
        return ProfileSectionStatus.IN_PROGRESS
    if not missing_required(context, (section,)):
        return ProfileSectionStatus.COMPLETE
    if any(is_field_present(context.user, spec.key) for spec in section_specs(section)):
        return ProfileSectionStatus.IN_PROGRESS
    return ProfileSectionStatus.NOT_STARTED


def resolve_section(
    context: ProfileFlowContext, requested: str | None
) -> OnboardingSection:
    """The requested section when valid, else the first one still unfinished."""
    try:
        return OnboardingSection(requested or "")
    except ValueError:
        pass
    for section in EDITABLE_SECTIONS:
        if section_status(context, section) != ProfileSectionStatus.COMPLETE:
            return section
    return OnboardingSection.REVIEW


def next_section(section: OnboardingSection) -> OnboardingSection:
    order = [definition.code for definition in SECTION_DEFINITIONS]
    index = order.index(section)
    return order[min(index + 1, len(order) - 1)]


# ---------------------------------------------------------------------------
# Stored values
# ---------------------------------------------------------------------------


def _comparable(user: User, name: str) -> Any:
    if name == "office":
        return user.office_id  # ty: ignore[unresolved-attribute]
    if name == "headshot":
        return bool(user.headshot)
    value = getattr(user, name)
    if name == "license_expires_on":
        return value.isoformat() if value else ""
    if name in LIST_FIELDS:
        return list(value or [])
    return value or ""


def section_revision(user: User, section: OnboardingSection) -> str:
    names = sorted(name for spec in section_specs(section) for name in spec.field_names)
    payload = {
        "version": user.onboarding_version,
        "section": str(section),
        "values": {name: _comparable(user, name) for name in names},
    }
    encoded = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def stored_form_data(user: User, names: tuple[str, ...]) -> dict[str, Any]:
    """Stored values shaped like the POST that would have produced them."""
    data: dict[str, Any] = {}
    for name in names:
        value = _comparable(user, name)
        data[name] = "" if value is None else value
        if name == "office" and value is not None:
            data[name] = str(value)
    return data


def _apply_microsoft_name(user: User, name: MicrosoftLegalName | None) -> None:
    if name is None or not name.complete:
        return
    user.first_name = name.first_name
    user.last_name = name.last_name


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SectionSaveResult:
    changed: bool
    invalid_form: OnboardingProfileSectionForm | None = None
    errors: dict | None = None


def _lock_writable_user(user: User, expected_onboarding_version: int) -> User:
    locked = User.objects.select_for_update().get(pk=user.pk)
    if locked.profile_completed:
        raise ProfileAlreadyFinalized
    if expected_onboarding_version != locked.onboarding_version:
        raise StaleOnboardingVersion
    return locked


def save_profile_section(
    *,
    user: User,
    section: OnboardingSection,
    data: Mapping[str, Any],
    expected_revision: str,
    expected_onboarding_version: int,
    office_confirmed: bool = False,
    confirmed_office_id: int | None = None,
) -> SectionSaveResult:
    """Validate and persist one section without completing the profile."""
    from apps.audit.events import publish
    from apps.audit.service import actor_from_user, log_model_change
    from apps.user.services.agent_administration import reset_license_verification
    from apps.user.services.hierarchy import sync_primary_membership
    from apps.user.services.role_assignments import sync_default_agent_assignment

    if section not in EDITABLE_SECTIONS:
        raise ValueError(f"{section} does not accept profile values.")

    with transaction.atomic():
        locked = _lock_writable_user(user, expected_onboarding_version)
        context = flow_context(locked)
        current_revision = section_revision(locked, section)
        before = copy.copy(locked)
        form = OnboardingProfileSectionForm(
            data,
            instance=locked,
            field_names=section_field_names(context, section),
            required_fields=required_field_names(context, section),
            can_change_office=context.office_editable,
        )
        if not form.is_valid():
            return SectionSaveResult(changed=False, invalid_form=form)
        case = (
            UserOnboardingCase.objects.select_for_update(of=("self",))
            .filter(user=locked)
            .first()
        )
        selected_office = (
            form.cleaned_data.get("office", locked.office)
            if section == OnboardingSection.CREDENTIALS
            else locked.office
        )
        confirmation_changed = False
        if section == OnboardingSection.CREDENTIALS:
            confirmation_is_current = bool(
                case
                and case.office_confirmed_at
                and getattr(case, "office_confirmed_for_id", None)
                == getattr(selected_office, "pk", None)
                and case.office_confirmation_version == locked.onboarding_version
            )
            posted_confirmation_is_valid = bool(
                office_confirmed
                and selected_office is not None
                and confirmed_office_id == selected_office.pk
            )
            if not confirmation_is_current and not posted_confirmation_is_valid:
                return SectionSaveResult(
                    changed=False,
                    errors={
                        "fields": {
                            OFFICE_CONFIRMATION_FIELD: [
                                "Review and confirm this office before continuing."
                            ]
                        },
                        "form": [],
                    },
                )
            confirmation_changed = not confirmation_is_current
        if section == OnboardingSection.IDENTITY:
            _apply_microsoft_name(locked, context.microsoft_name)

        compared = [
            name for spec in section_specs(section) for name in spec.field_names
        ]
        if not confirmation_changed and all(
            _comparable(before, name) == _comparable(locked, name) for name in compared
        ):
            return SectionSaveResult(changed=False)
        if expected_revision != current_revision:
            raise StaleProfileSection

        saved = form.save()
        if before.office_id != saved.office_id:  # ty: ignore[unresolved-attribute]
            sync_primary_membership(
                saved, actor=saved, business_reason=ONBOARDING_OFFICE_REASON
            )
            sync_default_agent_assignment(
                saved, actor=saved, business_reason=ONBOARDING_OFFICE_REASON
            )
            publish(
                "user.onboarding.office_changed",
                actor_id=str(saved.pk),
                subject=f"user:{saved.pk}",
                payload={"user_id": saved.pk},
            )
        if section == OnboardingSection.CREDENTIALS and confirmation_changed:
            now = timezone.now()
            if case is None:
                case = UserOnboardingCase(user=saved)
            case.office_confirmed_at = now
            case.office_confirmed_for = saved.office
            case.office_confirmation_version = saved.onboarding_version
            case.required_setup_completed_at = None
            case.updated_by = saved
            case.save()
        if any(
            _comparable(before, name) != _comparable(saved, name)
            for name in LICENSE_FIELDS
        ):
            reset_license_verification(saved, reason="license_edited_by_agent")
        log_model_change(
            "user.onboarding.profile_section_saved",
            actor=actor_from_user(saved),
            instance=saved,
            before_instance=before,
            snapshot_fields=[name for name in PROFILE_AUDIT_FIELDS if name in compared],
            metadata={
                "section": str(section),
                "onboarding_version": saved.onboarding_version,
            },
        )
        publish(
            "user.onboarding.profile_changed",
            actor_id=str(saved.pk),
            subject=f"user:{saved.pk}",
            payload={"user_id": saved.pk},
        )
    return SectionSaveResult(changed=True)


@dataclass(frozen=True)
class FinalizeResult:
    completed: bool
    errors: dict | None = None


def _missing_message(spec: ProfileFieldSpec) -> str:
    if spec.key == "headshot":
        return "Add a professional headshot before you finish."
    if spec.key == "office":
        return "Choose the office you work from."
    return f"{spec.label} is required."


def _finalize_errors(
    context: ProfileFlowContext,
    *,
    confirmed: bool,
    case: UserOnboardingCase | None,
) -> dict | None:
    user = context.user
    names = tuple(
        name
        for section in EDITABLE_SECTIONS
        for name in section_field_names(context, section)
    )
    required = tuple(
        name
        for section in EDITABLE_SECTIONS
        for name in required_field_names(context, section)
    )
    # Re-run today's rules over what is stored: an office retired, or a field
    # made required, since a section was saved must stop the finish here.
    form = OnboardingProfileSectionForm(
        stored_form_data(user, names),
        instance=user,
        field_names=names,
        required_fields=required,
        can_change_office=context.office_editable,
    )
    errors = empty_validation_errors() if form.is_valid() else form_errors(form)
    fields: dict[str, list[str]] = errors["fields"]
    for spec in missing_required(context):
        if not fields.get(spec.key):
            fields[spec.key] = [_missing_message(spec)]
    if user.headshot and not headshot_is_stored(user):
        fields["headshot"] = [
            "We could not find your uploaded photo. Upload it again to finish."
        ]
    if not (
        case
        and case.office_confirmed_at
        and getattr(case, "office_confirmed_for_id", None)
        == getattr(user, "office_id", None)
        and case.office_confirmation_version == user.onboarding_version
    ):
        fields[OFFICE_CONFIRMATION_FIELD] = [
            "Review and confirm your selected office before you finish."
        ]
    if not confirmed:
        fields[REVIEW_CONFIRMATION_FIELD] = [
            "Confirm that these details are correct before you finish."
        ]
    return errors if fields or errors["form"] else None


def finalize_profile(
    *, user: User, confirmed: bool, expected_onboarding_version: int
) -> FinalizeResult:
    """Complete the profile atomically, exactly once.

    Raises ``HeadshotStorageUnavailable`` when storage cannot confirm the
    photo, and ``StaleOnboardingVersion`` for a page from an earlier cycle.
    """
    from apps.audit.events import publish
    from apps.audit.service import (
        AuditTarget,
        actor_from_user,
        log_event,
        log_model_change,
    )
    from apps.user.services.hierarchy import sync_primary_membership
    from apps.user.services.onboarding_operations import complete_required_setup
    from apps.user.services.role_assignments import sync_default_agent_assignment

    with transaction.atomic():
        try:
            locked = _lock_writable_user(user, expected_onboarding_version)
        except ProfileAlreadyFinalized:
            return FinalizeResult(completed=False)
        context = flow_context(locked)
        before = copy.copy(locked)
        case = (
            UserOnboardingCase.objects.select_for_update(of=("self",))
            .filter(user=locked)
            .first()
        )
        errors = _finalize_errors(context, confirmed=confirmed, case=case)
        if errors is not None:
            return FinalizeResult(completed=False, errors=errors)

        _apply_microsoft_name(locked, context.microsoft_name)
        locked.display_name = locked.get_full_name().strip()
        locked.profile_completed = True
        locked.profile_completed_at = timezone.now()
        locked.save(
            update_fields=[
                "first_name",
                "last_name",
                "display_name",
                "profile_completed",
                "profile_completed_at",
            ]
        )
        sync_primary_membership(
            locked, actor=locked, business_reason=ONBOARDING_OFFICE_REASON
        )
        sync_default_agent_assignment(
            locked, actor=locked, business_reason=ONBOARDING_OFFICE_REASON
        )
        assert case is not None
        assert locked.office is not None
        resolved_admin = resolve_office_administrator(locked.office)
        case.office_handoff_office = locked.office
        case.office_handoff_onboarding_version = locked.onboarding_version
        case.office_handoff_updated_at = timezone.now()
        if resolved_admin is None:
            case.office_handoff_state = (
                UserOnboardingCase.OfficeHandoffState.NOTIFICATION_FAILED
            )
        else:
            case.office_handoff_state = UserOnboardingCase.OfficeHandoffState.PENDING
            if (
                case.owner is None
                and DEFAULT_OWNER_POLICY
                == DefaultOnboardingOwnerPolicy.RESOLVED_OFFICE_ADMIN
            ):
                case.owner = resolved_admin.user
        case.updated_by = locked
        case.save()
        log_event(
            (
                "user.onboarding.office_handoff_requested"
                if resolved_admin is not None
                else "user.onboarding.office_handoff_unavailable"
            ),
            actor=actor_from_user(locked),
            target=AuditTarget(
                target_type=UserOnboardingCase._meta.label_lower,
                target_id=str(locked.pk),
                target_label=f"User {locked.pk}",
            ),
            after={
                "state": case.office_handoff_state,
                "office_id": getattr(locked, "office_id", None),
                "onboarding_version": locked.onboarding_version,
                "recipient_id": resolved_admin.user.pk if resolved_admin else None,
            },
            office_id=locked.office.stable_key,
            channel="onboarding",
        )
        complete_required_setup(user=locked)
        log_model_change(
            "user.onboarding.completed",
            actor=actor_from_user(locked),
            instance=locked,
            before_instance=before,
            snapshot_fields=[
                "first_name",
                "last_name",
                "display_name",
                "state",
                "office",
                "profile_completed",
                "profile_completed_at",
                "onboarding_version",
            ],
            metadata={"review_confirmed": True},
        )
        # Persisted in this transaction and dispatched on commit, so a rollback
        # leaves no event and the row lock above keeps it to one per cycle.
        publish(
            "user.onboarded",
            version=2,
            actor_id=str(locked.pk),
            subject=f"user:{locked.pk}",
            payload={
                "user_id": locked.pk,
                "office_id": locked.office_id,  # ty: ignore[unresolved-attribute]
            },
        )
        if resolved_admin is not None:
            publish(
                OFFICE_HANDOFF_EVENT,
                actor_id=str(locked.pk),
                subject=f"user:{locked.pk}",
                payload={
                    "user_id": locked.pk,
                    "office_id": getattr(locked, "office_id", None),
                    "recipient_id": resolved_admin.user.pk,
                    "onboarding_version": locked.onboarding_version,
                },
            )
    return FinalizeResult(completed=True)


# ---------------------------------------------------------------------------
# Page payload
# ---------------------------------------------------------------------------


def _field_label(spec: ProfileFieldSpec, name: str) -> str:
    platform = SOCIAL_PLATFORM_BY_FIELD.get(name)
    return platform.label if platform is not None else spec.label


def _display_value(context: ProfileFlowContext, name: str) -> str:
    """The stored value as the review step shows it: normalized, never guessed."""
    user = context.user
    if name in LEGAL_NAME_FIELDS and context.legal_name_locked:
        return getattr(context.microsoft_name, name)
    if name == "headshot":
        return "Photo on file" if user.headshot else ""
    if name == "office":
        return user.office.path_label() if user.office else ""
    if name in ("state", "license_state"):
        return _STATE_NAMES.get(getattr(user, name), "")
    if name == "license_expires_on":
        value = user.license_expires_on
        return date_format(value, "F j, Y") if value else ""
    if name == "preferred_contact_method":
        return _CONTACT_METHOD_LABELS.get(user.preferred_contact_method, "")
    if name == "languages":
        return ", ".join(
            LANGUAGE_NAMES[code]
            for code in user.languages or []
            if code in LANGUAGE_NAMES
        )
    return str(getattr(user, name) or "")


def _field_policy_payload(context: ProfileFlowContext) -> dict[str, dict]:
    payload: dict[str, dict] = {}
    for spec in PROFILE_FIELD_SPECS:
        if spec.onboarding_section is None:
            continue
        multi = len(_spec_fields(spec)) > 1
        for name in _spec_fields(spec):
            payload[name] = {
                "label": _field_label(spec, name),
                "section": str(spec.onboarding_section),
                "required": spec.is_required_for(context.user) and not multi,
                "owner": str(context.owner(spec)),
                "readOnly": context.read_only(name),
                "guidance": "" if multi else spec.guidance,
            }
    return payload


def _review_payload(context: ProfileFlowContext) -> dict:
    groups = []
    for definition in SECTION_DEFINITIONS:
        if definition.code not in EDITABLE_SECTIONS:
            continue
        rows = []
        for spec in section_specs(definition.code):
            multi = len(_spec_fields(spec)) > 1
            for name in _spec_fields(spec):
                rows.append(
                    {
                        "field": name,
                        "label": _field_label(spec, name),
                        "display": _display_value(context, name),
                        "required": spec.is_required_for(context.user) and not multi,
                        "owner": str(context.owner(spec)),
                    }
                )
        groups.append(
            {"section": str(definition.code), "label": definition.label, "rows": rows}
        )
    missing = [
        {
            "field": spec.key,
            "label": spec.label,
            "section": str(spec.onboarding_section),
        }
        for spec in missing_required(context)
    ]
    if not context.office_confirmed:
        missing.append(
            {
                "field": OFFICE_CONFIRMATION_FIELD,
                "label": "Office confirmation",
                "section": str(OnboardingSection.CREDENTIALS),
            }
        )
    return {"ready": not missing, "missing": missing, "groups": groups}


def _legal_name_notice(context: ProfileFlowContext) -> str | None:
    name = context.microsoft_name
    user = context.user
    if name is None:
        return None
    if not name.complete:
        return (
            "Microsoft did not send your full name. Enter it exactly as it "
            "appears on your license."
        )
    if (user.first_name, user.last_name) != (name.first_name, name.last_name):
        return (
            "Your name on file differed from your Microsoft account, so the "
            "Microsoft name will be saved."
        )
    return None


def _posted_list(posted: Mapping[str, Any], name: str) -> list[str]:
    getlist = getattr(posted, "getlist", None)
    if callable(getlist):
        return [str(value) for value in getlist(name)]
    raw = posted.get(name, [])
    if isinstance(raw, (list, tuple)):
        return [str(value) for value in raw]
    return [str(raw)] if raw else []


def onboarding_profile_page_props(
    user: User,
    *,
    request,
    section: OnboardingSection,
    context: ProfileFlowContext | None = None,
    errors: dict | None = None,
    posted: Mapping[str, Any] | None = None,
) -> dict:
    """Props for the onboarding profile flow.

    ``posted`` re-applies what was submitted for ``section`` after a 422, so a
    validation failure never wipes the fields the agent just typed, while
    every other section keeps showing what the server holds.
    """
    context = context or flow_context(user)
    saved = profile_initial(
        user,
        None,
        request=request,
        field_map=SELF_PROFILE_FIELD_MAP,
        include_languages=True,
        include_specialties=True,
    )
    initial = dict(saved)
    if posted is not None and section in EDITABLE_SECTIONS:
        writable = set(section_field_names(context, section))
        for prop, name in SELF_PROFILE_FIELD_MAP:
            if name in writable:
                initial[prop] = posted.get(name, "")
        if "languages" in writable:
            initial["languages"] = _posted_list(posted, "languages")

    legal_first, legal_last = user.first_name, user.last_name
    if context.legal_name_locked and context.microsoft_name is not None:
        legal_first = context.microsoft_name.first_name
        legal_last = context.microsoft_name.last_name

    selected_office = None
    offices = []
    if context.office_editable:
        office_rows = list(Office.assignable_queryset())
        try:
            preview_office_id = int(initial.get("officeId") or 0)
        except (TypeError, ValueError):
            preview_office_id = 0
        groups: dict[str, list[dict]] = {}
        group_order: list[str] = []
        for office in office_rows:
            if office.pk == preview_office_id:
                selected_office = office
            group = office.region_name()
            if group not in groups:
                groups[group] = []
                group_order.append(group)
            groups[group].append(
                {
                    "id": office.pk,
                    "name": office.name,
                    "city": office.city,
                    "state": office.state,
                    "region": office.region_name(),
                }
            )
        offices = [{"label": label, "offices": groups[label]} for label in group_order]
    elif getattr(user, "office_id", None):
        selected_office = user.office
    case = getattr(user, "onboarding_case", None)
    office_is_confirmed = bool(
        context.office_confirmed
        and case
        and case.office_confirmed_for_id == getattr(selected_office, "pk", None)
    )

    return {
        "profileFlow": {
            "onboardingVersion": user.onboarding_version,
            "currentSection": str(section),
            "sections": [
                {
                    "code": str(definition.code),
                    "label": definition.label,
                    "description": definition.description,
                    "status": (
                        str(section_status(context, definition.code))
                        if definition.code in EDITABLE_SECTIONS
                        else None
                    ),
                    "revision": (
                        section_revision(user, definition.code)
                        if definition.code in EDITABLE_SECTIONS
                        else None
                    ),
                }
                for definition in SECTION_DEFINITIONS
            ],
            "fields": _field_policy_payload(context),
            "review": _review_payload(context),
        },
        "identity": {
            "email": user.email,
            "emailOwner": str(FieldOwner.MICROSOFT),
            "legalName": {"firstName": legal_first, "lastName": legal_last},
            "legalNameLocked": context.legal_name_locked,
            "legalNameNotice": _legal_name_notice(context),
        },
        "initial": initial,
        "saved": saved,
        "validation": errors or empty_validation_errors(),
        "offices": offices,
        "officeLabel": user.office.path_label() if user.office else "",
        "officeSelection": (
            office_confirmation_payload(selected_office) if selected_office else None
        ),
        "officeConfirmed": office_is_confirmed,
        "states": [{"code": code, "name": name} for code, name in US_STATE_CHOICES],
        "languageOptions": language_options(),
        "contactMethods": contact_method_options(),
        "socialPlatforms": social_platform_options(),
        "limits": {
            "headshotMaxBytes": MAX_BYTES,
            "headshotMinDimension": MIN_DIM,
            "bioMaxLength": BIO_MAX_LENGTH,
            "maxLanguages": MAX_LANGUAGES,
        },
    }
