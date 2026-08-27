"""Governed contract-template authoring services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.service import AuditTarget, actor_from_user, log_event
from apps.contract.docuseal_client import (
    DocuSealError,
    DocuSealNotConfigured,
    DocuSealTemplate,
    agent_submitter_payload,
    build_builder_token,
    create_submission,
    docuseal_embeds_available,
    download_submission_documents,
    embed_host,
    embed_origin,
    embed_protocol,
    get_template,
    is_docuseal_builder_configured,
    is_docuseal_configured,
    prefill_submitter_payload,
)
from apps.contract.models import (
    AgentContract,
    ContractTemplate,
    ContractTemplateVersion,
)
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


SOURCE_FETCH_SALT = "contract-docuseal-source"
SOURCE_FETCH_MAX_AGE = 60 * 60  # 1 hour


def _docuseal_external_id(version: ContractTemplateVersion) -> str:
    if version.docuseal_external_id:
        return version.docuseal_external_id
    return f"contract-template-version-{version.public_id}"


def _source_signer() -> TimestampSigner:
    return TimestampSigner(salt=SOURCE_FETCH_SALT)


def source_fetch_token(version: ContractTemplateVersion) -> str:
    return _source_signer().sign(str(version.public_id))


def resolve_source_fetch_token(token: str) -> ContractTemplateVersion:
    try:
        public_id = _source_signer().unsign(token, max_age=SOURCE_FETCH_MAX_AGE)
    except SignatureExpired as exc:
        raise ValidationError({"form": ["Source download link expired."]}) from exc
    except BadSignature as exc:
        raise ValidationError({"form": ["Invalid source download link."]}) from exc
    version = ContractTemplateVersion.objects.filter(public_id=public_id).first()
    if version is None or not version.source_document:
        raise ValidationError({"form": ["Template source is not available."]})
    return version


def document_fetch_base_url() -> str:
    configured = (getattr(settings, "DOCUSEAL_DOCUMENT_FETCH_BASE", "") or "").strip()
    if configured:
        return configured.rstrip("/")
    # Local runserver / host-side DocuSeal: browser-reachable Django.
    return "http://localhost:8000"


def source_document_fetch_url(version: ContractTemplateVersion) -> str:
    token = source_fetch_token(version)
    return (
        f"{document_fetch_base_url()}"
        f"/operations/contract-templates/docuseal-source/{token}"
    )


def ensure_docuseal_template(
    version: ContractTemplateVersion,
    *,
    pdf_bytes: bytes | None = None,
) -> ContractTemplateVersion:
    """Bind a stable DocuSeal external_id after a PDF upload.

    Open-source DocuSeal blocks ``POST /templates/pdf`` (Pro). The template is
    created when the admin opens the embedded builder JWT (document_urls or
    in-builder upload) and saves.
    """
    del pdf_bytes  # retained for call-site compatibility
    if version.status != ContractTemplateVersion.Status.DRAFT:
        raise ValidationError(
            {"form": ["Only draft versions can sync a DocuSeal template."]}
        )
    if not version.source_document:
        raise ValidationError({"source_document": ["Upload a PDF first."]})
    if not is_docuseal_builder_configured():
        raise ValidationError(
            {
                "form": [
                    "DocuSeal builder is not configured. Set DOCUSEAL_API_KEY, "
                    "DOCUSEAL_BASE_URL, and DOCUSEAL_USER_EMAIL."
                ]
            }
        )

    external_id = _docuseal_external_id(version)
    version.docuseal_external_id = external_id
    # New PDF means the remote DocuSeal documents must be re-bound via builder.
    version.docuseal_template_id = None
    version.save(
        update_fields=[
            "docuseal_external_id",
            "docuseal_template_id",
            "updated_at",
        ]
    )
    return version


def bind_docuseal_template_id(
    actor: User,
    *,
    version: ContractTemplateVersion,
    template_id: int,
) -> ContractTemplateVersion:
    """Persist the DocuSeal template id returned by the builder ``onSave``."""
    _ensure_manage(actor)
    if version.status != ContractTemplateVersion.Status.DRAFT:
        raise ValidationError(
            {"form": ["Only draft versions can bind a DocuSeal template."]}
        )
    if template_id < 1:
        raise ValidationError({"form": ["Invalid DocuSeal template id."]})
    version.docuseal_template_id = int(template_id)
    version.docuseal_external_id = _docuseal_external_id(version)
    version.save(
        update_fields=["docuseal_template_id", "docuseal_external_id", "updated_at"]
    )
    return version


def sync_docuseal_fields(version: ContractTemplateVersion) -> ContractTemplateVersion:
    """Pull field names from DocuSeal into placeholder keys / merge schema."""
    if not version.docuseal_template_id:
        raise ValidationError(
            {"form": ["Create the DocuSeal template before syncing fields."]}
        )
    try:
        remote = get_template(int(version.docuseal_template_id))
    except DocuSealNotConfigured as exc:
        raise ValidationError({"form": ["DocuSeal is not configured."]}) from exc
    except DocuSealError as exc:
        raise ValidationError(
            {"form": ["Could not load the DocuSeal template fields."]}
        ) from exc

    return apply_docuseal_template_fields(version, remote)


def apply_docuseal_template_fields(
    version: ContractTemplateVersion,
    remote: DocuSealTemplate,
) -> ContractTemplateVersion:
    merge_keys = list(remote.merge_field_names)
    version.extracted_placeholder_keys = merge_keys
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
    version.merge_schema = merged
    version.full_clean()
    version.save(
        update_fields=[
            "extracted_placeholder_keys",
            "merge_schema",
            "updated_at",
        ]
    )
    return version


def builder_token_for_version(version: ContractTemplateVersion) -> dict[str, str]:
    """Mint a builder JWT for a draft version with an uploaded PDF."""
    if not version.source_document and not version.docuseal_template_id:
        raise ValidationError(
            {"form": ["Upload a PDF so DocuSeal can open the builder."]}
        )
    if not is_docuseal_builder_configured():
        raise ValidationError({"form": ["DocuSeal builder is not configured."]})

    name = (
        version.display_name or f"{version.template.name} {version.version_label}"
    ).strip()
    external_id = _docuseal_external_id(version)
    document_urls: list[str] | None = None
    template_id = (
        int(version.docuseal_template_id) if version.docuseal_template_id else None
    )
    if template_id is None and version.source_document:
        document_urls = [source_document_fetch_url(version)]

    try:
        token = build_builder_token(
            template_id=template_id,
            external_id=external_id,
            name=name,
            document_urls=document_urls,
        )
    except DocuSealNotConfigured as exc:
        raise ValidationError(
            {"form": ["DocuSeal builder is not configured."]}
        ) from exc
    return {
        "token": token,
        "host": embed_host(),
        "protocol": embed_protocol(),
        "templateId": str(template_id or ""),
    }


def _assert_publishable(version: ContractTemplateVersion) -> None:
    if not version.docuseal_template_id:
        raise ValidationError({"form": ["Link a DocuSeal template before publishing."]})
    try:
        remote = get_template(int(version.docuseal_template_id))
    except DocuSealError as exc:
        raise ValidationError(
            {"form": ["Could not verify the DocuSeal template before publishing."]}
        ) from exc
    except DocuSealNotConfigured as exc:
        raise ValidationError({"form": ["DocuSeal is not configured."]}) from exc

    if not remote.has_agent_signature:
        raise ValidationError(
            {
                "form": [
                    "Add at least one Agent signature field in the DocuSeal "
                    "builder before publishing."
                ]
            }
        )
    merge_keys = list(remote.merge_field_names)
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
                    "Map every DocuSeal field to a hub source before publishing: "
                    + ", ".join(missing_sources)
                ]
            }
        )


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
            ensure_docuseal_template(locked, pdf_bytes=data)
            locked.refresh_from_db()
            # Keep existing merge mappings when re-uploading; field sync comes
            # from DocuSeal after the builder places fields.
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
    if not version.docuseal_template_id:
        raise ValidationError(
            {"form": ["Upload a PDF and open the DocuSeal builder first."]}
        )

    sync_docuseal_fields(version)
    version.refresh_from_db()
    validate_merge_schema(
        list(version.merge_schema or []),
        placeholder_keys=list(version.extracted_placeholder_keys or []),
    )
    preview_context = synthetic_preview_context(list(version.merge_schema or []))
    prefill_email = (settings.DOCUSEAL_PREFILL_EMAIL or "").strip()
    if not prefill_email:
        raise ValidationError(
            {"form": ["DOCUSEAL_PREFILL_EMAIL is required for previews."]}
        )

    try:
        submission = create_submission(
            template_id=int(version.docuseal_template_id),
            name=f"Preview {version.template.stable_key}@{version.version_label}",
            submitters=[
                prefill_submitter_payload(email=prefill_email, values=preview_context),
                agent_submitter_payload(
                    email="preview-agent@example.com",
                    name="Preview Agent",
                    external_id=f"preview-{version.public_id}",
                ),
            ],
        )
        preview_bytes = download_submission_documents(submission.id)
    except DocuSealNotConfigured as exc:
        raise ValidationError({"form": ["DocuSeal is not configured."]}) from exc
    except DocuSealError as exc:
        raise ValidationError(
            {
                "form": [
                    "Could not generate a DocuSeal preview. Ensure Prefill and "
                    "Agent fields are placed in the builder."
                ]
            }
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
    if (
        hasattr(template, "_prefetched_objects_cache")
        and "versions" in template._prefetched_objects_cache
    ):
        versions = list(template.versions.all())
    else:
        versions = list(template.versions.order_by("-created_at", "-pk"))
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
    embeds_ok = docuseal_embeds_available()
    builder = None
    if (
        embeds_ok
        and version.status == ContractTemplateVersion.Status.DRAFT
        and (version.docuseal_template_id or version.source_document)
        and is_docuseal_builder_configured()
    ):
        try:
            builder = builder_token_for_version(version)
        except ValidationError:
            builder = None
    origin = embed_origin() if is_docuseal_configured() else ""
    template_id = version.docuseal_template_id
    admin_url = ""
    if origin:
        admin_url = (
            f"{origin}/templates/{template_id}"
            if template_id
            else f"{origin}/templates"
        )
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
        "docusealTemplateId": version.docuseal_template_id,
        "docusealExternalId": version.docuseal_external_id or "",
        "docusealHost": embed_host() if is_docuseal_configured() else "",
        "docusealOrigin": origin,
        "docusealAdminUrl": admin_url,
        "docusealEmbedsAvailable": embeds_ok,
        "builder": builder,
        "builderReady": is_docuseal_builder_configured(),
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
