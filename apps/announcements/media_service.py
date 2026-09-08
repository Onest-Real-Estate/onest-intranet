"""Attach, replace, reorder, remove, and serve announcement media.

Why there are no presigned URLs
-------------------------------
A presigned S3 link is an *escape* from the audience predicate for the length
of its TTL: once issued, it works for whoever holds it, and a reader who leaves
the audience the next minute keeps it until it expires. Every file here — hero,
attachment, and every generated variant — is therefore streamed through a view
that re-runs :func:`apps.announcements.audience.visible_to` on **each request**.

That is strictly stronger than a short-lived URL and it is what the acceptance
criterion is really after: guessing a storage key gets you nothing (the key is
random and the bucket is private), and a previously issued URL is just the view
path, which authorizes again on arrival. Responses are marked
``private, no-store`` so the bytes do not survive in a shared cache as a
durable artifact either.

Retention
---------
Media is deleted only while the announcement is still a draft. Once published,
replacing or removing a file *deactivates* the row instead: the bytes and the
record of who uploaded what, when, and with which checksum stay reconstructable
for audit. :func:`sweep_orphan_media` is the counterweight — it is what stops
that policy from turning abandoned drafts and rolled-back transactions into
storage nobody can account for.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import FileResponse, Http404
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.announcements.media import (
    MAX_ATTACHMENTS,
    VARIANT_WIDTHS,
    inspect_upload,
    variant_key,
)
from apps.announcements.models import Announcement, AnnouncementMedia
from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.user.models import User
from apps.user.storage import private_storage

Role = AnnouncementMedia.Role
State = AnnouncementMedia.ProcessingState

#: Media on a draft nobody has touched for this long is sweepable.
ABANDONED_DRAFT_DAYS = 30
#: Storage objects with no row are swept once they are older than this. The
#: grace period exists so a write that is mid-flight in another request is
#: never mistaken for an orphan.
ORPHAN_GRACE_HOURS = 6


# --------------------------------------------------------------------------- #
# Authority
# --------------------------------------------------------------------------- #


def assert_can_manage_media(actor: User, announcement: Announcement) -> None:
    """Managing an announcement's files is managing the announcement."""
    from apps.announcements.services import assert_can_manage

    assert_can_manage(actor, announcement.owner_office)


def _target(media: AnnouncementMedia) -> AuditTarget:
    return AuditTarget(
        target_type=AnnouncementMedia._meta.label_lower,
        target_id=str(media.pk or ""),
        target_label=media.display_name,
    )


def _snapshot(media: AnnouncementMedia) -> dict[str, Any]:
    return {
        "display_name": media.display_name,
        "role": media.role,
        "media_type": media.media_type,
        "byte_size": media.byte_size,
        "checksum": media.checksum,
        "processing_state": media.processing_state,
        "is_active": media.is_active,
        "sort_order": media.sort_order,
    }


# --------------------------------------------------------------------------- #
# Upload
# --------------------------------------------------------------------------- #


def _next_sort_order(announcement: Announcement) -> int:
    existing = (
        AnnouncementMedia.objects.filter(
            announcement=announcement, role=Role.ATTACHMENT, is_active=True
        )
        .order_by("-sort_order")
        .values_list("sort_order", flat=True)
        .first()
    )
    return 0 if existing is None else existing + 1


def _assert_attachment_room(announcement: Announcement) -> None:
    count = AnnouncementMedia.objects.filter(
        announcement=announcement, role=Role.ATTACHMENT, is_active=True
    ).count()
    if count >= MAX_ATTACHMENTS:
        raise ValidationError(
            {"file": _(f"An announcement can carry at most {MAX_ATTACHMENTS} files.")}
        )


