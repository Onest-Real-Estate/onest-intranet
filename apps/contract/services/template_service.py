"""Governed contract-template authoring services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.contract.field_ai import field_ai_configured, suggest_fields_for_pdf
from apps.contract.field_layout import (
    assert_publishable_layout,
    normalize_field_layout,
    prefill_field_names,
)
from apps.contract.models import (
    AgentContract,
    ContractTemplate,
    ContractTemplateVersion,
)
from apps.contract.pdf_signing import fill_prefill_fields
from apps.contract.template_security import (
    MERGE_SOURCE_OPTIONS,
    inspect_template,
    seed_merge_schema_from_placeholders,
    synthetic_preview_context,
    validate_merge_schema,
)
from apps.user.models import Office, User
from apps.user.services.role_assignments import (
    get_effective_access,
    has_effective_permission,
)
from apps.web.authorization import scope_queryset_for_offices

MANAGE_PERMISSION = "contract.manage_contract_templates"
APPROVE_PERMISSION = "contract.approve_contract_templates"


@dataclass(frozen=True)
class TemplateCapabilities:
    can_manage: bool
    can_approve: bool

    def payload(self) -> dict[str, bool]:
        return {
            "canManage": self.can_manage,
            "canApprove": self.can_approve,
        }


def capabilities(actor: User) -> TemplateCapabilities:
    return TemplateCapabilities(
        can_manage=has_effective_permission(actor, MANAGE_PERMISSION),
        can_approve=has_effective_permission(actor, APPROVE_PERMISSION),
    )


def version_token(version: ContractTemplateVersion) -> str:
    return version.updated_at.isoformat() if version.updated_at else ""


def _actor_scope(actor: User) -> tuple[frozenset[int], frozenset[str], bool]:
    if getattr(actor, "is_superuser", False):
        office_ids = frozenset(Office.objects.values_list("pk", flat=True))
        region_keys = frozenset(
            Office.objects.filter(kind=Office.Kind.REGION).values_list(
                "stable_key", flat=True
            )
        )
        return office_ids, region_keys, True
    access = get_effective_access(actor)
    office_ids = frozenset(
        scope_queryset_for_offices(
            actor, Office.objects.filter(is_active=True)
        ).values_list("pk", flat=True)
    )
    return office_ids, access.region_keys, access.company_wide


def manageable_template_queryset(actor: User) -> QuerySet[ContractTemplate]:
    if not (
        getattr(actor, "is_superuser", False)
        or has_effective_permission(actor, MANAGE_PERMISSION)
        or has_effective_permission(actor, APPROVE_PERMISSION)
    ):
        return ContractTemplate.objects.none()

    queryset = ContractTemplate.objects.prefetch_related(
        "applicable_offices",
        "applicable_regions",
        "versions",
    ).select_related("active_version")
    office_ids, region_keys, company_wide = _actor_scope(actor)
    if company_wide:
        return queryset
    if not office_ids and not region_keys:
        return queryset.none()
    return queryset.filter(
        Q(company_wide=True)
        | Q(applicable_offices__pk__in=sorted(office_ids))
        | Q(applicable_regions__stable_key__in=sorted(region_keys))
    ).distinct()


def manageable_version_queryset(actor: User) -> QuerySet[ContractTemplateVersion]:
    return (
        ContractTemplateVersion.objects.select_related(
            "template",
            "template__active_version",
            "created_by",
            "approved_by",
            "retired_by",
            "supersedes",
        )
        .filter(template__in=manageable_template_queryset(actor))
        .order_by("template__name", "-created_at")
    )


def _ensure_manage(actor: User) -> None:
    if getattr(actor, "is_superuser", False):
        return
    if not has_effective_permission(actor, MANAGE_PERMISSION):
        raise PermissionDenied("You cannot manage contract templates.")


def _ensure_approve(actor: User) -> None:
    if getattr(actor, "is_superuser", False):
        return
    if not has_effective_permission(actor, APPROVE_PERMISSION):
        raise PermissionDenied("You cannot approve or activate contract templates.")


def _assert_in_scope(
    actor: User,
    *,
    company_wide: bool,
    applicable_offices: list[Office] | None,
    applicable_regions: list[Office] | None,
) -> None:
    office_ids, region_keys, actor_company_wide = _actor_scope(actor)
    if actor_company_wide:
        return
    if company_wide:
        raise ValidationError(
            {
                "company_wide": (
                    "Only brokerage-wide administrators may create company-wide "
                    "templates."
                )
            }
        )
    offices = applicable_offices or []
    regions = applicable_regions or []
    if any(office.pk not in office_ids for office in offices):
        raise ValidationError(
            {
                "applicable_offices": (
                    "One or more offices are outside your administrative scope."
                )
            }
        )
    if any(region.stable_key not in region_keys for region in regions):
        raise ValidationError(
            {
                "applicable_regions": (
                    "One or more regions are outside your administrative scope."
                )
            }
        )


def create_template_family(
    actor: User,
    *,
    stable_key: str,
    name: str,
    description: str = "",
    jurisdiction_state_codes: list[str] | None = None,
    company_wide: bool = False,
    applicable_offices: list[Office] | None = None,
    applicable_regions: list[Office] | None = None,
    effective_from=None,
    effective_until=None,
) -> ContractTemplate:
    _ensure_manage(actor)
    _assert_in_scope(
        actor,
        company_wide=company_wide,
        applicable_offices=applicable_offices,
        applicable_regions=applicable_regions,
    )
    template = ContractTemplate(
        stable_key=stable_key,
        name=name,
        description=description,
        jurisdiction_state_codes=list(jurisdiction_state_codes or []),
        company_wide=company_wide,
        effective_from=effective_from,
        effective_until=effective_until,
        created_by=actor,
        status=ContractTemplate.Status.DRAFT,
    )
    template.full_clean()
    with transaction.atomic():
        template.save()
        if applicable_offices:
            template.applicable_offices.set(applicable_offices)
        if applicable_regions:
            template.applicable_regions.set(applicable_regions)
        log_event(
            "contract_template.family.created",
            actor=actor_from_user(actor),
            target=AuditTarget(
                target_type=ContractTemplate._meta.label_lower,
                target_id=str(template.public_id),
                target_label=template.stable_key,
                target_snapshot={"status": template.status, "name": template.name},
            ),
            outcome=AuditEvent.Outcome.SUCCESS,
            source="service",
            channel="contract",
        )
    return template


SOURCE_FETCH_SALT = "contract-source-fetch"
SOURCE_FETCH_MAX_AGE = 60 * 60  # 1 hour


def _read_version_source_bytes(version: ContractTemplateVersion) -> bytes:
    if not version.source_document:
        raise ValidationError({"source_document": ["Upload a PDF first."]})
    version.source_document.open("rb")
    try:
        data = version.source_document.read()
    finally:
        version.source_document.close()
    if not data:
        raise ValidationError({"source_document": ["Template PDF is empty."]})
    return data


def prepare_template_after_pdf_upload(
    version: ContractTemplateVersion,
    *,
    pdf_bytes: bytes | None = None,
) -> ContractTemplateVersion:
    """Reset field layout after a new blank PDF upload."""
    del pdf_bytes  # retained for call-site compatibility
    if version.status != ContractTemplateVersion.Status.DRAFT:
        raise ValidationError(
            {"form": ["Only draft versions can replace the template PDF."]}
        )
    if not version.source_document:
        raise ValidationError({"source_document": ["Upload a PDF first."]})

    version.field_layout = []
    version.extracted_placeholder_keys = []
    version.merge_schema = []
    version.save(
        update_fields=[
            "field_layout",
            "extracted_placeholder_keys",
            "merge_schema",
            "updated_at",
        ]
    )
    return version


def save_field_layout(
    actor: User,
    *,
    version: ContractTemplateVersion,
    layout: Any,
) -> ContractTemplateVersion:
    """Persist Hub field placement and reseed Prefill merge keys."""
    _ensure_manage(actor)
    if version.status != ContractTemplateVersion.Status.DRAFT:
        raise ValidationError(
            {"form": ["Only draft versions can edit field placement."]}
        )
    if not version.source_document:
        raise ValidationError({"source_document": ["Upload a PDF first."]})

    normalized = normalize_field_layout(layout)
    merge_keys = prefill_field_names(normalized)
    existing = {
        str(item.get("key", "")).strip(): item
        for item in (version.merge_schema or [])
        if isinstance(item, dict) and str(item.get("key", "")).strip()
    }
    merged: list[dict] = []
    for key in merge_keys:
        prior = existing.get(key)
        if prior is not None:
            merged.append(dict(prior))
        else:
            merged.extend(seed_merge_schema_from_placeholders([key]))

    version.field_layout = normalized
    version.extracted_placeholder_keys = merge_keys
    version.merge_schema = merged
    version.full_clean()
    version.save(
        update_fields=[
            "field_layout",
            "extracted_placeholder_keys",
            "merge_schema",
            "updated_at",
        ]
    )
    return version


def suggest_field_layout(
    actor: User,
    *,
    version: ContractTemplateVersion,
) -> list[dict]:
    """Return AI field suggestions for the draft PDF (human must accept)."""
    _ensure_manage(actor)
    if version.status != ContractTemplateVersion.Status.DRAFT:
        raise ValidationError({"form": ["Only draft versions can run field AI."]})
    if not field_ai_configured():
        raise ValidationError(
            {
                "form": [
                    "Field AI is not configured. Set CONTRACT_FIELD_AI_ENDPOINT "
                    "and CONTRACT_FIELD_AI_API_KEY."
                ]
            }
        )
    pdf_bytes = _read_version_source_bytes(version)
    return suggest_fields_for_pdf(pdf_bytes)


def _assert_publishable(version: ContractTemplateVersion) -> None:
    layout = normalize_field_layout(version.field_layout or [])
    assert_publishable_layout(layout)
    merge_keys = prefill_field_names(layout)
    version.extracted_placeholder_keys = merge_keys
    validate_merge_schema(
        list(version.merge_schema or []),
        placeholder_keys=merge_keys,
    )
    missing_sources = [
        str(item.get("key", "")).strip()
        for item in (version.merge_schema or [])
        if isinstance(item, dict)
        and str(item.get("key", "")).strip()
        and not str(item.get("source", "")).strip()
    ]
    if missing_sources:
        raise ValidationError(
            {
                "merge_schema": [
                    "Map every Prefill field to a hub source before publishing: "
                    + ", ".join(missing_sources)
                ]
            }
        )
    if not version.source_document:
        raise ValidationError({"source_document": ["Upload a PDF before publishing."]})


def create_draft_version(
    actor: User,
    *,
    template: ContractTemplate,
    version_label: str,
    display_name: str = "",
    description: str = "",
    merge_schema: list[dict] | None = None,
    supersedes: ContractTemplateVersion | None = None,
) -> ContractTemplateVersion:
    _ensure_manage(actor)
    if not manageable_template_queryset(actor).filter(pk=template.pk).exists():
        raise PermissionDenied("That template family is outside your scope.")
    version = ContractTemplateVersion(
        template=template,
        version_label=version_label,
        display_name=display_name,
        description=description,
        merge_schema=list(merge_schema or []),
        supersedes=supersedes,
        created_by=actor,
        status=ContractTemplateVersion.Status.DRAFT,
    )
    version.full_clean()
    version.save()
    log_event(
        "contract_template.version.created",
        actor=actor_from_user(actor),
        target=AuditTarget(
            target_type=ContractTemplateVersion._meta.label_lower,
            target_id=str(version.public_id),
            target_label=version.version_label,
            target_snapshot={
                "template": template.stable_key,
                "status": version.status,
                "versionLabel": version.version_label,
            },
        ),
        outcome=AuditEvent.Outcome.SUCCESS,
        source="service",
        channel="contract",
    )
    return version


def save_draft_version(
    actor: User,
    *,
    version: ContractTemplateVersion,
    expected_version: str = "",
    display_name: str,
    description: str,
    merge_schema: list[dict],
    source_upload=None,
) -> ContractTemplateVersion:
    _ensure_manage(actor)
    with transaction.atomic():
        locked = (
            ContractTemplateVersion.objects.select_for_update()
            .select_related("template")
            .get(pk=version.pk)
        )
        if version_token(locked) != (expected_version or ""):
            raise ValidationError(
                {
                    "form": [
                        "Somebody else saved this template version first. Review "
                        "the latest draft and try again."
                    ]
                }
            )
        if locked.status != ContractTemplateVersion.Status.DRAFT:
            raise ValidationError(
                {
                    "form": [
                        "Only draft versions can be edited. Create a new draft "
                        "version instead."
                    ]
                }
            )

        locked.display_name = display_name
        locked.description = description
        locked.merge_schema = list(merge_schema or [])

        if source_upload is not None:
            source_upload.seek(0)
            data = source_upload.read()
            inspection = inspect_template(
                filename=source_upload.name,
                media_type=getattr(source_upload, "content_type", ""),
                data=data,
            )
            locked.source_format = inspection.format
            locked.source_media_type = inspection.media_type
            locked.source_checksum = inspection.checksum
            locked.source_document.save(
                source_upload.name, ContentFile(data), save=False
            )
            locked.full_clean()
            locked.save()
            prepare_template_after_pdf_upload(locked, pdf_bytes=data)
            locked.refresh_from_db()
            # Keep existing merge mappings when re-uploading; Prefill keys are
            # reseeded when the Hub field layout is saved.
            if not locked.merge_schema and locked.extracted_placeholder_keys:
                locked.merge_schema = seed_merge_schema_from_placeholders(
                    locked.extracted_placeholder_keys
                )
                locked.save(update_fields=["merge_schema", "updated_at"])
            return locked

        if locked.extracted_placeholder_keys:
            validate_merge_schema(
                locked.merge_schema,
                placeholder_keys=list(locked.extracted_placeholder_keys or []),
            )

        locked.full_clean()
        locked.save()
        return locked


def generate_preview(version: ContractTemplateVersion) -> ContractTemplateVersion:
    if version.status != ContractTemplateVersion.Status.DRAFT:
        raise ValidationError({"form": ["Only draft versions can generate a preview."]})
    layout = normalize_field_layout(version.field_layout or [])
    if not layout:
        raise ValidationError(
            {"form": ["Upload a PDF and place fields in the Hub placer first."]}
        )
    assert_publishable_layout(layout)
    merge_keys = prefill_field_names(layout)
    validate_merge_schema(
        list(version.merge_schema or []),
        placeholder_keys=merge_keys,
    )
    preview_context = synthetic_preview_context(list(version.merge_schema or []))
    source_pdf = _read_version_source_bytes(version)
    try:
        preview_bytes = fill_prefill_fields(
            source_pdf, layout=layout, values=preview_context
        )
    except Exception as exc:  # noqa: BLE001
        raise ValidationError(
            {"form": ["Could not generate a Hub preview from the field layout."]}
        ) from exc

    version.preview_context = preview_context
    version.preview_generated_at = timezone.now()
    version.validation_errors = []
    version.preview_pdf.save(
        f"{version.template.stable_key}-{version.version_label}-preview.pdf",
        ContentFile(preview_bytes),
        save=False,
    )
    from apps.contract.template_security import checksum_of

    version.preview_checksum = checksum_of(preview_bytes)
    version.full_clean()
    version.save()
    return version


def publish_version(
    actor: User, *, version: ContractTemplateVersion
) -> ContractTemplateVersion:
    _ensure_approve(actor)
    with transaction.atomic():
        locked = (
            ContractTemplateVersion.objects.select_for_update()
            .select_related("template")
            .get(pk=version.pk)
        )
        if locked.status != ContractTemplateVersion.Status.DRAFT:
            raise ValidationError({"form": ["Only draft versions can be published."]})
        _assert_publishable(locked)
        if not locked.preview_pdf:
            raise ValidationError(
                {"preview_pdf": ["Generate a synthetic preview before publishing."]}
            )
        locked.status = ContractTemplateVersion.Status.PUBLISHED
        locked.published_at = timezone.now()
        locked.approved_by = actor
        locked.full_clean()
        locked.save()
        locked.template.approved_by = actor
        locked.template.approved_at = locked.published_at
        locked.template.save(update_fields=["approved_by", "approved_at", "updated_at"])
        log_event(
            "contract_template.version.published",
            actor=actor_from_user(actor),
            target=AuditTarget(
                target_type=ContractTemplateVersion._meta.label_lower,
                target_id=str(locked.public_id),
                target_label=f"{locked.template.stable_key}@{locked.version_label}",
            ),
            outcome=AuditEvent.Outcome.SUCCESS,
            source="service",
            channel="contract",
        )
    return locked


def activate_version(
    actor: User, *, version: ContractTemplateVersion
) -> ContractTemplateVersion:
    _ensure_approve(actor)
    with transaction.atomic():
        locked = (
            ContractTemplateVersion.objects.select_for_update()
            .select_related("template")
            .get(pk=version.pk)
        )
        if locked.status != ContractTemplateVersion.Status.PUBLISHED:
            raise ValidationError(
                {"form": ["Only published versions can be activated."]}
            )
        template = locked.template
        previous = template.active_version
        template.active_version = locked
        template.status = ContractTemplate.Status.ACTIVE
        template.approved_by = actor
        template.approved_at = timezone.now()
        template.full_clean()
        template.save()
        if (
            previous
            and previous.pk != locked.pk
            and previous.status == previous.Status.PUBLISHED
        ):
            previous.status = ContractTemplateVersion.Status.SUPERSEDED
            previous.retired_by = actor
            previous.retired_at = timezone.now()
            previous.save(
                update_fields=["status", "retired_by", "retired_at", "updated_at"]
            )
        log_event(
            "contract_template.version.activated",
            actor=actor_from_user(actor),
            target=AuditTarget(
                target_type=ContractTemplateVersion._meta.label_lower,
                target_id=str(locked.public_id),
                target_label=f"{locked.template.stable_key}@{locked.version_label}",
            ),
            metadata={
                "previousActiveVersionId": str(previous.public_id) if previous else ""
            },
            outcome=AuditEvent.Outcome.SUCCESS,
            source="service",
            channel="contract",
        )
    return locked


def retire_version(
    actor: User, *, version: ContractTemplateVersion
) -> ContractTemplateVersion:
    _ensure_approve(actor)
    with transaction.atomic():
        locked = (
            ContractTemplateVersion.objects.select_for_update()
            .select_related("template")
            .get(pk=version.pk)
        )
        if AgentContract.objects.filter(template_version=locked).exists():
            raise ValidationError(
                {
                    "form": [
                        "Referenced template versions cannot be retired "
                        "destructively in place."
                    ]
                }
            )
        locked.status = ContractTemplateVersion.Status.RETIRED
        locked.retired_by = actor
        locked.retired_at = timezone.now()
        locked.full_clean()
        locked.save()
        if locked.template.active_version_id == locked.pk:
            locked.template.active_version = None
            locked.template.status = ContractTemplate.Status.RETIRED
            locked.template.retired_by = actor
            locked.template.retired_at = locked.retired_at
            locked.template.save()
        log_event(
            "contract_template.version.retired",
            actor=actor_from_user(actor),
            target=AuditTarget(
                target_type=ContractTemplateVersion._meta.label_lower,
                target_id=str(locked.public_id),
                target_label=f"{locked.template.stable_key}@{locked.version_label}",
            ),
            outcome=AuditEvent.Outcome.SUCCESS,
            source="service",
            channel="contract",
        )
    return locked


def _workspace_version_pk(template: ContractTemplate) -> int | None:
    """Version to open from the family list: latest draft, else active, else newest."""
    # Query the version table directly — reverse managers are invisible to ty.
    versions = list(
        ContractTemplateVersion.objects.filter(template=template).order_by(
            "-created_at", "-pk"
        )
    )
    draft = next(
        (
            version
            for version in sorted(
                versions, key=lambda item: (item.created_at, item.pk), reverse=True
            )
            if version.status == ContractTemplateVersion.Status.DRAFT
        ),
        None,
    )
    if draft is not None:
        return draft.pk
    if template.active_version_id is not None:
        return template.active_version_id
    if not versions:
        return None
    newest = max(versions, key=lambda item: (item.created_at, item.pk))
    return newest.pk


def serialize_template_row(template: ContractTemplate) -> dict[str, Any]:
    return {
        "publicId": str(template.public_id),
        "stableKey": template.stable_key,
        "name": template.name,
        "description": template.description,
        "status": template.status,
        "jurisdictionStateCodes": list(template.jurisdiction_state_codes or []),
        "companyWide": template.company_wide,
        "effectiveFrom": template.effective_from.isoformat()
        if template.effective_from
        else "",
        "effectiveUntil": template.effective_until.isoformat()
        if template.effective_until
        else "",
        "activeVersionPk": template.active_version_id,
        "activeVersionId": (
            str(template.active_version.public_id)
            if template.active_version is not None
            else None
        ),
        "workspaceVersionPk": _workspace_version_pk(template),
    }


def serialize_version_detail(version: ContractTemplateVersion) -> dict[str, Any]:
    has_source = bool(version.source_document)
    return {
        "id": version.pk,
        "publicId": str(version.public_id),
        "templatePublicId": str(version.template.public_id),
        "versionLabel": version.version_label,
        "displayName": version.display_name,
        "description": version.description,
        "status": version.status,
        "sourceFormat": version.source_format,
        "sourceMediaType": version.source_media_type,
        "sourceChecksum": version.source_checksum,
        "sourcePdfUrl": (
            f"/operations/contract-templates/templates/{version.pk}/source.pdf"
            if has_source
            else ""
        ),
        "previewUrl": (
            f"/operations/contract-templates/templates/{version.pk}/preview.pdf"
            if version.preview_pdf
            else None
        ),
        "fieldLayout": list(version.field_layout or []),
        "fieldAiConfigured": field_ai_configured(),
        "mergeSourceOptions": list(MERGE_SOURCE_OPTIONS),
        "placeholderKeys": list(version.extracted_placeholder_keys or []),
        "mergeSchema": list(version.merge_schema or []),
        "previewChecksum": version.preview_checksum,
        "previewGeneratedAt": version.preview_generated_at.isoformat()
        if version.preview_generated_at
        else None,
        "validationErrors": list(version.validation_errors or []),
        "publishedAt": version.published_at.isoformat()
        if version.published_at
        else None,
        "retiredAt": version.retired_at.isoformat() if version.retired_at else None,
        "contractsUsingVersion": AgentContract.objects.filter(
            template_version=version
        ).count(),
        "version": version_token(version),
    }
