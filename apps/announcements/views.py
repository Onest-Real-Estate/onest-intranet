"""Announcement surfaces. Every one of them asks the same audience predicate.

The feed, the detail page, and the attachment download share
:mod:`apps.announcements.audience`, so a guessed URL is exactly as permissive
as the list the reader was actually shown — which is to say, not at all.
Audience is re-evaluated on each request; nothing here trusts a recipient set
computed when the announcement was published.
"""

from __future__ import annotations

from typing import cast

from django.core.exceptions import ValidationError
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_GET, require_POST
from inertia import inertia

from apps.announcements.audience import (
    assert_visible,
    describe_audience,
    search_recipients,
)
from apps.announcements.media import allowed_matrix_payload
from apps.announcements.media_service import (
    admin_media_payload,
    assert_can_manage_media,
    assert_readable,
    attach_media,
    attachments_payload,
    hero_payload,
    media_payload,
    remove_media,
    reorder_attachments,
    replace_media,
    stream_media,
)
from apps.announcements.models import Announcement, AnnouncementMedia
from apps.announcements.services import (
    build_feed,
    category_filter_options,
    feed_row,
    priority_filter_options,
)
from apps.user.models import User
from apps.web.authorization import enforce_policy
from apps.web.contracts import empty_validation_errors


def _page_param(request: HttpRequest) -> int:
    try:
        return max(1, int(request.GET.get("page", "1")))
    except ValueError:
        return 1


@enforce_policy("announcements_feed")
@require_GET
@inertia("Announcements")
def announcements(request: HttpRequest):
    actor = cast(User, request.user)
    feed = build_feed(actor, params=request.GET, page=_page_param(request))
    selected_category = feed["filters"]["category"]
    return {
        "feed": feed,
        "filterOptions": {
            # A retired category the reader is filtering by stays listed so the
            # control can show the filter that is actually applied.
            "categories": category_filter_options(include_codes=(selected_category,)),
            "priorities": priority_filter_options(),
        },
    }


@enforce_policy("announcement_detail")
@require_GET
@inertia("AnnouncementDetail")
def announcement_detail(request: HttpRequest, announcement_id: int):
    actor = cast(User, request.user)
    # Fetched by id, then authorized by audience — never filtered by an office
    # the client named. ``assert_visible`` records the denial.
    announcement = get_object_or_404(
        Announcement.objects.select_related("category", "owner_office"),
        pk=announcement_id,
    )
    assert_visible(actor, announcement, reason="detail_out_of_audience")
    return {
        "announcement": {
            **feed_row(announcement),
            "audience": describe_audience(announcement),
            "hero": hero_payload(announcement),
            "attachments": attachments_payload(announcement),
        }
    }


@enforce_policy("announcement_media")
@require_GET
def announcement_media(request: HttpRequest, media_id: int):
    """One original file, authorized at access time.

    Streamed rather than redirected to a signed link: the audience predicate
    runs on this request, for this reader, and nothing durable is handed out
    that could outlive their place in the audience.
    """
    return _serve_media(request, media_id, variant="")


@enforce_policy("announcement_media_variant")
@require_GET
def announcement_media_variant(request: HttpRequest, media_id: int, variant: str):
    """A generated derivative, behind exactly the same check as the original.

    An unknown or not-yet-generated variant degrades to the original instead of
    404-ing, so a half-finished processing pass is invisible to the reader
    rather than a broken image.
    """
    return _serve_media(request, media_id, variant=variant)


def _serve_media(request: HttpRequest, media_id: int, *, variant: str):
    actor = cast(User, request.user)
    media = get_object_or_404(
        AnnouncementMedia.objects.select_related(
            "announcement", "announcement__owner_office"
        ),
        pk=media_id,
    )
    assert_readable(actor, media)
    return stream_media(request, media, variant=variant)


@enforce_policy("announcement_recipient_search")
@require_GET
def recipient_search(request: HttpRequest):
    """Typeahead for individual recipients, bounded by the actor's own grant.

    JSON rather than an Inertia page: it is called from a compose control. The
    scope and the minimum query length are enforced in the service, so this
    view cannot widen either by passing something different.
    """
    actor = cast(User, request.user)
    return JsonResponse({"results": search_recipients(actor, request.GET.get("q", ""))})


# --------------------------------------------------------------------------- #
# Management surface
# --------------------------------------------------------------------------- #


