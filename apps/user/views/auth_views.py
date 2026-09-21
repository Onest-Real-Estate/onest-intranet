import mimetypes
from collections.abc import Callable
from typing import cast

from django.contrib.auth import logout as auth_logout
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_GET, require_POST
from inertia import inertia, render
from inertia.http import clear_history

from apps.web.authorization import enforce_policy

from ..forms import (
    ProfileForm,
    SelfProfileForm,
    form_errors,
    self_profile_page_props,
)
from ..headshot import headshot_public_url, validate_headshot
from ..models import User
from ..services.agent_administration import (
    ADMINISTERED_FIELDS,
    reset_license_verification,
)
from ..services.onboarding_metrics import OnboardingErrorCode, record_onboarding_error
from ..services.profile import (
    PROFILE_AUDIT_FIELDS,
    HeadshotStorageUnavailable,
    can_self_assign_office,
    remove_headshot,
    replace_headshot,
)
from ..services.role_assignments import sync_default_agent_assignment

__all__ = [
    "login_page",
    "logout",
    "headshot_upload",
    "headshot_display",
    "profile",
    "profile_submit",
]

# Fields a user is never permitted to set through a form POST.
# These are enforced both at the form level (excluded from Meta.fields)
# and here as a secondary guard on the raw POST data. ``office`` is the one
# conditional member — see ``profile_submit``.
#
# ``ADMINISTERED_FIELDS`` joins the set wholesale: every value the
# administration page owns is, by definition, one an agent may read on their
# profile and never submit back. Adding an administrative field there protects
# it here without anyone having to remember to.
_PROTECTED_FIELDS = frozenset(
    {
        *(field for field in ADMINISTERED_FIELDS if field != "office"),
        "license_verified_at",
        "license_verified_by",
        "administration_updated_at",
        "administration_updated_by",
        "id",
        "pk",
        "is_staff",
        "is_superuser",
        "is_active",
        "groups",
        "user_permissions",
        "role",
        "roles",
        "role_assignments",
        "profile_completed",
        "profile_completed_at",
        "onboarding_version",
        "date_joined",
        "last_login",
        "display_name",
        "email",
        "password",
    }
)


_LICENSE_FIELDS = ("license_number", "license_state", "license_expires_on")


def _license_details_changed(before: User, after: User) -> bool:
    return any(
        getattr(before, field) != getattr(after, field) for field in _LICENSE_FIELDS
    )


def _rejected_fields(
    request: HttpRequest, extra: frozenset[str] = frozenset()
) -> frozenset[str]:
    return (_PROTECTED_FIELDS | extra) & set(request.POST.keys())


def _log_protected_field_rejection(
    request: HttpRequest, fields: frozenset[str]
) -> None:
    from apps.audit.models import AuditEvent
    from apps.audit.service import AuditTarget, actor_from_user, log_event

    log_event(
        "security.profile.protected_field_rejected",
        actor=actor_from_user(request.user),
        target=AuditTarget(
            target_type="endpoint",
            target_label=request.path,
            # Field *names* only; the submitted values are never recorded.
            target_snapshot={"fields": sorted(fields)},
        ),
        outcome=AuditEvent.Outcome.DENIED,
        source="request",
        channel=request.method or "",
        reason="protected_field_in_payload",
    )


@enforce_policy("login_page")
@inertia("Login")
def login_page(request: HttpRequest):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return {"sessionExpired": request.GET.get("reason") == "session-expired"}


@enforce_policy("logout")
@require_POST
def logout(request: HttpRequest):
    auth_logout(request)
    clear_history(request)
    return redirect("login")


def _render_profile_form(
    request: HttpRequest,
    *,
    component: str,
    props_builder: Callable[..., dict],
    form: ProfileForm | None = None,
    status: int = 200,
) -> HttpResponse:
    user = cast(User, request.user)
    posted = request.POST if form is not None else None
    errors = form_errors(form) if form is not None else {}
    response = render(
        request,
        component,
        props_builder(user, request=request, errors=errors, posted=posted),
    )
    response.status_code = status
    return response


