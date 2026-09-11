"""First-login onboarding: resumable profile sections, review, and finish.

Every endpoint here only ever reads ``request.user``. No URL, field, or payload
names a user, and the protected-field guard shared with ``/profile`` rejects a
crafted identifier before any form is bound.
"""

from typing import cast

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from inertia import render

from apps.web.authorization import enforce_policy
from apps.web.flash import set_flash

from ..forms import (
    OnboardingProfileFinalizeForm,
    OnboardingProfileSubmissionForm,
    form_errors,
)
from ..models import User
from ..services.onboarding_profile import (
    EDITABLE_SECTIONS,
    ProfileAlreadyFinalized,
    ProfileFlowContext,
    StaleOnboardingVersion,
    StaleProfileSection,
    finalize_profile,
    flow_context,
    next_section,
    onboarding_profile_page_props,
    resolve_section,
    save_profile_section,
)
from ..services.profile import HeadshotStorageUnavailable, OnboardingSection
from .auth_views import _log_protected_field_rejection, _rejected_fields

__all__ = [
    "onboarding",
    "onboarding_profile_finalize",
    "onboarding_profile_save",
]


def _form_message(message: str) -> dict:
    return {"fields": {}, "form": [message]}


def _render_flow(
    request: HttpRequest,
    *,
    section: OnboardingSection,
    context: ProfileFlowContext | None = None,
    status: int = 200,
    errors: dict | None = None,
    posted=None,
) -> HttpResponse:
    from apps.user.services.onboarding_state import (
        agent_journey_payload,
        journey_applies_to,
        journey_for_user,
    )

    user = cast(User, request.user)
    props = onboarding_profile_page_props(
        user,
        request=request,
        section=section,
        context=context,
        errors=errors,
        posted=posted,
    )
    if journey_applies_to(user):
        journey = getattr(request, "_onboarding_journey", None) or journey_for_user(
            user
        )
        props["onboardingJourney"] = agent_journey_payload(journey)
    response = render(request, "Onboarding", props)
    response.status_code = status
    return response


def _protected_field_denial(request: HttpRequest) -> HttpResponse | None:
    rejected = _rejected_fields(request)
    if not rejected:
        return None
    _log_protected_field_rejection(request, rejected)
    return HttpResponse("Forbidden", status=403)


@enforce_policy("onboarding")
@require_GET
def onboarding(request: HttpRequest) -> HttpResponse:
    """The resumable profile flow. Completed users go to the dashboard."""
    user = cast(User, request.user)
    if user.profile_completed:
        return redirect("dashboard")
    context = flow_context(user)
    section = resolve_section(context, request.GET.get("section"))
    return _render_flow(request, section=section, context=context)


@enforce_policy("onboarding_profile_save")
@require_POST
def onboarding_profile_save(request: HttpRequest, section: str) -> HttpResponse:
    """Save one section, then move to the next one (post/redirect/get)."""
    user = cast(User, request.user)
    try:
        target = OnboardingSection(section)
    except ValueError:
        raise Http404 from None
    if target not in EDITABLE_SECTIONS:
        raise Http404
    denial = _protected_field_denial(request)
    if denial is not None:
        return denial
    if user.profile_completed:
        return redirect("dashboard")

    tokens = OnboardingProfileSubmissionForm(request.POST)
    if not tokens.is_valid():
        return _render_flow(
            request,
            section=target,
            status=409,
            errors=_form_message(StaleOnboardingVersion.message),
            posted=request.POST,
        )
    try:
        result = save_profile_section(
            user=user,
            section=target,
            data=request.POST,
            expected_revision=tokens.cleaned_data["revision"],
            expected_onboarding_version=tokens.cleaned_data[
                "expected_onboarding_version"
            ],
        )
    except ProfileAlreadyFinalized:
        return redirect("dashboard")
    except StaleOnboardingVersion as exc:
        return _render_flow(
            request, section=target, status=409, errors=_form_message(exc.message)
        )
    except StaleProfileSection as exc:
        # Keep what the agent typed: the newer values are one save away from
        # being replaced deliberately, never silently.
        return _render_flow(
            request,
            section=target,
            status=409,
            errors=_form_message(exc.message),
            posted=request.POST,
        )
    if result.invalid_form is not None:
        return _render_flow(
            request,
            section=target,
            status=422,
            errors=form_errors(result.invalid_form),
            posted=request.POST,
        )
    return redirect(f"{reverse('onboarding')}?section={next_section(target)}")


@enforce_policy("onboarding_profile_finalize")
@require_POST
def onboarding_profile_finalize(request: HttpRequest) -> HttpResponse:
    """Confirm the reviewed profile and complete onboarding's profile half."""
    user = cast(User, request.user)
    denial = _protected_field_denial(request)
    if denial is not None:
        return denial
    if user.profile_completed:
        return redirect("dashboard")

    submission = OnboardingProfileFinalizeForm(request.POST)
    if not submission.is_valid():
        return _render_flow(
            request,
            section=OnboardingSection.REVIEW,
            status=409,
            errors=_form_message(StaleOnboardingVersion.message),
        )
    try:
        result = finalize_profile(
            user=user,
            confirmed=submission.cleaned_data["confirm_review"],
            expected_onboarding_version=submission.cleaned_data[
                "expected_onboarding_version"
            ],
        )
    except StaleOnboardingVersion as exc:
        return _render_flow(
            request,
            section=OnboardingSection.REVIEW,
            status=409,
            errors=_form_message(exc.message),
        )
    except HeadshotStorageUnavailable as exc:
        return _render_flow(
            request,
            section=OnboardingSection.REVIEW,
            status=503,
            errors=_form_message(exc.message),
        )
    if result.errors is not None:
        return _render_flow(
            request,
            section=OnboardingSection.REVIEW,
            status=422,
            errors=result.errors,
        )
    if result.completed:
        set_flash(
            request,
            level="success",
            message="Your profile is complete. Your office takes it from here.",
        )
    return redirect("dashboard")
