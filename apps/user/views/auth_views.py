from typing import cast

from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_GET, require_POST
from inertia import inertia, render
from inertia.http import clear_history

from ..forms import ProfileForm, form_errors, profile_page_props
from ..models import User

__all__ = [
    "login_page",
    "logout",
    "onboarding",
    "onboarding_submit",
    "profile",
    "profile_submit",
]


@inertia("Login")
def login_page(request: HttpRequest):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return {}


@require_POST
def logout(request: HttpRequest):
    auth_logout(request)
    clear_history(request)
    return redirect("login")


def _render_profile_form(
    request: HttpRequest,
    *,
    component: str,
    form: ProfileForm | None = None,
    status: int = 200,
) -> HttpResponse:
    user = cast(User, request.user)
    posted = request.POST if form is not None else None
    errors = form_errors(form) if form is not None else {}
    response = render(
        request,
        component,
        profile_page_props(user, errors=errors, posted=posted),
    )
    response.status_code = status
    return response


@login_required
@require_GET
@inertia("Onboarding")
def onboarding(request: HttpRequest):
    """First-signup details page. Completed users go to the dashboard."""
    user = cast(User, request.user)
    if user.profile_completed:
        return redirect("dashboard")
    return profile_page_props(user)


@login_required
@require_POST
def onboarding_submit(request: HttpRequest):
    """Save onboarding details and mark the profile complete."""
    user = cast(User, request.user)
    form = ProfileForm(request.POST, instance=user)
    if form.is_valid():
        user = form.save()
        user.profile_completed = True
        user.save(update_fields=["profile_completed"])
        return redirect("dashboard")
    return _render_profile_form(request, component="Onboarding", form=form, status=422)


@login_required
@require_GET
@inertia("Profile")
def profile(request: HttpRequest):
    """Edit-profile page (including optional MLS / NRDS)."""
    return profile_page_props(cast(User, request.user))


@login_required
@require_POST
def profile_submit(request: HttpRequest):
    user = cast(User, request.user)
    form = ProfileForm(request.POST, instance=user)
    if form.is_valid():
        form.save()
        return redirect("profile")
    return _render_profile_form(request, component="Profile", form=form, status=422)