@enforce_policy("headshot_upload")
@require_POST
def headshot_upload(request: HttpRequest) -> JsonResponse:
    """AJAX endpoint: replace or remove the signed-in user's headshot.

    Returns JSON so onboarding and the profile page can both show a preview and
    upload progress before the surrounding form is submitted. The endpoint only
    ever reads ``request.user``; no user identifier is accepted from the client,
    so no cross-user upload or deletion is possible through it.

    ``retryable`` tells the page whether sending the same file again can help:
    a storage outage can, a file Pillow rejected cannot.
    """
    user = cast(User, request.user)

    if request.POST.get("remove") == "1":
        remove_headshot(user)
        return JsonResponse({"url": None})

    upload = request.FILES.get("headshot")
    if not upload:
        return JsonResponse(
            {"error": "Choose a JPEG or PNG photo to upload.", "retryable": False},
            status=400,
        )

    try:
        validate_headshot(upload)
    except ValidationError as exc:
        record_onboarding_error(OnboardingErrorCode.HEADSHOT_INVALID)
        return JsonResponse(
            {"error": " ".join(exc.messages), "retryable": False}, status=422
        )

    try:
        replace_headshot(user, upload)
    except HeadshotStorageUnavailable as exc:
        record_onboarding_error(OnboardingErrorCode.HEADSHOT_STORAGE_UNAVAILABLE)
        return JsonResponse({"error": exc.message, "retryable": True}, status=503)
    return JsonResponse({"url": headshot_public_url(request, user)})


@enforce_policy("headshot_display")
@require_GET
def headshot_display(request: HttpRequest) -> FileResponse:
    """Stream the signed-in user's headshot from storage on the app origin."""
    user = cast(User, request.user)
    if not user.headshot:
        raise Http404
    content_type, _ = mimetypes.guess_type(user.headshot.name)
    response = FileResponse(
        user.headshot.open("rb"),
        content_type=content_type or "application/octet-stream",
    )
    response["Cache-Control"] = "private, max-age=300"
    return response


@enforce_policy("profile")
@require_GET
@inertia("Profile")
def profile(request: HttpRequest):
    """The signed-in user's own profile — always their own record."""
    return self_profile_page_props(cast(User, request.user), request=request)


@enforce_policy("profile_submit")
@require_POST
def profile_submit(request: HttpRequest):
    user = cast(User, request.user)
    can_change_office = can_self_assign_office(user)

    # Office is administrative for anyone whose authorization is scoped by it,
    # so for those users it joins the protected set rather than being ignored.
    extra_protected = frozenset() if can_change_office else frozenset({"office"})
    rejected = _rejected_fields(request, extra_protected)
    if rejected:
        _log_protected_field_rejection(request, rejected)
        return HttpResponse("Forbidden", status=403)

    form = SelfProfileForm(
        request.POST,
        request.FILES,
        instance=user,
        can_change_office=can_change_office,
    )
    if not form.is_valid():
        return _render_profile_form(
            request,
            component="Profile",
            props_builder=self_profile_page_props,
            form=form,
            status=422,
        )

    with transaction.atomic():
        from apps.audit.service import actor_from_user, log_model_change
        from apps.user.services.hierarchy import sync_primary_membership

        before_user = User.objects.get(pk=user.pk)
        saved_user = form.save()
        if before_user.office_id != saved_user.office_id:
            sync_primary_membership(
                saved_user,
                actor=saved_user,
                business_reason="Office changed from the profile page.",
            )
        sync_default_agent_assignment(
            saved_user,
            actor=saved_user,
            business_reason="Office changed from the profile page.",
        )
        if _license_details_changed(before_user, saved_user):
            # An agent may correct their own license, but not carry a
            # broker's verification of the old one onto the new number.
            reset_license_verification(saved_user, reason="license_edited_by_agent")
        log_model_change(
            "user.profile.updated",
            actor=actor_from_user(saved_user),
            instance=saved_user,
            before_instance=before_user,
            snapshot_fields=PROFILE_AUDIT_FIELDS,
            metadata={"path": request.path},
        )

    return redirect("profile")
