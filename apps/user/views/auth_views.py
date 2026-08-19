from typing import cast

from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
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
    "headshot_upload",
    "profile",
    "profile_submit",
]

# Fields a user is never permitted to set through a form POST.
# These are enforced both at the form level (excluded from Meta.fields)
# and here as a secondary guard on the raw POST data.
_PROTECTED_FIELDS = frozenset(
    {
        "is_staff",
        "is_superuser",
        "is_active",
        "groups",
        "user_permissions",
        "profile_completed",
        "profile_completed_at",
        "onboarding_version",
        "date_joined",
        "last_login",
        "email",
        "password",
    }
)


def _has_protected_field(request: HttpRequest) -> bool:
    return bool(_PROTECTED_FIELDS & set(request.POST.keys()))


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
    """Save onboarding details and mark the profile complete, atomically."""
    user = cast(User, request.user)

    # Secondary mass-assignment guard — block crafted POSTs even if the form
    # somehow failed to exclude these fields.
    if _has_protected_field(request):
        return HttpResponse("Forbidden", status=403)

    # Already completed — idempotency: just redirect.
    if user.profile_completed:
        return redirect("dashboard")

    form = ProfileForm(request.POST, request.FILES, instance=user)
    if not form.is_valid():
        return _render_profile_form(
            request, component="Onboarding", form=form, status=422
        )

    with transaction.atomic():
        from apps.audit.service import actor_from_user, log_model_change

        before_user = User.objects.get(pk=user.pk)
        saved_user = form.save(commit=False)
        saved_user.profile_completed = True
        saved_user.profile_completed_at = timezone.now()
        saved_user.save()
        log_model_change(
            "user.onboarding.completed",
            actor=actor_from_user(user),
            instance=saved_user,
            before_instance=before_user,
            snapshot_fields=[
                "first_name",
                "last_name",
                "display_name",
                "phone_number",
                "street_address",
                "city",
                "state",
                "zip_code",
                "office",
                "profile_completed",
                "profile_completed_at",
                "onboarding_version",
            ],
            metadata={"path": request.path},
        )
        try:
            from apps.audit.events import publish

            publish(
                "user.onboarded",
                actor_id=str(saved_user.pk),
                subject=f"user:{saved_user.pk}",
                payload={
                    "user_id": saved_user.pk,
                    "email": saved_user.email,
                    "office_id": saved_user.office_id,
                },
            )
        except ImportError:
            # audit app not yet merged into this branch.
            pass

    return redirect("dashboard")


@login_required
@require_POST
def headshot_upload(request: HttpRequest) -> JsonResponse:
    """AJAX endpoint: validate and upload headshot, return URL.

    Returns JSON so the multi-step frontend can preview before final submit.
    The saved file path is stored in the session; onboarding_submit reads it.
    Only the owning user's upload is accepted (authentication enforced by
    @login_required; no cross-user upload is possible through this endpoint).
    """
    from ..headshot import validate_headshot

    upload = request.FILES.get("headshot")
    if not upload:
        return JsonResponse({"error": "No file provided."}, status=400)

    try:
        validate_headshot(upload)
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=422)

    user = cast(User, request.user)
    if user.headshot:
        user.headshot.delete(save=False)
    user.headshot = upload  # ty: ignore[invalid-assignment]
    user.save(update_fields=["headshot"])

    return JsonResponse({"url": user.headshot.url})


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

    if _has_protected_field(request):
        return HttpResponse("Forbidden", status=403)

    form = ProfileForm(request.POST, request.FILES, instance=user)
    if form.is_valid():
        form.save()
        return redirect("profile")
    return _render_profile_form(request, component="Profile", form=form, status=422)
