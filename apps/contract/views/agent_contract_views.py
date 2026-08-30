"""HTTP surface for agent-contract administration (P1-039)."""

from __future__ import annotations

import json
import uuid
from datetime import date
from typing import Any, cast

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import FileResponse, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from inertia import inertia, render

from apps.contract.administration import (
    UNSET,
    agreement_preview_payload,
    applicable_template_versions,
    capabilities,
    commercial_preview,
    create_draft_with_applicability,
    issue_contract,
    search_contract_recipients,
    serialize_template_option,
    update_draft_contract,
    workspace_payload,
)
from apps.contract.artifact_delivery import stream_contract_artifact
from apps.contract.change_kinds import ContractChangeKind
from apps.contract.lifecycle import (
    ConfirmationRequired,
    StaleContractVersion,
    TransitionRefused,
    transition,
)
from apps.contract.models import AgentContract, ContractTemplateVersion
from apps.contract.services import scoped_contract_queryset, serialize_contract
from apps.contract.signed_pdf_generation import integrity_payload
from apps.contract.statuses import contract_status_options
from apps.contract.versioning import (
    create_amendment_draft,
    create_replacement_draft,
)
from apps.user.models import Office, User
from apps.web.authorization import enforce_policy
from apps.web.contracts import empty_validation_errors, list_response
from apps.web.flash import set_flash

INDEX_PAGE = "AgentContractAdministration"
WORKSPACE_PAGE = "AgentContractWorkspace"
NEW_PAGE = "AgentContractNew"


def _validation_payload(exc: ValidationError) -> dict[str, Any]:
    if hasattr(exc, "message_dict"):
        fields = {
            key: [str(message) for message in messages]
            for key, messages in exc.message_dict.items()
        }
        form_messages = fields.pop("__all__", [])
        return {"fields": fields, "form": form_messages}
    return {"fields": {}, "form": [str(message) for message in exc.messages]}


def _actor(request: HttpRequest) -> User:
    return cast(User, request.user)


def _target(request: HttpRequest, public_id: uuid.UUID) -> AgentContract:
    return get_object_or_404(
        scoped_contract_queryset(_actor(request)), public_id=public_id
    )


def _page(request: HttpRequest) -> int:
    try:
        return max(1, int(request.GET.get("page", "1")))
    except ValueError:
        return 1


def index_props(actor: User, *, params) -> dict[str, Any]:
    query = (params.get("q") or "").strip()
    status = (params.get("status") or "").strip()
    rows = scoped_contract_queryset(actor).select_related(
        "recipient", "office", "template_version", "template_version__template"
    )
    if query:
        rows = rows.filter(
            Q(recipient__email__icontains=query)
            | Q(recipient__first_name__icontains=query)
            | Q(recipient__last_name__icontains=query)
            | Q(recipient__display_name__icontains=query)
            | Q(public_id__icontains=query)
        )
    if status:
        rows = rows.filter(status=status)
    total = rows.count()
    page = _page_from_params(params)
    page_size = 20
    start = (page - 1) * page_size
    items = [
        {
            **serialize_contract(actor, contract),
            "recipientName": contract.recipient.preferred_display_name(),
            "recipientEmail": contract.recipient.email,
            "officeName": contract.office.name,
            "templateLabel": (
                (
                    contract.template_version.display_name
                    or contract.template_version.template.name
                )
                if contract.template_version is not None
                else ""
            ),
        }
        for contract in rows.order_by("-updated_at")[start : start + page_size]
    ]
    return {
        "contracts": list_response(
            items,
            page=page,
            page_size=page_size,
            total_items=total,
            filters={"q": query, "status": status},
            sort_key="updated_at",
        ),
        "capabilities": capabilities(actor),
        "statusOptions": contract_status_options(),
        "errors": empty_validation_errors(),
    }


def _page_from_params(params) -> int:
    try:
        return max(1, int(params.get("page", "1")))
    except ValueError:
        return 1


@enforce_policy("agent_contract_admin")
@require_GET
@inertia(INDEX_PAGE)
def agent_contract_index(request: HttpRequest):
    return index_props(_actor(request), params=request.GET)


@enforce_policy("agent_contract_manage")
@require_GET
@inertia(NEW_PAGE)
def agent_contract_new(request: HttpRequest):
    actor = _actor(request)
    return {
        "capabilities": capabilities(actor),
        "errors": empty_validation_errors(),
        "draft": {
            "effectiveOn": date.today().isoformat(),
            "agentSplitPercent": "70",
            "officeSplitPercent": "30",
        },
    }


