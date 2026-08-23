"""The announcement workspace's HTTP surface.

Two rules shape every view here:

* **Load through the scoped queryset, never by bare primary key.** An
  announcement outside the actor's grant is a 404, not a 403 — confirming that
  an id exists is itself a disclosure across a scope boundary.
* **Answer the failure the caller actually hit.** A refused field is 422 with
  the messages attached; a row that moved underneath is 409 with the current
  values re-rendered, so the recovery path is "read theirs, then reapply mine"
  rather than a lost update or a silent overwrite.

Nothing here decides authority. ``enforce_policy`` gates the route on the
reviewed permission and :mod:`apps.announcements.administration` re-derives
scope, capability, and audience authority on every write.
"""

from __future__ import annotations

from typing import Any, cast

from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_GET, require_POST
from inertia import inertia, render

from apps.announcements.administration import (
    PAGE_SIZE,
    StaleAnnouncementVersion,
    TransitionRefused,
    WorkspaceFilters,
    admin_row,
    announcement_version,
    apply_workspace_filters,
    audience_choice_payload,
    capabilities,
    category_options,
    create_announcement,
    detail_payload,
    manageable_queryset,
    order_for_workspace,
    preview_payload,
    publishable_office_queryset,
    set_pinned,
    transition,
    update_announcement,
)
from apps.announcements.forms import (
    AnnouncementForm,
    AnnouncementPinForm,
    AnnouncementTransitionForm,
)
from apps.announcements.models import Announcement
from apps.announcements.services import priority_filter_options
from apps.announcements.taxonomy import PRIORITY_CODES
from apps.user.models import Office, User
from apps.web.authorization import enforce_policy
from apps.web.contracts import empty_validation_errors, list_response, validation_errors

INDEX_ROUTE = "admin_announcements"
INDEX_PAGE = "AnnouncementAdministration"
WORKSPACE_PAGE = "AnnouncementWorkspace"


def _page_param(request: HttpRequest) -> int:
    try:
        return max(1, int(request.GET.get("page", "1")))
    except ValueError:
        return 1


def _target(request: HttpRequest, announcement_id: int) -> Announcement:
    actor = cast(User, request.user)
    return get_object_or_404(manageable_queryset(actor), pk=announcement_id)


# --------------------------------------------------------------------------- #
# Index
# --------------------------------------------------------------------------- #


#: Draft keys the create drawer posts, echoed back after a 422 so a rejected
#: create loses nothing the author typed. Multi-valued audience fields are
#: listed separately because they come back as lists, not scalars.
_SHEET_DRAFT_FIELDS: tuple[str, ...] = (
    "owner_office",
    "title",
    "summary",
    "body",
    "category",
    "priority",
    "publish_at",
    "expires_at",
    "cta_label",
    "cta_url",
)

_SHEET_DRAFT_LISTS: tuple[str, ...] = (
    "audience_roles",
    "audience_regions",
    "audience_offices",
    "audience_users",
)


def _sheet_draft(params) -> dict[str, Any]:
    draft: dict[str, Any] = {
        name: value for name in _SHEET_DRAFT_FIELDS if (value := params.get(name, ""))
    }
    for name in _SHEET_DRAFT_LISTS:
        values = params.getlist(name)
        if values:
            draft[name] = values
    if params.get("audience_company") in {"on", "true", "True"}:
        draft["audience_company"] = "on"
    return draft


def index_props(
    actor: User,
    *,
    params,
    page: int = 1,
    create_sheet: dict[str, Any] | None = None,
    errors: dict | None = None,
) -> dict[str, Any]:
    from apps.announcements.models import AnnouncementCategory

    known_categories = list(AnnouncementCategory.objects.values_list("code", flat=True))
    filters = WorkspaceFilters.from_params(
        params, known_categories=known_categories, known_priorities=PRIORITY_CODES
    )
    rows = order_for_workspace(
        apply_workspace_filters(manageable_queryset(actor), filters)
    )
    total = rows.count()
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    current = min(max(page, 1), total_pages)
    start = (current - 1) * PAGE_SIZE
    items = [admin_row(row) for row in rows[start : start + PAGE_SIZE]]
    offices = [
        {"value": office.pk, "label": office.name}
        for office in publishable_office_queryset(actor)
    ]
    return {
        "announcements": list_response(
            items,
            page=current,
            page_size=PAGE_SIZE,
            total_items=total,
            filters=filters.as_payload(),
            sort_key="updatedAt",
            sort_direction="desc",
        ),
        "filterOptions": {
            "categories": category_options(include_codes=(filters.category,)),
            "priorities": priority_filter_options(),
            "offices": offices,
        },
        # Everything the create drawer needs to render inline, so opening it
        # costs no round trip — and so its choices come from the same
        # grant-bounded querysets the save re-checks.
        "createOptions": {
            "offices": offices,
            "categories": category_options(),
            "priorities": priority_filter_options(),
            "audience": audience_choice_payload(actor),
        },
        "createSheet": create_sheet,
        "capabilities": capabilities(actor).payload(),
        "errors": errors or empty_validation_errors(),
    }


