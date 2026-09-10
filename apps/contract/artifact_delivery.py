"""Authorized streaming of protected contract artifacts."""

from __future__ import annotations

from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.contract.models import AgentContract, ContractArtifact
from apps.contract.services import accessible_contract_queryset
from apps.user.models import User


def stream_contract_artifact(
    actor: User,
    *,
    contract_public_id,
    artifact_public_id,
    as_attachment: bool = True,
    queryset=None,
) -> FileResponse:
    """Stream one artifact after re-checking contract access policy.

    Never issues a durable/presigned URL. Object keys are not accepted from the
    client — only public ids resolved through the accessible queryset.

    ``as_attachment=False`` streams for in-page/new-tab preview (inline
    Content-Disposition) with same-origin framing allowed.
    """
    scope = queryset if queryset is not None else accessible_contract_queryset(actor)
    contract = get_object_or_404(scope, public_id=contract_public_id)
    artifact = (
        ContractArtifact.objects.filter(
            public_id=artifact_public_id,
            contract_id=contract.pk,
        )
        .select_related("contract")
        .first()
    )
    if artifact is None or not artifact.file:
        raise Http404

    # Only the current generated/signed pointers (or historical artifacts on
    # this contract) are readable — the queryset already scoped the contract.
    storage = artifact.file.storage
    key = artifact.file.name
    if not key or not storage.exists(key):
        raise Http404

    log_event(
        "contract.artifact.downloaded",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=ContractArtifact._meta.label_lower,
            target_id=str(artifact.public_id),
            target_label=artifact.display_name,
            target_snapshot={
                "contract_id": str(contract.public_id),
                "kind": artifact.kind,
            },
        ),
        outcome=AuditEvent.Outcome.SUCCESS,
        source="view",
        channel="contract",
        office_id=getattr(contract.office, "stable_key", "") or "",
        metadata={
            "kind": artifact.kind,
            "disposition": "attachment" if as_attachment else "inline",
        },
    )

    response = FileResponse(
        storage.open(key, "rb"),
        as_attachment=as_attachment,
        filename=artifact.display_name,
        content_type=artifact.media_type or "application/octet-stream",
    )
    response["Cache-Control"] = "private, no-store, max-age=0"
    response["X-Content-Type-Options"] = "nosniff"
    if not as_attachment:
        # Allow same-origin iframe preview; default middleware is DENY.
        response["X-Frame-Options"] = "SAMEORIGIN"
    return response


def _generated_pdf_url(contract: AgentContract, *, route_name: str) -> str | None:
    from django.urls import reverse

    if not contract.generated_pdf_id:
        return None
    artifact = contract.generated_pdf
    if artifact is None:
        return None
    return reverse(
        route_name,
        kwargs={
            "public_id": contract.public_id,
            "artifact_public_id": artifact.public_id,
        },
    )


def generated_pdf_download_url(contract: AgentContract) -> str | None:
    return _generated_pdf_url(contract, route_name="agent_contract_artifact_download")


def generated_pdf_preview_url(contract: AgentContract) -> str | None:
    """Inline stream URL for same-origin iframe / new-tab preview."""
    return _generated_pdf_url(contract, route_name="agent_contract_artifact_preview")