@transaction.atomic
def attach_media(
    actor: User,
    announcement: Announcement,
    uploaded,
    *,
    role: str = Role.ATTACHMENT,
) -> AnnouncementMedia:
    """Validate, store, and queue processing for one upload.

    The row lands in ``PENDING``. It is not readable by anyone but an
    administrator until the background pass says otherwise, which is what keeps
    an unscanned file from ever reaching a recipient.
    """
    assert_can_manage_media(actor, announcement)
    inspected, data = inspect_upload(uploaded, hero=role == Role.HERO)

    if role == Role.HERO:
        # Replacing the hero retires the old one rather than deleting it; the
        # partial unique constraint only counts the active row.
        _retire_current_hero(actor, announcement)
        sort_order = 0
    else:
        _assert_attachment_room(announcement)
        sort_order = _next_sort_order(announcement)

    media = AnnouncementMedia(
        announcement=announcement,
        role=role,
        display_name=inspected.display_name,
        media_type=inspected.media_type,
        byte_size=inspected.byte_size,
        checksum=inspected.checksum,
        width=inspected.width,
        height=inspected.height,
        processing_state=State.PENDING,
        sort_order=sort_order,
        uploaded_by=actor,
    )
    # ``save=False``: the name is generated by ``_media_upload_to`` and the row
    # is written once, below, so a rollback leaves no half-registered file.
    media.file.save(inspected.display_name, ContentFile(data), save=False)
    media.full_clean(exclude={"uploaded_by"})
    media.save()

    log_event(
        "announcement.media_attached",
        actor=actor_from_user(actor),
        target=_target(media),
        after=_snapshot(media),
        metadata={"announcement_id": announcement.pk},
    )
    # Queued only after the transaction commits: a rollback must not leave a
    # worker chasing a row that never existed.
    transaction.on_commit(lambda: _queue_processing(media.pk))
    return media


def _queue_processing(media_id: int) -> None:
    from apps.announcements.tasks import process_announcement_media

    process_announcement_media.delay(media_id)


def _retire_current_hero(actor: User, announcement: Announcement) -> None:
    current = (
        AnnouncementMedia.objects.filter(
            announcement=announcement, role=Role.HERO, is_active=True
        )
        .select_for_update()
        .first()
    )
    if current is None:
        return
    _deactivate_or_delete(actor, current, reason="replaced")


def _deactivate_or_delete(
    actor: User, media: AnnouncementMedia, *, reason: str
) -> None:
    """Delete while the parent is a draft; retain once it has been published.

    Retention is the default for anything a recipient could already have seen.
    A draft has no readers, so its discarded uploads are storage nobody needs.
    """
    before = _snapshot(media)
    published = media.announcement.status != Announcement.Status.DRAFT
    if published:
        media.is_active = False
        media.save(update_fields=["is_active", "updated_at"])
        action = "announcement.media_retired"
        after = _snapshot(media)
    else:
        _delete_stored_objects(media)
        media.delete()
        action = "announcement.media_deleted"
        after = {}
    log_event(
        action,
        actor=actor_from_user(actor),
        target=_target(media),
        before=before,
        after=after,
        reason=reason,
        metadata={"announcement_id": media.announcement.pk},
    )


def _delete_stored_objects(media: AnnouncementMedia) -> None:
    """Remove the original and every derivative. Never leaves the variants."""
    storage = media.file.storage
    for key in list(media.variants.values()):
        if key:
            storage.delete(key)
    if media.file:
        storage.delete(media.file.name)


@transaction.atomic
def replace_media(actor: User, media: AnnouncementMedia, uploaded) -> AnnouncementMedia:
    """Attach a new file in the same role, retiring or deleting the old one."""
    assert_can_manage_media(actor, media.announcement)
    announcement = media.announcement
    role = media.role
    if role == Role.HERO:
        return attach_media(actor, announcement, uploaded, role=Role.HERO)
    order = media.sort_order
    _deactivate_or_delete(actor, media, reason="replaced")
    replacement = attach_media(actor, announcement, uploaded, role=Role.ATTACHMENT)
    replacement.sort_order = order
    replacement.save(update_fields=["sort_order", "updated_at"])
    return replacement


@transaction.atomic
def remove_media(actor: User, media: AnnouncementMedia) -> None:
    assert_can_manage_media(actor, media.announcement)
    _deactivate_or_delete(actor, media, reason="removed_by_admin")


