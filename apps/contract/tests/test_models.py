"""Model constraints, snapshots, PROTECT, artifacts, and indexes."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.contract.models import (
    AgentContract,
    ContractArtifact,
    ContractTemplate,
    ContractTemplateVersion,
)
from apps.contract.services import attach_artifact, create_draft_contract
from apps.contract.statuses import ContractStatus
from apps.contract.tests.conftest import agent, company_admin, office


@pytest.mark.django_db
def test_draft_contract_persists_decimal_precision(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    contract = create_draft_contract(
        admin,
        recipient=recipient,
        effective_on=date.today(),
        agent_split_percent="70.125",
        office_split_percent="29.875",
        transaction_fee_amount="150.50",
        mentor_percent="5",
        mentor_basis="gross_commission",
        mentor_payee=admin,
    )
    contract.refresh_from_db()
    assert contract.agent_split_percent == Decimal("70.125")
    assert contract.office_split_percent == Decimal("29.875")
    assert contract.transaction_fee_amount == Decimal("150.50")
    assert contract.mentor_percent == Decimal("5.000")


@pytest.mark.django_db
def test_invalid_percentage_and_money_rejected(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    with pytest.raises(ValidationError):
        create_draft_contract(
            admin,
            recipient=recipient,
            effective_on=date.today(),
            agent_split_percent="101",
            office_split_percent="-1",
        )
    with pytest.raises(ValidationError):
        create_draft_contract(
            admin,
            recipient=recipient,
            effective_on=date.today(),
            transaction_fee_amount="-10",
        )


@pytest.mark.django_db
def test_splits_must_sum_to_one_hundred(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    with pytest.raises(ValidationError) as exc:
        create_draft_contract(
            admin,
            recipient=recipient,
            effective_on=date.today(),
            agent_split_percent="60",
            office_split_percent="30",
        )
    assert "agent_split_percent" in exc.value.message_dict


@pytest.mark.django_db
def test_expiration_before_effective_rejected(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    with pytest.raises(ValidationError):
        create_draft_contract(
            admin,
            recipient=recipient,
            effective_on=date.today(),
            expires_on=date.today() - timedelta(days=1),
        )


@pytest.mark.django_db
def test_snapshots_survive_profile_and_office_edits(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    recipient.first_name = "Original"
    recipient.last_name = "Agent"
    recipient.license_number = "VA-111"
    recipient.save()
    owning = office("fairfax-va")
    owning.street_address = "100 Main St"
    owning.save(update_fields=["street_address"])
    owning.refresh_from_db()

    contract = create_draft_contract(
        admin,
        recipient=recipient,
        office=owning,
        effective_on=date.today(),
        agent_split_percent="80",
        office_split_percent="20",
    )
    frozen_party = dict(contract.party_snapshot)
    frozen_office = dict(contract.office_snapshot)
    frozen_terms = dict(contract.terms_snapshot)

    recipient.first_name = "Changed"
    recipient.license_number = "VA-999"
    recipient.save()
    owning.street_address = "999 Other Ave"
    owning.save()
    contract.agent_split_percent = Decimal("50.000")
    contract.office_split_percent = Decimal("50.000")
    contract.save()

    contract.refresh_from_db()
    assert contract.party_snapshot == frozen_party
    assert contract.office_snapshot == frozen_office
    assert contract.terms_snapshot == frozen_terms
    assert contract.party_snapshot["legalFirstName"] == "Original"
    assert contract.office_snapshot["streetAddress"] == "100 Main St"
    assert contract.terms_snapshot["agentSplitPercent"] == "80.000"


@pytest.mark.django_db
def test_protect_blocks_deleting_referenced_agent_and_office(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    contract = create_draft_contract(
        admin, recipient=recipient, effective_on=date.today()
    )
    with pytest.raises(ProtectedError):
        recipient.delete()
    with pytest.raises(ProtectedError):
        contract.office.delete()


@pytest.mark.django_db
def test_protect_blocks_deleting_template_version_in_use(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    template = ContractTemplate.objects.create(
        stable_key="standard-ica",
        name="Standard ICA",
        status="active",
        company_wide=True,
    )
    version = ContractTemplateVersion.objects.create(
        template=template,
        version_label="1.0.0",
        status=ContractTemplateVersion.Status.PUBLISHED,
    )
    template.active_version = version
    template.save(update_fields=["active_version"])
    create_draft_contract(
        admin,
        recipient=recipient,
        effective_on=date.today(),
        template_version=version,
    )
    with pytest.raises(ProtectedError):
        version.delete()
    with pytest.raises(ProtectedError):
        template.delete()


@pytest.mark.django_db
def test_one_active_contract_per_recipient(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    from apps.contract.lifecycle import allow_status_write

    first = create_draft_contract(admin, recipient=recipient, effective_on=date.today())
    first.status = ContractStatus.ACTIVE
    first.activated_at = first.created_at
    with allow_status_write():
        first.save()

    second = create_draft_contract(
        admin,
        recipient=recipient,
        effective_on=date.today() + timedelta(days=30),
    )
    second.status = ContractStatus.ACTIVE
    with pytest.raises(IntegrityError), transaction.atomic(), allow_status_write():
        second.save()


@pytest.mark.django_db
def test_artifact_is_private_reference_with_checksum(
    seeded_offices, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    contract = create_draft_contract(
        admin, recipient=recipient, effective_on=date.today()
    )
    data = b"%PDF-1.4 private contract bytes"
    checksum = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    # Real checksum of the payload:
    import hashlib

    checksum = hashlib.sha256(data).hexdigest()
    artifact = attach_artifact(
        admin,
        contract,
        kind=ContractArtifact.Kind.GENERATED_PDF,
        file=ContentFile(data, name="draft.pdf"),
        display_name="draft.pdf",
        media_type="application/pdf",
        byte_size=len(data),
        checksum=checksum,
    )
    contract.refresh_from_db()
    assert contract.generated_pdf_id == artifact.pk
    assert artifact.checksum == checksum
    assert artifact.file.url is None or not str(artifact.file).startswith("http")
    # Storage path is under private layout, never a permanent public media URL.
    assert "contracts/" in artifact.file.name
    assert artifact.kind == ContractArtifact.Kind.GENERATED_PDF


@pytest.mark.django_db
def test_artifact_rejects_bad_checksum(seeded_offices, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    contract = create_draft_contract(
        admin, recipient=recipient, effective_on=date.today()
    )
    with pytest.raises(ValidationError):
        attach_artifact(
            admin,
            contract,
            kind=ContractArtifact.Kind.SIGNED_PDF,
            file=ContentFile(b"x", name="signed.pdf"),
            display_name="signed.pdf",
            media_type="application/pdf",
            byte_size=1,
            checksum="not-a-sha256",
        )


@pytest.mark.django_db
def test_expected_indexes_exist():
    index_names = {index.name for index in AgentContract._meta.indexes}
    assert "contract_recipient_status" in index_names
    assert "contract_office_status" in index_names
    assert "contract_status_effective" in index_names
    assert "contract_family_version_idx" in index_names
    constraint_names = {c.name for c in AgentContract._meta.constraints}
    assert "contract_one_active_per_recipient" in constraint_names
    assert "contract_expires_on_or_after_effective" in constraint_names


@pytest.mark.django_db
def test_mentor_terms_require_basis(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    with pytest.raises(ValidationError) as exc:
        create_draft_contract(
            admin,
            recipient=recipient,
            effective_on=date.today(),
            mentor_percent="10",
            mentor_payee=admin,
        )
    assert "mentor_basis" in exc.value.message_dict


@pytest.mark.django_db
def test_mentor_terms_require_payee(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    with pytest.raises(ValidationError) as exc:
        create_draft_contract(
            admin,
            recipient=recipient,
            effective_on=date.today(),
            mentor_percent="10",
            mentor_basis="gross_commission",
        )
    assert "mentor_payee" in exc.value.message_dict