@enforce_policy("operations_admin_announcements")
@require_GET
@inertia(INDEX_PAGE)
def announcement_administration_index(request: HttpRequest):
    actor = cast(User, request.user)
    # ``?create=1`` is how Quick Create opens the drawer here instead of sending
    # the author to a standalone form. It only opens a drawer — the create
    # endpoint still applies every permission and scope check on submit.
    opening = request.GET.get("create") == "1"
    return index_props(
        actor,
        params=request.GET,
        page=_page_param(request),
        create_sheet={"open": True, "draft": {}} if opening else None,
    )


def _render_index_with_sheet_errors(
    request: HttpRequest, *, errors: dict
) -> HttpResponse:
    """Re-render the queue with the create drawer reopened and repopulated.

    A rejected create is answered with the *list* page rather than the
    standalone form, because that is the page the author was on. The filters
    they were reading are re-parsed from the submission so the queue behind the
    drawer does not silently reset while they fix a field.
    """
    actor = cast(User, request.user)
    response = render(
        request,
        INDEX_PAGE,
        index_props(
            actor,
            params=request.POST,
            create_sheet={"open": True, "draft": _sheet_draft(request.POST)},
            errors=errors,
        ),
    )
    response.status_code = 422
    return response


# --------------------------------------------------------------------------- #
# Workspace
# --------------------------------------------------------------------------- #


def _preview_office(actor: User, raw: str) -> Office | None:
    """Resolve the previewed office inside the actor's own grant.

    A client-named office is never authority here either: it is looked up
    through ``publishable_office_queryset`` so previewing cannot be used to ask
    whether an office outside the grant exists.
    """
    if not raw.isdigit():
        return None
    return publishable_office_queryset(actor).filter(pk=int(raw)).first()


def workspace_props(
    actor: User,
    *,
    announcement: Announcement | None = None,
    errors: dict | None = None,
    posted=None,
    preview_office: str = "",
    preview_role: str = "",
) -> dict[str, Any]:
    office = _preview_office(actor, preview_office) if announcement else None
    role = (
        preview_role
        if preview_role
        in {option["value"] for option in audience_choice_payload(actor)["roles"]}
        else ""
    )
    return {
        "announcement": detail_payload(announcement) if announcement else None,
        "officeOptions": [
            {"value": office_row.pk, "label": office_row.name}
            for office_row in publishable_office_queryset(actor)
        ],
        "categoryOptions": category_options(
            include_codes=(
                (announcement.category.code,)
                if announcement and announcement.category
                else ()
            )
        ),
        "priorityOptions": priority_filter_options(),
        "audienceOptions": audience_choice_payload(actor),
        "capabilities": capabilities(actor).payload(),
        "preview": (
            {
                **preview_payload(announcement, office=office, role_code=role),
                "roleCode": role,
                "officeId": office.pk if office else None,
            }
            if announcement
            else None
        ),
        "errors": errors or empty_validation_errors(),
        "posted": _posted_payload(posted),
    }


def _posted_payload(posted) -> dict[str, list[str]] | None:
    """What the author typed, echoed back so a rejection loses nothing.

    Returned as lists because the audience fields are multi-valued; the page
    reads scalars off index zero.
    """
    if posted is None:
        return None
    return {key: posted.getlist(key) for key in posted}


@enforce_policy("announcement_new")
@require_GET
@inertia(WORKSPACE_PAGE)
def announcement_new(request: HttpRequest):
    return workspace_props(cast(User, request.user))


@enforce_policy("announcement_edit")
@require_GET
@inertia(WORKSPACE_PAGE)
def announcement_edit(request: HttpRequest, announcement_id: int):
    actor = cast(User, request.user)
    return workspace_props(
        actor,
        announcement=_target(request, announcement_id),
        preview_office=request.GET.get("previewOffice", "").strip(),
        preview_role=request.GET.get("previewRole", "").strip(),
    )


def _render_workspace(
    request: HttpRequest,
    *,
    announcement: Announcement | None,
    errors: dict,
    status: int,
) -> HttpResponse:
    actor = cast(User, request.user)
    response = render(
        request,
        WORKSPACE_PAGE,
        workspace_props(
            actor,
            announcement=announcement,
            errors=errors,
            posted=request.POST,
        ),
    )
    response.status_code = status
    return response


def _validation_payload(exc: ValidationError) -> dict[str, Any]:
    """Split a ``ValidationError`` the way the shared payload expects.

    ``form`` carries non-field messages only. Falling back to ``exc.messages``
    there would republish each field's sentence at form level, because
    ``messages`` is those same per-field entries flattened.
    """
    if hasattr(exc, "message_dict"):
        data = exc.message_dict
        return {
            "fields": {
                field: [str(message) for message in messages]
                for field, messages in data.items()
                if field != "__all__"
            },
            "form": [str(message) for message in data.get("__all__", [])],
        }
    return {"fields": {}, "form": [str(message) for message in exc.messages]}


