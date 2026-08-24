"""Contract review-PDF generation: render, attach, idempotency, delivery."""

from __future__ import annotations

import io
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    BooleanObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

from apps.audit.models import AuditEvent, DomainEvent
from apps.contract.lifecycle import contract_version, transition
from apps.contract.models import (
    ContractArtifact,
    ContractTemplate,
    ContractTemplateVersion,
)
from apps.contract.pdf_generation import (
    RENDERER_VERSION,
    attach_generated_pdf,
    build_merge_values,
    generate_and_store,
    render_contract_pdf,
)
from apps.contract.services import create_draft_contract
from apps.contract.statuses import ContractStatus
from apps.contract.tasks import cleanup_orphan_contract_artifacts, generate_contract_pdf
from apps.contract.template_security import checksum_of
from apps.contract.tests.conftest import agent, company_admin


def _acroform_pdf(*field_names: str) -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    field_refs = []
    for index, name in enumerate(field_names):
        field = DictionaryObject()
        field.update(
            {
                NameObject("/FT"): NameObject("/Tx"),
                NameObject("/T"): TextStringObject(name),
                NameObject("/V"): TextStringObject(""),
                NameObject("/Kids"): ArrayObject(),
            }
        )
        field_ref = writer._add_object(field)
        y = 700 - (index * 28)
        widget = DictionaryObject()
        widget.update(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Widget"),
                NameObject("/Parent"): field_ref,
                NameObject("/Rect"): ArrayObject(
                    [
                        NumberObject(72),
                        NumberObject(y),
                        NumberObject(400),
                        NumberObject(y + 20),
                    ]
                ),
                NameObject("/F"): NumberObject(4),
            }
        )
        widget_ref = writer.add_annotation(0, widget)
        field[NameObject("/Kids")] = ArrayObject([widget_ref])
        field_refs.append(field_ref)

    acro = DictionaryObject(
        {
            NameObject("/Fields"): ArrayObject(field_refs),
            NameObject("/NeedAppearances"): BooleanObject(True),
        }
    )
    writer.root_object[NameObject("/AcroForm")] = writer._add_object(acro)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _published_pdf_template(
    *,
    key: str = "ica-pdf",
    fields: tuple[str, ...] = (
        "party.legalFirstName",
        "office.state",
        "contract.publicId",
        "terms.agentSplitPercent",
    ),
) -> ContractTemplateVersion:
    template = ContractTemplate.objects.create(
        stable_key=key,
        name="ICA PDF",
        status=ContractTemplate.Status.ACTIVE,
        company_wide=True,
    )
    version = ContractTemplateVersion(
        template=template,
        version_label="1.0.0",
        status=ContractTemplateVersion.Status.DRAFT,
        source_format="pdf",
        source_media_type="application/pdf",
        merge_schema=[
            {
                "key": name,
                "type": "text",
                "label": name,
                "source": name,
            }
            for name in fields
        ],
        extracted_placeholder_keys=list(fields),
    )
    data = _acroform_pdf(*fields)
    version.source_checksum = checksum_of(data)
    version.source_document.save("template.pdf", ContentFile(data), save=False)
    version.preview_checksum = version.source_checksum
    from django.utils import timezone as dj_tz

    version.preview_generated_at = dj_tz.now()
    version.published_at = dj_tz.now()
    version.status = ContractTemplateVersion.Status.PUBLISHED
    version.full_clean()
    version.save()
    template.active_version = version
    template.save(update_fields=["active_version", "updated_at"])
    return version


def _issued_contract(admin, recipient, **kwargs):
    version = kwargs.pop("template_version", None) or _published_pdf_template()
    contract = create_draft_contract(
        admin,
        recipient=recipient,
        effective_on=date.today(),
        template_version=version,
        agent_split_percent="70",
        office_split_percent="30",
        **kwargs,
    )
    ready = transition(
        actor=admin,
        contract=contract,
        action="submit_for_review",
        expected_version=contract_version(contract),
    )
    with patch("apps.contract.tasks.generate_contract_pdf.delay"):
        return transition(
            actor=admin,
            contract=ready,
            action="issue",
            expected_version=contract_version(ready),
            confirmed=True,
        )


