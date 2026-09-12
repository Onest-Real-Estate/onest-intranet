"""Governed training taxonomy: content types, categories, and tool codes."""

from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

CONTENT_TYPE_ARTICLE = "article"
CONTENT_TYPE_GUIDE = "guide"
CONTENT_TYPE_VIDEO = "video"
CONTENT_TYPE_CHECKLIST = "checklist"
CONTENT_TYPE_COURSE = "course"
CONTENT_TYPE_QUIZ = "quiz"
CONTENT_TYPE_LIVE_SESSION = "live_session"
CONTENT_TYPE_RECORDING = "recording"
CONTENT_TYPE_TOOL_ONBOARDING = "tool_onboarding"

INTERACTIVE_CONTENT_TYPES = frozenset(
    {CONTENT_TYPE_QUIZ, CONTENT_TYPE_LIVE_SESSION, CONTENT_TYPE_COURSE}
)

CONTENT_TYPE_CHOICES = (
    (CONTENT_TYPE_ARTICLE, _("Article")),
    (CONTENT_TYPE_GUIDE, _("Guide")),
    (CONTENT_TYPE_VIDEO, _("Video")),
    (CONTENT_TYPE_CHECKLIST, _("Checklist")),
    (CONTENT_TYPE_COURSE, _("Course")),
    (CONTENT_TYPE_QUIZ, _("Quiz")),
    (CONTENT_TYPE_LIVE_SESSION, _("Live session")),
    (CONTENT_TYPE_RECORDING, _("Recording")),
    (CONTENT_TYPE_TOOL_ONBOARDING, _("Tool onboarding")),
)

CONTENT_TYPE_CODES = frozenset(code for code, _ in CONTENT_TYPE_CHOICES)

COMPLETION_NOT_STARTED = "not_started"
COMPLETION_IN_PROGRESS = "in_progress"
COMPLETION_COMPLETED = "completed"

COMPLETION_CHOICES = (
    (COMPLETION_NOT_STARTED, _("Not started")),
    (COMPLETION_IN_PROGRESS, _("In progress")),
    (COMPLETION_COMPLETED, _("Completed")),
)

COMPLETION_FILTER_CODES = frozenset(code for code, _ in COMPLETION_CHOICES)

VERSION_POLICY_CURRENT = "current_version"
VERSION_POLICY_ANY = "any_version"

VERSION_COMPLETION_POLICY_CHOICES = (
    (VERSION_POLICY_CURRENT, _("Current live version")),
    (VERSION_POLICY_ANY, _("Any completed version")),
)

VERSION_COMPLETION_POLICY_CODES = frozenset(
    code for code, _ in VERSION_COMPLETION_POLICY_CHOICES
)

PROGRESS_SOURCE_LEARNER = "learner"
PROGRESS_SOURCE_QUIZ = "quiz"
PROGRESS_SOURCE_SESSION = "session"
PROGRESS_SOURCE_COURSE_ROLLUP = "course_rollup"
PROGRESS_SOURCE_ADMIN = "admin_correction"
PROGRESS_SOURCE_SYSTEM = "system"

PROGRESS_SOURCE_CHOICES = (
    (PROGRESS_SOURCE_LEARNER, _("Learner")),
    (PROGRESS_SOURCE_QUIZ, _("Quiz")),
    (PROGRESS_SOURCE_SESSION, _("Live session")),
    (PROGRESS_SOURCE_COURSE_ROLLUP, _("Course rollup")),
    (PROGRESS_SOURCE_ADMIN, _("Admin correction")),
    (PROGRESS_SOURCE_SYSTEM, _("System")),
)

PROGRESS_SOURCE_CODES = frozenset(code for code, _ in PROGRESS_SOURCE_CHOICES)

QUIZ_FEEDBACK_NONE = "none"
QUIZ_FEEDBACK_SCORE_ONLY = "score_only"
QUIZ_FEEDBACK_REVIEW = "review"

