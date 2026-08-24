"""Background tasks for governed contract templates."""

from __future__ import annotations

from celery import shared_task
from django.core.exceptions import ValidationError


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
