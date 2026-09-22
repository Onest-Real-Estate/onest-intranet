"""Authorized Hub streaming for transaction document versions."""

from __future__ import annotations

from django.http import FileResponse, Http404
from django.utils.translation import gettext_lazy as _

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.transactions.concurrency import can_manage_workspace
from apps.transactions.deal_documents import load_version_for_reader
from apps.transactions.models import TransactionDocumentVersion
from apps.user.models import User


def log_file_denial(actor: User, version_id: str, *, reason: str) -> None:
    log_event(
        "security.transaction.document_denied",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type="transaction.document_version",
            target_id=str(version_id),
        ),
        outcome=AuditEvent.Outcome.DENIED,
        reason=reason,
    )


def assert_readable_version(
    actor: User,
    version: TransactionDocumentVersion,
    *,
    allow_historical: bool = False,
) -> None:
    """Ordinary readers get the current ready version only; managers may history."""
    if not version.is_readable:
        log_file_denial(actor, str(version.public_id), reason="file_not_ready")
        raise Http404(_("No document matches that id."))

    document = version.document
    is_current = document.current_version_pk == version.pk
    if is_current:
        return

    if allow_historical and can_manage_workspace(actor, document.transaction):
        return

    log_file_denial(actor, str(version.public_id), reason="not_current")
    raise Http404(_("No document matches that id."))


def stream_version(
    request,
    version: TransactionDocumentVersion,
    *,
    as_attachment: bool = True,
) -> FileResponse:
    storage = version.file.storage
    key = version.file.name
    if not key or not storage.exists(key):
        raise Http404(_("That file is no longer stored."))
    response = FileResponse(
        storage.open(key, "rb"),
        as_attachment=as_attachment,
        filename=version.display_name or version.original_name,
        content_type=version.media_type or "application/octet-stream",
    )
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["X-Content-Type-Options"] = "nosniff"
    if not as_attachment:
        response["X-Frame-Options"] = "SAMEORIGIN"
    return response


def resolve_and_stream(
    request,
    *,
    version_public_id,
    as_attachment: bool,
    allow_historical: bool = False,
) -> FileResponse:
    actor = request.user
    try:
        version = load_version_for_reader(actor, version_public_id)
    except TransactionDocumentVersion.DoesNotExist as exc:
        log_file_denial(actor, str(version_public_id), reason="out_of_scope")
        raise Http404(_("No document matches that id.")) from exc
    assert_readable_version(actor, version, allow_historical=allow_historical)
    return stream_version(request, version, as_attachment=as_attachment)


__all__ = [
    "assert_readable_version",
    "log_file_denial",
    "resolve_and_stream",
    "stream_version",
]
