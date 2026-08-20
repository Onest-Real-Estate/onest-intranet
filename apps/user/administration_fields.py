"""Broker-controlled agent administration vocabulary and normalizers.

The mirror image of :mod:`apps.user.profile_fields`: everything an agent may
*not* maintain about themselves. The closed sets live here so the model, the
administration form, and the read-only view an agent sees on their own profile
all describe the same value in the same words.
"""

from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

# ---------------------------------------------------------------------------
# Agent status
# ---------------------------------------------------------------------------

PROSPECTIVE = "prospective"
ACTIVE = "active"
ON_LEAVE = "on_leave"
SUSPENDED = "suspended"
DEPARTED = "departed"

AGENT_STATUS_CHOICES: tuple[tuple[str, str], ...] = (
    (PROSPECTIVE, "Prospective"),
    (ACTIVE, "Active"),
    (ON_LEAVE, "On leave"),
    (SUSPENDED, "Suspended"),
    (DEPARTED, "Departed"),
)

AGENT_STATUS_VALUES = {value for value, _label in AGENT_STATUS_CHOICES}
AGENT_STATUS_LABELS: dict[str, str] = dict(AGENT_STATUS_CHOICES)

# Statuses that describe someone still working here. Stripping the last live
# role assignment from one of these leaves a working agent with no access at
# all, so the service refuses it — see ``services.agent_administration``.
ENGAGED_AGENT_STATUSES = frozenset({PROSPECTIVE, ACTIVE, ON_LEAVE})

AGENT_STATUS_TONES: dict[str, str] = {
    PROSPECTIVE: "info",
    ACTIVE: "success",
    ON_LEAVE: "warning",
    SUSPENDED: "destructive",
    DEPARTED: "neutral",
}

# ---------------------------------------------------------------------------
# License verification
# ---------------------------------------------------------------------------

UNVERIFIED = "unverified"
PENDING = "pending"
VERIFIED = "verified"
REJECTED = "rejected"

LICENSE_VERIFICATION_CHOICES: tuple[tuple[str, str], ...] = (
    (UNVERIFIED, "Not verified"),
    (PENDING, "Verification pending"),
    (VERIFIED, "Verified"),
    (REJECTED, "Rejected"),
)

LICENSE_VERIFICATION_VALUES = {value for value, _label in LICENSE_VERIFICATION_CHOICES}
LICENSE_VERIFICATION_LABELS: dict[str, str] = dict(LICENSE_VERIFICATION_CHOICES)

LICENSE_VERIFICATION_TONES: dict[str, str] = {
    UNVERIFIED: "neutral",
    PENDING: "warning",
    VERIFIED: "success",
    REJECTED: "destructive",
}

# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------

AGENT_IDENTIFIER_MAX_LENGTH = 32
INTERNAL_NOTES_MAX_LENGTH = 4000
VERIFICATION_NOTE_MAX_LENGTH = 500

_MULTISPACE_RE = re.compile(r"\s+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_IDENTIFIER_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]*$")


# ---------------------------------------------------------------------------
# Normalizers
# ---------------------------------------------------------------------------


def normalize_agent_identifier(value: str) -> str:
    """Uppercase, whitespace-free internal identifier. Blank stays blank.

    A closed character set keeps the value safe to render, export, and match
    on: an identifier that may contain anything is an identifier no report can
    join against.
    """
    raw = _MULTISPACE_RE.sub("", (value or "").strip()).upper()
    if not raw:
        return ""
    if len(raw) > AGENT_IDENTIFIER_MAX_LENGTH:
        raise ValidationError(
            _("Agent IDs must be %(max)d characters or fewer.")
            % {"max": AGENT_IDENTIFIER_MAX_LENGTH},
            code="max_length",
        )
    if not _IDENTIFIER_RE.match(raw):
        raise ValidationError(
            _("Use letters, digits, dots, dashes, and underscores only."),
            code="invalid",
        )
    return raw


def normalize_internal_notes(value: str) -> str:
    """Trim, normalize line endings, and cap runs of blank lines."""
    raw = (value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        return ""
    raw = _BLANK_LINES_RE.sub("\n\n", raw)
    if len(raw) > INTERNAL_NOTES_MAX_LENGTH:
        raise ValidationError(
            _("Keep operational notes under %(max)d characters. These are %(count)d.")
            % {"max": INTERNAL_NOTES_MAX_LENGTH, "count": len(raw)},
            code="max_length",
        )
    return raw


def normalize_agent_status(value: str) -> str:
    raw = (value or "").strip().lower()
    if raw not in AGENT_STATUS_VALUES:
        raise ValidationError(_("Choose a supported agent status."), code="invalid")
    return raw


def normalize_license_verification_state(value: str) -> str:
    raw = (value or "").strip().lower()
    if raw not in LICENSE_VERIFICATION_VALUES:
        raise ValidationError(
            _("Choose a supported verification state."), code="invalid"
        )
    return raw


# ---------------------------------------------------------------------------
# Option payloads
# ---------------------------------------------------------------------------


def agent_status_options() -> list[dict[str, str]]:
    return [
        {"value": value, "label": label, "tone": AGENT_STATUS_TONES[value]}
        for value, label in AGENT_STATUS_CHOICES
    ]


def license_verification_options() -> list[dict[str, str]]:
    return [
        {"value": value, "label": label, "tone": LICENSE_VERIFICATION_TONES[value]}
        for value, label in LICENSE_VERIFICATION_CHOICES
    ]