@enforce_policy("agent_contract_manage")
@require_POST
def agent_contract_create(request: HttpRequest):
    actor = _actor(request)
    try:
        recipient_id = int(request.POST.get("recipient_id") or "0")
    except ValueError:
        recipient_id = 0
    recipient = get_object_or_404(User, pk=recipient_id)
    template_raw = (request.POST.get("template_version_id") or "").strip()
    template_version = None
    if template_raw:
        template_version = get_object_or_404(
            ContractTemplateVersion, pk=int(template_raw)
        )
    office_raw = (request.POST.get("office_id") or "").strip()
    office = None
    if office_raw:
        office = get_object_or_404(Office, pk=int(office_raw))

    try:
        contract = create_draft_with_applicability(
            actor,
            recipient=recipient,
            office=office,
            effective_on=_parse_date(request.POST.get("effective_on")),
            expires_on=_parse_date(request.POST.get("expires_on"), allow_empty=True),
            template_version=template_version,
            agent_split_percent=request.POST.get("agent_split_percent") or None,
            office_split_percent=request.POST.get("office_split_percent") or None,
            transaction_fee_amount=request.POST.get("transaction_fee_amount") or None,
            transaction_fee_percent=request.POST.get("transaction_fee_percent") or None,
            annual_cap_amount=request.POST.get("annual_cap_amount") or None,
            special_arrangements=request.POST.get("special_arrangements") or "",
            internal_notes=request.POST.get("internal_notes") or "",
        )
    except (ValidationError, PermissionDenied) as exc:
        return _render_new_error(request, exc)

    return redirect("agent_contract_workspace", public_id=contract.public_id)


def _render_new_error(request: HttpRequest, exc) -> HttpResponse:
    actor = _actor(request)
    errors = (
        _validation_payload(exc)
        if isinstance(exc, ValidationError)
        else {"fields": {}, "form": [str(exc)]}
    )
    response = render(
        request,
        NEW_PAGE,
        {
            "capabilities": capabilities(actor),
            "errors": errors,
            "draft": dict(request.POST),
        },
    )
    response.status_code = 422
    return response


@enforce_policy("agent_contract_workspace")
@require_GET
@inertia(WORKSPACE_PAGE)
def agent_contract_workspace(request: HttpRequest, public_id: uuid.UUID):
    actor = _actor(request)
    contract = _target(request, public_id)
    return {
        **workspace_payload(actor, contract),
        "errors": empty_validation_errors(),
        "agreementPreview": None,
    }


@enforce_policy("agent_contract_manage")
@require_POST
def agent_contract_update(request: HttpRequest, public_id: uuid.UUID):
    actor = _actor(request)
    contract = _target(request, public_id)
    template_raw = (request.POST.get("template_version_id") or "").strip()
    template_version = UNSET
    if "template_version_id" in request.POST:
        if template_raw:
            template_version = get_object_or_404(
                ContractTemplateVersion, pk=int(template_raw)
            )
        else:
            template_version = None
    office_raw = (request.POST.get("office_id") or "").strip()
    office = None
    if office_raw:
        office = get_object_or_404(Office, pk=int(office_raw))

    mentor_payee = UNSET
    if "mentor_payee_id" in request.POST:
        raw = (request.POST.get("mentor_payee_id") or "").strip()
        mentor_payee = get_object_or_404(User, pk=int(raw)) if raw else None
    referral_payee = UNSET
    if "referral_payee_id" in request.POST:
        raw = (request.POST.get("referral_payee_id") or "").strip()
        referral_payee = get_object_or_404(User, pk=int(raw)) if raw else None

    addenda_raw = (request.POST.get("addenda_references") or "").strip()
    addenda = None
    if addenda_raw:
        try:
            parsed = json.loads(addenda_raw)
            addenda = parsed if isinstance(parsed, list) else [addenda_raw]
        except json.JSONDecodeError:
            addenda = [
                line.strip() for line in addenda_raw.splitlines() if line.strip()
            ]

    try:
        update_draft_contract(
            actor,
            contract,
            expected_version=request.POST.get("expected_version") or "",
            office=office,
            effective_on=_parse_date(request.POST.get("effective_on")),
            expires_on=_parse_date(request.POST.get("expires_on"), allow_empty=True)
            if "expires_on" in request.POST
            else UNSET,
            template_version=template_version,
            agent_split_percent=request.POST.get("agent_split_percent") or None,
            office_split_percent=request.POST.get("office_split_percent") or None,
            transaction_fee_amount=request.POST.get("transaction_fee_amount") or None,
            transaction_fee_percent=request.POST.get("transaction_fee_percent") or None,
            annual_cap_amount=request.POST.get("annual_cap_amount") or None,
            mentor_percent=request.POST.get("mentor_percent") or None,
            mentor_fixed_amount=request.POST.get("mentor_fixed_amount") or None,
            mentor_cap_amount=request.POST.get("mentor_cap_amount") or None,
            mentor_basis=request.POST.get("mentor_basis") or "",
            mentor_payee=mentor_payee,
            mentor_notes=request.POST.get("mentor_notes") or "",
            referral_percent=request.POST.get("referral_percent") or None,
            referral_fixed_amount=request.POST.get("referral_fixed_amount") or None,
            referral_cap_amount=request.POST.get("referral_cap_amount") or None,
            referral_basis=request.POST.get("referral_basis") or "",
            referral_payee=referral_payee,
            referral_notes=request.POST.get("referral_notes") or "",
            special_arrangements=request.POST.get("special_arrangements") or "",
            addenda_references=addenda,
            internal_notes=request.POST.get("internal_notes")
            if "internal_notes" in request.POST
            else None,
            change_summary=request.POST.get("change_summary")
            if "change_summary" in request.POST
            else None,
        )
    except (ValidationError, PermissionDenied, StaleContractVersion) as exc:
        return _render_workspace_error(request, contract, exc)

    set_flash(request, level="success", message="Draft saved")
    return redirect("agent_contract_workspace", public_id=contract.public_id)