QUIZ_FEEDBACK_POLICY_CHOICES = (
    (QUIZ_FEEDBACK_NONE, _("No feedback")),
    (QUIZ_FEEDBACK_SCORE_ONLY, _("Score only")),
    (QUIZ_FEEDBACK_REVIEW, _("Score and review")),
)

QUIZ_FEEDBACK_POLICY_CODES = frozenset(code for code, _ in QUIZ_FEEDBACK_POLICY_CHOICES)

SESSION_REGISTERED = "registered"
SESSION_CANCELLED = "cancelled"
SESSION_ATTENDED = "attended"
SESSION_NO_SHOW = "no_show"

SESSION_REGISTRATION_STATUS_CHOICES = (
    (SESSION_REGISTERED, _("Registered")),
    (SESSION_CANCELLED, _("Cancelled")),
    (SESSION_ATTENDED, _("Attended")),
    (SESSION_NO_SHOW, _("No show")),
)

SESSION_REGISTRATION_STATUS_CODES = frozenset(
    code for code, _ in SESSION_REGISTRATION_STATUS_CHOICES
)

CERTIFICATE_PENDING = "pending"
CERTIFICATE_APPROVED = "approved"
CERTIFICATE_REVOKED = "revoked"

CERTIFICATE_STATUS_CHOICES = (
    (CERTIFICATE_PENDING, _("Pending")),
    (CERTIFICATE_APPROVED, _("Approved")),
    (CERTIFICATE_REVOKED, _("Revoked")),
)

CERTIFICATE_STATUS_CODES = frozenset(code for code, _ in CERTIFICATE_STATUS_CHOICES)

#: Codes from the retired four-value tool enum. Published content still carries
#: them, so they stay valid forever; anything new is checked against the live
#: catalog instead, which is data rather than a deploy.
LEGACY_TOOL_CODES = frozenset(
    {"lofty", "skyslope", "microsoft365", "dotloop"},
)

TOOL_CODES = LEGACY_TOOL_CODES


def is_known_tool_code(code: str) -> bool:
    """Whether content may be tagged with this tool code."""
    if code in LEGACY_TOOL_CODES:
        return True

    from apps.onboarding_tools.models import OnboardingTool

    return OnboardingTool.objects.filter(slug=code, is_active=True).exists()


LIBRARY_VIEW_ALL = "all"
LIBRARY_VIEW_REQUIRED = "required"
LIBRARY_VIEW_RECOMMENDED = "recommended"

LIBRARY_VIEW_CODES = frozenset(
    {LIBRARY_VIEW_ALL, LIBRARY_VIEW_REQUIRED, LIBRARY_VIEW_RECOMMENDED}
)


@dataclass(frozen=True)
class CategorySeed:
    code: str
    label: str
    description: str
    display_order: int


CATEGORY_SEED: tuple[CategorySeed, ...] = (
    CategorySeed("ethics", "Ethics", "Ethics and professional conduct.", 10),
    CategorySeed(
        "fair_housing",
        "Fair housing",
        "Fair housing compliance and best practices.",
        20,
    ),
    CategorySeed(
        "onboarding",
        "Onboarding",
        "New agent orientation and brokerage basics.",
        30,
    ),
    CategorySeed(
        "tools",
        "Tools & systems",
        "Third-party tool onboarding and how-tos.",
        40,
    ),
    CategorySeed(
        "compliance",
        "Compliance",
        "License renewal and regulatory requirements.",
        50,
    ),
    CategorySeed(
        "skills",
        "Skills",
        "Sales, negotiation, and client service skills.",
        60,
    ),
    CategorySeed("general", "General", "General training resources.", 100),
)

SYSTEM_CATEGORY_CODES = frozenset(item.code for item in CATEGORY_SEED)


def require_content_type(code: str) -> str:
    normalized = (code or "").strip()
    if normalized not in CONTENT_TYPE_CODES:
        raise ValidationError(_("Unknown training content type."))
    return normalized