def _managed_announcement(actor: User, announcement_id: int) -> Announcement:
    """Fetch by id, then authorize. Never filtered by a client-named office."""
    announcement = get_object_or_404(
        Announcement.objects.select_related("owner_office", "category"),
        pk=announcement_id,
    )
    assert_can_manage_media(actor, announcement)
    return announcement


@enforce_policy("announcement_media_manager")
@require_GET
@inertia("AnnouncementMediaManager")
def announcement_media_manager(request: HttpRequest, announcement_id: int):
    actor = cast(User, request.user)
    announcement = _managed_announcement(actor, announcement_id)
    return {
        "announcement": {
            "id": announcement.pk,
            "title": announcement.title,
            "status": announcement.status,
        },
        "media": admin_media_payload(announcement),
        "limits": allowed_matrix_payload(),
        "validation": empty_validation_errors(),
    }


def _media_error(exc: ValidationError, status: int = 422) -> JsonResponse:
    """Split a ``ValidationError`` the way the shared payload expects.

    ``form`` is for non-field errors only. An empty list is the right answer
    when everything was per-field — falling back to ``exc.messages`` there
    would republish each field's sentence at form level, because ``messages``
    is those same per-field entries flattened, and the reader would see the
    same line twice.
    """
    if hasattr(exc, "message_dict"):
        data = exc.message_dict
        return JsonResponse(
            {
                "validation": {
                    "fields": {
                        field: [str(message) for message in messages]
                        for field, messages in data.items()
                        if field != "__all__"
                    },
                    "form": [str(message) for message in data.get("__all__", [])],
                }
            },
            status=status,
        )
    # No field mapping at all: every message is a form-level one.
    return JsonResponse(
        {
            "validation": {
                "fields": {},
                "form": [str(message) for message in exc.messages],
            }
        },
        status=status,
    )


@enforce_policy("announcement_media_upload")
@require_POST
def announcement_media_upload(request: HttpRequest, announcement_id: int):
    """Upload a hero image or an attachment.

    Answers JSON because the control reports progress and per-file errors
    inline; an Inertia redirect would discard the upload's own feedback.
    """
    actor = cast(User, request.user)
    announcement = _managed_announcement(actor, announcement_id)
    uploaded = request.FILES.get("file")
    if uploaded is None:
        return _media_error(ValidationError({"file": "Choose a file to upload."}))
    role = (
        AnnouncementMedia.Role.HERO
        if request.POST.get("role") == AnnouncementMedia.Role.HERO
        else AnnouncementMedia.Role.ATTACHMENT
    )
    try:
        media = attach_media(actor, announcement, uploaded, role=role)
    except ValidationError as exc:
        return _media_error(exc)
    return JsonResponse({"media": media_payload(media, for_admin=True)}, status=201)


@enforce_policy("announcement_media_replace")
@require_POST
def announcement_media_replace(request: HttpRequest, media_id: int):
    actor = cast(User, request.user)
    media = get_object_or_404(
        AnnouncementMedia.objects.select_related("announcement"), pk=media_id
    )
    uploaded = request.FILES.get("file")
    if uploaded is None:
        return _media_error(ValidationError({"file": "Choose a replacement file."}))
    try:
        replacement = replace_media(actor, media, uploaded)
    except ValidationError as exc:
        return _media_error(exc)
    return JsonResponse({"media": media_payload(replacement, for_admin=True)})


@enforce_policy("announcement_media_remove")
@require_POST
def announcement_media_remove(request: HttpRequest, media_id: int):
    actor = cast(User, request.user)
    media = get_object_or_404(
        AnnouncementMedia.objects.select_related("announcement"), pk=media_id
    )
    remove_media(actor, media)
    return redirect("announcement_media_manager", announcement_id=media.announcement.pk)


@enforce_policy("announcement_media_reorder")
@require_POST
def announcement_media_reorder(request: HttpRequest, announcement_id: int):
    actor = cast(User, request.user)
    announcement = _managed_announcement(actor, announcement_id)
    raw = request.POST.getlist("order")
    ordered: list[int] = []
    for value in raw:
        try:
            ordered.append(int(value))
        except (TypeError, ValueError):
            continue
    reorder_attachments(actor, announcement, ordered)
    return redirect("announcement_media_manager", announcement_id=announcement.pk)