@transaction.atomic
def reorder_attachments(
    actor: User, announcement: Announcement, ordered_ids: list[int]
) -> None:
    """Set attachment order from a client-supplied sequence of ids.

    The ids are intersected with this announcement's own attachments before
    anything is written, so a foreign id is ignored rather than reparented, and
    any attachment the client forgot keeps a deterministic place at the end.
    """
    assert_can_manage_media(actor, announcement)
    rows = {
        row.pk: row
        for row in AnnouncementMedia.objects.filter(
            announcement=announcement, role=Role.ATTACHMENT, is_active=True
        )
    }
    before = [row.pk for row in sorted(rows.values(), key=lambda r: r.sort_order)]

    seen: list[int] = []
    for candidate in ordered_ids:
        if candidate in rows and candidate not in seen:
            seen.append(candidate)
    seen.extend(pk for pk in rows if pk not in seen)

    for index, pk in enumerate(seen):
        row = rows[pk]
        if row.sort_order != index:
            row.sort_order = index
            row.save(update_fields=["sort_order", "updated_at"])

    log_event(
        "announcement.media_reordered",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=Announcement._meta.label_lower,
            target_id=str(announcement.pk),
            target_label=announcement.slug,
        ),
        before={"order": before},
        after={"order": seen},
    )


# --------------------------------------------------------------------------- #
# Serving
# --------------------------------------------------------------------------- #


def resolve_variant_key(media: AnnouncementMedia, variant: str) -> str:
    """The stored key for a variant, or the original when it is missing.

    Degrading to the original rather than 404-ing is what makes a half-finished
    processing pass invisible to a reader instead of a broken image.
    """
    if not variant:
        return media.file.name
    return media.variants.get(variant) or media.file.name


def stream_media(request, media: AnnouncementMedia, *, variant: str = ""):
    """An authorized response, generated at access time. Never a durable URL."""
    key = resolve_variant_key(media, variant)
    storage = media.file.storage
    if not key or not storage.exists(key):
        raise Http404("That file is no longer stored.")
    response = FileResponse(
        storage.open(key, "rb"),
        as_attachment=not media.is_image,
        filename=media.display_name,
        content_type=media.media_type,
    )
    # The bytes are audience-gated, so they must not be reusable from any cache
    # that outlives this request.
    response["Cache-Control"] = "private, no-store, max-age=0"
    return response


def media_url(media: AnnouncementMedia, *, variant: str = "") -> str:
    if variant:
        return reverse("announcement_media_variant", args=[media.pk, variant])
    return reverse("announcement_media", args=[media.pk])


# --------------------------------------------------------------------------- #
# Payloads
# --------------------------------------------------------------------------- #


def media_payload(media: AnnouncementMedia, *, for_admin: bool = False) -> dict:
    """camelCase media entry.

    ``processingState`` and ``processingNote`` are administrator-only: telling a
    recipient that a file was quarantined tells them a file exists, which is
    itself more than they are entitled to know.
    """
    payload: dict[str, Any] = {
        "id": media.pk,
        "role": media.role,
        "displayName": media.display_name,
        "mediaType": media.media_type,
        "byteSize": media.byte_size,
        "width": media.width,
        "height": media.height,
        "isImage": media.is_image,
        "url": media_url(media),
        "variants": {
            label: media_url(media, variant=label) for label in media.variants
        },
    }
    if for_admin:
        payload["processingState"] = media.processing_state
        payload["processingNote"] = media.processing_note
        payload["isActive"] = media.is_active
        payload["checksum"] = media.checksum
        payload["sortOrder"] = media.sort_order
    return payload


def readable_media(announcement: Announcement) -> list[AnnouncementMedia]:
    return list(
        AnnouncementMedia.objects.filter(announcement=announcement)
        .readable()
        .order_by("role", "sort_order", "pk")
    )


def hero_payload(announcement: Announcement) -> dict | None:
    hero = next(
        (item for item in readable_media(announcement) if item.role == Role.HERO), None
    )
    return media_payload(hero) if hero else None


def attachments_payload(announcement: Announcement) -> list[dict]:
    return [
        media_payload(item)
        for item in readable_media(announcement)
        if item.role == Role.ATTACHMENT
    ]


def admin_media_payload(announcement: Announcement) -> dict:
    """Everything an administrator may see, including what is not ready."""
    rows = list(
        AnnouncementMedia.objects.filter(announcement=announcement, is_active=True)
        .order_by("role", "sort_order", "pk")
        .select_related("announcement")
    )
    hero = next((row for row in rows if row.role == Role.HERO), None)
    return {
        "hero": media_payload(hero, for_admin=True) if hero else None,
        "attachments": [
            media_payload(row, for_admin=True)
            for row in rows
            if row.role == Role.ATTACHMENT
        ],
    }


# --------------------------------------------------------------------------- #
# Publish gate
# --------------------------------------------------------------------------- #


