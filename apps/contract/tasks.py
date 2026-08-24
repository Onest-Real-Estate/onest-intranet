"""Background tasks for contract templates and agent-contract lifecycle."""

from __future__ import annotations

import logging

from celery import shared_task
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def generate_contract_template_preview(self, version_id: int) -> str:
    from apps.contract.models import ContractTemplateVersion
    from apps.contract.template_service import generate_preview

    version = (
        ContractTemplateVersion.objects.select_related("template")
        .filter(pk=version_id)
        .first()
    )
    if version is None:
        return "missing"

    try:
        generate_preview(version)
    except ValidationError as exc:
        version.validation_errors = (
            exc.message_dict
            if hasattr(exc, "message_dict")
            else [{"form": [str(message) for message in exc.messages]}]
        )
        version.save(update_fields=["validation_errors", "updated_at"])
        return "invalid"
    return "ready"


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def generate_contract_pdf(self, contract_id: int) -> str:
    """Stub for P1-042: validate post-issue state; do not attach artifacts yet."""
    from apps.contract.models import AgentContract
    from apps.contract.statuses import ContractStatus

    contract = AgentContract.objects.filter(pk=contract_id).first()
    if contract is None:
        return "missing"
    if contract.status not in {
        ContractStatus.SENT,
        ContractStatus.GENERATION_ERROR,
    }:
        logger.info(
            "generate_contract_pdf skipped contract_id=%s status=%s",
            contract_id,
            contract.status,
        )
        return "skipped"
    if not contract.party_snapshot or not contract.office_snapshot:
        logger.warning(
            "generate_contract_pdf missing snapshots contract_id=%s",
            contract_id,
        )
        return "invalid"
    logger.info(
        "generate_contract_pdf stubbed contract_id=%s public_id=%s",
        contract_id,
        contract.public_id,
    )
    return "stubbed"


@shared_task
def expire_due_contracts() -> int:
    """Beat-safe expiry: active contracts past ``expires_on`` become expired."""
    from apps.contract.lifecycle import expire_due_contracts as run_expire

    return run_expire()
