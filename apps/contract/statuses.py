"""Stable Agent Contract lifecycle codes and presentation metadata.

Allowed transitions, side effects, locking, and idempotency live in
``apps.contract.lifecycle``. This module owns the vocabulary every surface
must share so a directory filter, an admin badge, and the transition service
never disagree about what ``active`` means.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class ContractStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    READY_FOR_REVIEW = "ready_for_review", _("Ready for review")
    SENT = "sent", _("Sent to agent")
    VIEWED = "viewed", _("Viewed")
    SIGNED = "signed", _("Signed")
    ACTIVE = "active", _("Active")
    SUPERSEDED = "superseded", _("Superseded")
    EXPIRED = "expired", _("Expired")
    TERMINATED = "terminated", _("Terminated")
    GENERATION_ERROR = "generation_error", _("Generation error")


#: Statuses that still describe a live agreement governing the agent.
GOVERNING_STATUSES = frozenset({ContractStatus.ACTIVE})

#: In-flight statuses before a contract becomes governing or terminal.
PIPELINE_STATUSES = frozenset(
    {
        ContractStatus.DRAFT,
        ContractStatus.READY_FOR_REVIEW,
        ContractStatus.SENT,
        ContractStatus.VIEWED,
        ContractStatus.SIGNED,
        ContractStatus.GENERATION_ERROR,
    }
)

#: Terminal statuses: history only; no further signing or activation.
TERMINAL_STATUSES = frozenset(
    {
        ContractStatus.SUPERSEDED,
        ContractStatus.EXPIRED,
        ContractStatus.TERMINATED,
    }
)

#: Tone keys consumed by directory/admin badges (semantic, not hex).
STATUS_TONES: dict[str, str] = {
    ContractStatus.DRAFT: "neutral",
    ContractStatus.READY_FOR_REVIEW: "warning",
    ContractStatus.SENT: "info",
    ContractStatus.VIEWED: "info",
    ContractStatus.SIGNED: "info",
    ContractStatus.ACTIVE: "success",
    ContractStatus.SUPERSEDED: "neutral",
    ContractStatus.EXPIRED: "warning",
    ContractStatus.TERMINATED: "danger",
    ContractStatus.GENERATION_ERROR: "danger",
}


#: Tone keys for the template family lifecycle (``ContractTemplate.Status``).
TEMPLATE_STATUS_TONES: dict[str, str] = {
    "draft": "neutral",
    "active": "success",
    "retired": "neutral",
}

#: Tone keys for one version of a template (``ContractTemplateVersion.Status``).
TEMPLATE_VERSION_STATUS_TONES: dict[str, str] = {
    "draft": "neutral",
    "published": "info",
    "superseded": "neutral",
    "retired": "warning",
}


def _labelled(choices, code: str) -> str:
    for value, label in choices:
        if value == code:
            return str(label)
    return code


def template_status_label(code: str) -> str:
    from apps.contract.models import ContractTemplate

    return _labelled(ContractTemplate.Status.choices, code)


def template_status_tone(code: str) -> str:
    return TEMPLATE_STATUS_TONES.get(code, "neutral")


def template_version_status_label(code: str) -> str:
    from apps.contract.models import ContractTemplateVersion

    return _labelled(ContractTemplateVersion.Status.choices, code)


def template_version_status_tone(code: str) -> str:
    return TEMPLATE_VERSION_STATUS_TONES.get(code, "neutral")


def status_label(code: str) -> str:
    try:
        return ContractStatus(code).label
    except ValueError:
        return code


def status_tone(code: str) -> str:
    return STATUS_TONES.get(code, "neutral")


def contract_status_options() -> list[dict[str, str]]:
    """Filter choices for the people directory and contract consoles."""
    return [
        {"value": value, "label": str(label), "tone": status_tone(value)}
        for value, label in ContractStatus.choices
    ]
