"""Onboarding props the dashboard carries for Agent journey users.

While required setup is incomplete the dashboard is a shell: it carries the
greeting, the journey, and the profile flow that the setup dialog renders, and
never registers a widget provider. After release it carries the activation
center's open policy instead. See ``docs/onboarding-operations.md``.
"""

from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from django.http import HttpRequest

from apps.user.models import User
from apps.user.services.onboarding_office import office_confirmation_payload
from apps.user.services.onboarding_profile import (
    ProfileFlowContext,
    flow_context,
    onboarding_profile_page_props,
    resolve_section,
)
from apps.user.services.onboarding_state import AgentOnboardingJourney
from apps.user.services.profile import OnboardingSection

ONBOARDING_DIALOG_PARAM = "onboarding"
SECTION_PARAM = "section"
# Remembers, per login session, the onboarding cycle whose activation center
# already opened on its own. A new login or an administrative reset prompts
# once more; ordinary navigation never does.
ACTIVATION_PROMPT_SESSION_KEY = "onboarding_activation_prompted_version"


class OnboardingDialogRequest(StrEnum):
    """Values a link may pass as ``?onboarding=`` to ask for the dialog."""

    OPEN = "open"


def dialog_requested(request: HttpRequest) -> bool:
    return request.GET.get(ONBOARDING_DIALOG_PARAM) == OnboardingDialogRequest.OPEN


def setup_dialog_props(
    request: HttpRequest,
    user: User,
    *,
    section: OnboardingSection | None = None,
    context: ProfileFlowContext | None = None,
    errors: dict | None = None,
    posted: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The profile flow for the strict setup dialog, at the resumed section."""
    context = context or flow_context(user)
    if section is None:
        section = resolve_section(context, request.GET.get(SECTION_PARAM))
    return onboarding_profile_page_props(
        user,
        request=request,
        section=section,
        context=context,
        errors=errors,
        posted=posted,
    )


def activation_center_props(
    request: HttpRequest, user: User, journey: AgentOnboardingJourney
) -> dict[str, Any]:
    """Whether the released activation center opens, and the office it names.

    Callers pass this as a lazy prop so a partial reload that does not ask for
    it never spends the once-per-login prompt.
    """
    requested = dialog_requested(request)
    first_prompt = (
        not journey.activation_complete
        and request.session.get(ACTIVATION_PROMPT_SESSION_KEY)
        != user.onboarding_version
    )
    if requested or first_prompt:
        request.session[ACTIVATION_PROMPT_SESSION_KEY] = user.onboarding_version
    office = None
    if requested or not journey.activation_complete:
        selected = user.office
        office = office_confirmation_payload(selected) if selected else None
    return {"autoOpen": requested or first_prompt, "office": office}