@enforce_policy("agent_contract_manage")
@require_POST
def agent_contract_create_amendment(request: HttpRequest, public_id: uuid.UUID):
    actor = _actor(request)
    base = _target(request, public_id)
    kind = (request.POST.get("change_kind") or ContractChangeKind.AMENDMENT).strip()
    if kind not in {
        ContractChangeKind.AMENDMENT,
        ContractChangeKind.ADDENDUM,
    }:
        kind = ContractChangeKind.AMENDMENT
    try:
        draft = create_amendment_draft(
            actor,
            base,
            change_kind=kind,
            change_summary=request.POST.get("change_summary") or "",
            effective_on=_parse_date(
                request.POST.get("effective_on"), allow_empty=True
            ),
        )
    except (ValidationError, PermissionDenied) as exc:
        return _render_workspace_error(request, base, exc)

    set_flash(
        request,
        level="success",
        message="Amendment draft created — edit terms on the new version only.",
    )
    return redirect("agent_contract_workspace", public_id=draft.public_id)


@enforce_policy("agent_contract_manage")
@require_POST
def agent_contract_create_replacement(request: HttpRequest, public_id: uuid.UUID):
    actor = _actor(request)
    base = _target(request, public_id)
    try:
        draft = create_replacement_draft(
            actor,
            base,
            change_summary=request.POST.get("change_summary") or "",
            effective_on=_parse_date(
                request.POST.get("effective_on"), allow_empty=True
            ),
        )
    except (ValidationError, PermissionDenied) as exc:
        return _render_workspace_error(request, base, exc)

    set_flash(
        request,
        level="success",
        message="Replacement draft created — the signed version was not edited.",
    )
    return redirect("agent_contract_workspace", public_id=draft.public_id)


@enforce_policy("agent_contract_manage")
@require_POST
def agent_contract_lifecycle(request: HttpRequest, public_id: uuid.UUID):
    actor = _actor(request)
    contract = _target(request, public_id)
    action = (request.POST.get("action") or "").strip()
    expected = request.POST.get("expected_version") or ""
    confirmed = request.POST.get("confirmed") in {"1", "true", "on", "yes"}
    idempotency_key = (request.POST.get("idempotency_key") or "").strip()

    try:
        if action == "issue":
            issue_contract(
                actor,
                contract,
                expected_version=expected,
                confirmed=confirmed,
                idempotency_key=idempotency_key,
            )
        else:
            transition(
                actor=actor,
                contract=contract,
                action=action,
                expected_version=expected,
                confirmed=confirmed,
                idempotency_key=idempotency_key,
            )
    except (
        ValidationError,
        PermissionDenied,
        StaleContractVersion,
        TransitionRefused,
        ConfirmationRequired,
    ) as exc:
        return _render_workspace_error(request, contract, exc)

    labels = {
        "submit_for_review": "Submitted for review",
        "reopen": "Draft reopened",
        "issue": "Contract issued",
        "activate": "Contract activated",
        "supersede": "Contract superseded",
        "retry_generation": "PDF generation retried",
        "terminate": "Contract terminated",
    }
    set_flash(
        request,
        level="success",
        message=labels.get(action, "Lifecycle update saved"),
    )
    return redirect("agent_contract_workspace", public_id=public_id)