@pytest.mark.django_db
def test_build_merge_values_from_frozen_snapshots(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="merge@example.com")
    recipient.first_name = "Ada"
    recipient.last_name = "Lovelace"
    recipient.save(update_fields=["first_name", "last_name"])
    contract = _issued_contract(admin, recipient)
    values = build_merge_values(contract)
    assert values["party.legalFirstName"] == "Ada"
    assert "office.state" in values
    assert values["contract.publicId"] == str(contract.public_id)
    assert values["terms.agentSplitPercent"] == "70.000"


@pytest.mark.django_db
def test_render_golden_pdf_matches_frozen_inputs(seeded_offices, tmp_path):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="golden@example.com")
    recipient.first_name = "Grace"
    recipient.save(update_fields=["first_name"])
    contract = _issued_contract(admin, recipient)

    rendered = render_contract_pdf(contract)
    assert rendered.page_count >= 1
    assert rendered.checksum
    assert "document_id" in rendered.markers
    assert rendered.merge_values["party.legalFirstName"] == "Grace"

    # Persist under tmp for local visual inspection; CI asserts structure above.
    golden = tmp_path / "golden-contract.pdf"
    golden.write_bytes(rendered.data)
    assert golden.stat().st_size == len(rendered.data)

    reader = PdfReader(io.BytesIO(rendered.data))
    assert len(reader.pages) == rendered.page_count
    fields = reader.get_fields() or {}
    assert fields["party.legalFirstName"]["/V"] == "Grace"
    meta = reader.metadata
    keywords = "" if meta is None else str(meta.get("/Keywords") or "")
    assert str(contract.public_id) in keywords


@pytest.mark.django_db
def test_generate_and_store_is_idempotent(
    seeded_offices, settings, django_capture_on_commit_callbacks
):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="idem@example.com")
    contract = _issued_contract(admin, recipient)

    with django_capture_on_commit_callbacks(execute=True):
        first = generate_and_store(contract.pk)
    assert first == "ready"
    contract.refresh_from_db()
    artifact_id = contract.generated_pdf_id
    assert artifact_id is not None
    events = DomainEvent.objects.filter(name="contract.pdf_ready").count()
    audits = AuditEvent.objects.filter(action="contract.pdf_generated").count()
    assert events == 1
    assert audits == 1

    with django_capture_on_commit_callbacks(execute=True):
        second = generate_and_store(contract.pk)
    assert second in {"ready", "ready_idempotent"}
    contract.refresh_from_db()
    assert contract.generated_pdf_id == artifact_id
    assert (
        ContractArtifact.objects.filter(
            contract=contract, kind=ContractArtifact.Kind.GENERATED_PDF
        ).count()
        == 1
    )
    assert DomainEvent.objects.filter(name="contract.pdf_ready").count() == events
    assert AuditEvent.objects.filter(action="contract.pdf_generated").count() == audits


@pytest.mark.django_db
def test_task_duplicate_delivery_idempotent(
    seeded_offices, settings, django_capture_on_commit_callbacks
):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="task@example.com")
    contract = _issued_contract(admin, recipient)

    with django_capture_on_commit_callbacks(execute=True):
        assert generate_contract_pdf(contract.pk) == "ready"
    with django_capture_on_commit_callbacks(execute=True):
        assert generate_contract_pdf(contract.pk) == "ready_idempotent"
    assert AuditEvent.objects.filter(action="contract.pdf_generated").count() == 1
    assert DomainEvent.objects.filter(name="contract.pdf_ready").count() == 1