def _submit(request: HttpRequest, announcement: Announcement | None) -> HttpResponse:
    actor = cast(User, request.user)
    # The drawer on the queue page posts here too. It differs only in where a
    # rejection is rendered — the list with the drawer reopened, rather than the
    # standalone form page — so validation and authorization stay one path.
    from_sheet = announcement is None and request.POST.get("context") == "sheet"
    form = AnnouncementForm(
        request.POST, instance=announcement or Announcement(), actor=actor
    )
    if not form.is_valid():
        errors = validation_errors(form)
        if from_sheet:
            return _render_index_with_sheet_errors(request, errors=errors)
        return _render_workspace(
            request,
            announcement=announcement,
            errors=errors,
            status=422,
        )
    try:
        if announcement is None:
            saved = create_announcement(
                actor=actor,
                office=form.cleaned_data["owner_office"],
                cleaned=form.field_values,
                selectors=form.selectors,
            )
        else:
            saved = update_announcement(
                actor=actor,
                announcement=announcement,
                cleaned=form.field_values,
                selectors=form.selectors,
                expected_version=form.cleaned_data.get("expected_version", ""),
            )
    except StaleAnnouncementVersion as exc:
        # 409, not 422: nothing typed is wrong — the record moved underneath, so
        # the page re-renders with the *current* values beside what was typed.
        return _render_workspace(
            request,
            announcement=Announcement.objects.get(pk=announcement.pk)
            if announcement
            else None,
            errors={"fields": {}, "form": [exc.message]},
            status=409,
        )
    except ValidationError as exc:
        errors = _validation_payload(exc)
        if from_sheet:
            return _render_index_with_sheet_errors(request, errors=errors)
        return _render_workspace(
            request,
            announcement=announcement,
            errors=errors,
            status=422,
        )
    # Success always lands in the workspace, drawer or not: preview, the publish
    # checklist, and the lifecycle live there, and creating is only the first
    # step of the job the author came to do.
    return redirect("announcement_edit", announcement_id=saved.pk)


@enforce_policy("announcement_create")
@require_POST
def announcement_create(request: HttpRequest):
    return _submit(request, None)


@enforce_policy("announcement_update")
@require_POST
def announcement_update(request: HttpRequest, announcement_id: int):
    return _submit(request, _target(request, announcement_id))


# --------------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------------- #


def _lifecycle_failure(
    request: HttpRequest, announcement: Announcement, message: str, status: int
) -> HttpResponse:
    actor = cast(User, request.user)
    response = render(
        request,
        WORKSPACE_PAGE,
        workspace_props(
            actor,
            announcement=Announcement.objects.get(pk=announcement.pk),
            errors={"fields": {}, "form": [message]},
        ),
    )
    response.status_code = status
    return response


@enforce_policy("announcement_lifecycle")
@require_POST
def announcement_lifecycle(request: HttpRequest, announcement_id: int):
    actor = cast(User, request.user)
    announcement = _target(request, announcement_id)
    form = AnnouncementTransitionForm(request.POST)
    if not form.is_valid():
        return _lifecycle_failure(
            request, announcement, "That is not an announcement action.", 422
        )
    try:
        transition(
            actor=actor,
            announcement=announcement,
            action=form.cleaned_data["action"],
            expected_version=form.cleaned_data.get("expected_version", ""),
        )
    except StaleAnnouncementVersion as exc:
        return _lifecycle_failure(request, announcement, exc.message, 409)
    except TransitionRefused as exc:
        return _lifecycle_failure(request, announcement, exc.message, 422)
    except ValidationError as exc:
        # The publish checklist. Reported per field so the page can mark each
        # outstanding item rather than showing one flattened sentence.
        response = render(
            request,
            WORKSPACE_PAGE,
            workspace_props(
                actor,
                announcement=Announcement.objects.get(pk=announcement.pk),
                errors=_validation_payload(exc),
            ),
        )
        response.status_code = 422
        return response
    return redirect("announcement_edit", announcement_id=announcement.pk)


@enforce_policy("announcement_pin")
@require_POST
def announcement_pin(request: HttpRequest, announcement_id: int):
    actor = cast(User, request.user)
    announcement = _target(request, announcement_id)
    form = AnnouncementPinForm(request.POST)
    if not form.is_valid():
        return _lifecycle_failure(request, announcement, "Send a pin state.", 422)
    try:
        set_pinned(
            actor=actor,
            announcement=announcement,
            pinned=form.cleaned_data["pinned"],
            expected_version=form.cleaned_data.get("expected_version", ""),
        )
    except StaleAnnouncementVersion as exc:
        return _lifecycle_failure(request, announcement, exc.message, 409)
    except (TransitionRefused, ValidationError) as exc:
        message = getattr(exc, "message", None) or "; ".join(
            str(item) for item in exc.messages
        )
        return _lifecycle_failure(request, announcement, str(message), 422)
    return redirect(INDEX_ROUTE)


__all__ = [
    "announcement_administration_index",
    "announcement_new",
    "announcement_edit",
    "announcement_create",
    "announcement_update",
    "announcement_lifecycle",
    "announcement_pin",
    "announcement_version",
    "index_props",
    "workspace_props",
]