@enforce_policy("agent_contract_manage")
@require_GET
def agent_contract_recipient_search(request: HttpRequest):
    actor = _actor(request)
    results = search_contract_recipients(actor, request.GET.get("q") or "")
    return JsonResponse({"results": results})


@enforce_policy("agent_contract_manage")
@require_GET
def agent_contract_template_options(request: HttpRequest):
    actor = _actor(request)
    try:
        office_id = int(request.GET.get("office_id") or "0")
    except ValueError:
        office_id = 0
    office = get_object_or_404(Office, pk=office_id)
    effective = _parse_date(request.GET.get("effective_on") or date.today().isoformat())
    assert effective is not None
    # Scope: office must be in actor administration scope via a dummy check
    from apps.contract.services import _office_in_scope
    from apps.user.services.agent_administration import administration_scope

    if not _office_in_scope(office, administration_scope(actor)):
        raise PermissionDenied("Office outside scope.")
    options = [
        serialize_template_option(v)
        for v in applicable_template_versions(office, effective)
    ]
    return JsonResponse({"results": options})


@enforce_policy("agent_contract_manage")
@require_http_methods(["GET", "POST"])
def agent_contract_validate(request: HttpRequest, public_id: uuid.UUID):
    actor = _actor(request)
    contract = _target(request, public_id)
    gross = (
        request.GET.get("gross_commission")
        or request.POST.get("gross_commission")
        or "10000"
    )
    try:
        payload = commercial_preview(actor, contract, gross_commission=gross)
    except (ValidationError, PermissionDenied) as exc:
        return JsonResponse({"error": str(exc)}, status=422)
    return JsonResponse(payload)


@enforce_policy("agent_contract_manage")
@require_http_methods(["GET", "POST"])
@inertia(WORKSPACE_PAGE)
def agent_contract_preview(request: HttpRequest, public_id: uuid.UUID):
    actor = _actor(request)
    contract = _target(request, public_id)
    try:
        preview = agreement_preview_payload(actor, contract)
    except (ValidationError, PermissionDenied) as exc:
        return {
            **workspace_payload(actor, contract),
            "errors": _validation_payload(exc)
            if isinstance(exc, ValidationError)
            else {"fields": {}, "form": [str(exc)]},
            "agreementPreview": {"status": "error", "message": str(exc)},
        }
    return {
        **workspace_payload(actor, contract),
        "errors": empty_validation_errors(),
        "agreementPreview": preview,
    }


@enforce_policy("agent_contract_artifact_download")
@require_GET
def agent_contract_artifact_download(
    request: HttpRequest,
    public_id: uuid.UUID,
    artifact_public_id: uuid.UUID,
) -> FileResponse:
    return stream_contract_artifact(
        _actor(request),
        contract_public_id=public_id,
        artifact_public_id=artifact_public_id,
    )


@enforce_policy("agent_contract_signed_pdf_verify")
@require_GET
def agent_contract_signed_pdf_verify(
    request: HttpRequest,
    public_id: uuid.UUID,
) -> JsonResponse:
    """Checksum / finalization facts for ops — no PDF body."""
    contract = _target(request, public_id)
    payload = integrity_payload(contract)
    if payload is None:
        return JsonResponse({"error": "no_signature"}, status=404)
    return JsonResponse(payload)


def _render_workspace_error(
    request: HttpRequest, contract: AgentContract, exc
) -> HttpResponse:
    actor = _actor(request)
    contract.refresh_from_db()
    if isinstance(exc, (StaleContractVersion, TransitionRefused, ConfirmationRequired)):
        errors = {"fields": {}, "form": [exc.message]}
    elif isinstance(exc, ValidationError):
        errors = _validation_payload(exc)
    else:
        errors = {"fields": {}, "form": [str(exc)]}
    response = render(
        request,
        WORKSPACE_PAGE,
        {
            **workspace_payload(actor, contract),
            "errors": errors,
            "agreementPreview": None,
        },
    )
    response.status_code = 409 if isinstance(exc, StaleContractVersion) else 422
    return response


def _parse_date(raw: str | None, *, allow_empty: bool = False) -> date | None:
    value = (raw or "").strip()
    if not value:
        if allow_empty:
            return None
        raise ValidationError({"effective_on": "Enter an effective date."})
    return date.fromisoformat(value)