@pytest.mark.django_db
def test_failed_render_marks_generation_error(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="fail@example.com")
    contract = _issued_contract(admin, recipient)

    with patch(
        "apps.contract.pdf_generation.render_preview_pdf",
        side_effect=Exception("boom"),
    ):
        from apps.contract.pdf_generation import (
            PdfGenerationError,
            mark_generation_failed,
        )

        with pytest.raises(PdfGenerationError) as exc:
            render_contract_pdf(contract)
        assert exc.value.code == "render_failed"
        assert exc.value.retryable is True
        mark_generation_failed(contract.pk, code=exc.value.code)

    contract.refresh_from_db()
    assert contract.status == ContractStatus.GENERATION_ERROR
    assert contract.generated_pdf_id is None
    assert not DomainEvent.objects.filter(name="contract.pdf_ready").exists()


@pytest.mark.django_db
def test_nonretryable_failure_marks_error_without_raise(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="noretry@example.com")
    contract = _issued_contract(admin, recipient)

    with patch(
        "apps.contract.pdf_generation.render_contract_pdf",
        side_effect=__import__(
            "apps.contract.pdf_generation", fromlist=["PdfGenerationError"]
        ).PdfGenerationError("missing_snapshots", retryable=False),
    ):
        result = generate_and_store(contract.pk)

    assert result == "failed:missing_snapshots"
    contract.refresh_from_db()
    assert contract.status == ContractStatus.GENERATION_ERROR


@pytest.mark.django_db
def test_artifact_download_authorized(seeded_offices, client, settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="dl@example.com")
    outsider = agent(seeded_offices, email="outsider@example.com", slug="harrisburg")
    contract = _issued_contract(admin, recipient)
    assert generate_and_store(contract.pk) == "ready"
    contract.refresh_from_db()
    url = reverse(
        "agent_contract_artifact_download",
        kwargs={
            "public_id": contract.public_id,
            "artifact_public_id": contract.generated_pdf.public_id,
        },
    )

    client.force_login(admin)
    ok = client.get(url)
    assert ok.status_code == 200
    assert ok["Content-Type"] == "application/pdf"
    assert ok["Cache-Control"].startswith("private")

    client.force_login(recipient)
    own = client.get(url)
    assert own.status_code == 200

    client.force_login(outsider)
    denied = client.get(url)
    assert denied.status_code == 404

    # Object-key style probing must not work.
    client.force_login(admin)
    missing = client.get(
        reverse(
            "agent_contract_artifact_download",
            kwargs={
                "public_id": contract.public_id,
                "artifact_public_id": "00000000-0000-0000-0000-000000000000",
            },
        )
    )
    assert missing.status_code == 404


@pytest.mark.django_db
def test_orphan_cleanup_preserves_current(seeded_offices, settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="orphan@example.com")
    contract = _issued_contract(admin, recipient)
    generate_and_store(contract.pk)
    contract.refresh_from_db()
    current_id = contract.generated_pdf_id

    orphan = ContractArtifact(
        contract=contract,
        kind=ContractArtifact.Kind.GENERATED_PDF,
        display_name="orphan.pdf",
        media_type="application/pdf",
        byte_size=10,
        checksum="a" * 64,
        renderer_version=RENDERER_VERSION,
    )
    orphan.file.save("orphan.pdf", ContentFile(b"%PDF-orphan"), save=False)
    orphan.created_at = timezone.now() - timedelta(hours=48)
    orphan.save()

    deleted = cleanup_orphan_contract_artifacts(older_than_hours=24)
    assert deleted == 1
    assert not ContractArtifact.objects.filter(pk=orphan.pk).exists()
    assert ContractArtifact.objects.filter(pk=current_id).exists()


@pytest.mark.django_db
def test_attach_emits_event_after_commit(
    seeded_offices, django_capture_on_commit_callbacks
):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="commit@example.com")
    contract = _issued_contract(admin, recipient)
    rendered = render_contract_pdf(contract)
    with django_capture_on_commit_callbacks(execute=True):
        artifact, emitted = attach_generated_pdf(contract, rendered)
    assert emitted is True
    assert artifact.renderer_version == RENDERER_VERSION
    assert DomainEvent.objects.filter(name="contract.pdf_ready").exists()
    assert AuditEvent.objects.filter(action="contract.pdf_generated").exists()