def unprocessed_media(announcement: Announcement) -> list[AnnouncementMedia]:
    """Active media that has not finished processing cleanly."""
    return list(
        AnnouncementMedia.objects.filter(
            announcement=announcement, is_active=True
        ).exclude(processing_state=State.READY)
    )


def media_publish_debt(announcement: Announcement) -> list[tuple[str, Any]]:
    """Publication blockers contributed by media, for ``validation_debt``."""
    if announcement.pk is None:
        return []
    blocked = unprocessed_media(announcement)
    if not blocked:
        return []
    bad = [
        row
        for row in blocked
        if row.processing_state in {State.QUARANTINED, State.FAILED}
    ]
    if bad:
        names = ", ".join(row.display_name for row in bad[:3])
        return [
            (
                "media",
                _(f"Remove or replace the files that failed checks: {names}."),
            )
        ]
    return [("media", _("Files are still being processed. Try again shortly."))]


# --------------------------------------------------------------------------- #
# Orphan cleanup
# --------------------------------------------------------------------------- #


@dataclass
class SweepReport:
    deleted_objects: list[str]
    deleted_rows: list[int]


def sweep_orphan_media(*, now=None) -> SweepReport:
    """Delete storage nobody can account for, and media on abandoned drafts.

    Two distinct leaks, one broom:

    * **Rolled-back writes.** A file is written to storage inside the
      transaction that creates its row. If that transaction rolls back the row
      disappears and the object does not. Anything under the announcements
      prefix with no row pointing at it, older than the grace period, is one of
      those. The grace period is what keeps an in-flight upload in another
      request from looking like an orphan.
    * **Abandoned drafts.** A draft nobody has touched in
      :data:`ABANDONED_DRAFT_DAYS` is not history worth retaining, so its media
      rows and bytes both go.
    """
    moment = now or timezone.now()
    report = SweepReport(deleted_objects=[], deleted_rows=[])

    stale_cutoff = moment - timedelta(days=ABANDONED_DRAFT_DAYS)
    abandoned = AnnouncementMedia.objects.filter(
        announcement__status=Announcement.Status.DRAFT,
        announcement__updated_at__lt=stale_cutoff,
        updated_at__lt=stale_cutoff,
    ).select_related("announcement")
    for media in abandoned:
        _delete_stored_objects(media)
        report.deleted_rows.append(media.pk)
        media.delete()

    known: set[str] = set()
    for name, variants in AnnouncementMedia.objects.values_list("file", "variants"):
        if name:
            known.add(name)
        known.update(key for key in (variants or {}).values() if key)

    # The same callable the model field is declared with, so this resolves the
    # configured backend — and a test's MEDIA_ROOT override — without needing a
    # row to borrow it from. The sweep has to work when no rows are left.
    storage = private_storage()
    grace = moment - timedelta(hours=ORPHAN_GRACE_HOURS)
    try:
        _, files = storage.listdir("announcements")
    except (FileNotFoundError, NotImplementedError):
        return report
    for name in files:
        key = f"announcements/{name}"
        if key in known:
            continue
        try:
            if storage.get_modified_time(key) > grace:
                continue
        except (NotImplementedError, OSError):
            continue
        storage.delete(key)
        report.deleted_objects.append(key)
    return report


def log_media_denial(actor: User, media_id: str, *, reason: str) -> None:
    log_event(
        "security.announcement.media_denied",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=AnnouncementMedia._meta.label_lower, target_id=str(media_id)
        ),
        outcome=AuditEvent.Outcome.DENIED,
        reason=reason,
    )


def assert_readable(actor: User, media: AnnouncementMedia) -> None:
    """A recipient may read a file only if the parent reaches them *and* the
    file itself passed processing. Both, on every request."""
    from apps.announcements.audience import assert_visible

    assert_visible(actor, media.announcement, reason="media_out_of_audience")
    if not media.is_readable:
        log_media_denial(actor, str(media.pk), reason="media_not_ready")
        raise PermissionDenied("That file is not available.")


__all__ = [
    "VARIANT_WIDTHS",
    "admin_media_payload",
    "assert_can_manage_media",
    "assert_readable",
    "attach_media",
    "attachments_payload",
    "hero_payload",
    "media_payload",
    "media_publish_debt",
    "media_url",
    "remove_media",
    "reorder_attachments",
    "replace_media",
    "resolve_variant_key",
    "stream_media",
    "sweep_orphan_media",
    "variant_key",
]
