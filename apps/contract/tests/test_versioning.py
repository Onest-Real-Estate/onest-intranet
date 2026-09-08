"""Contract family versioning, amendments, replacements, and immutability."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction

from apps.contract.change_kinds import ContractChangeKind
from apps.contract.lifecycle import allow_status_write, contract_version, transition
from apps.contract.models import AgentContract, ContractArtifact
from apps.contract.services import create_draft_contract
from apps.contract.statuses import ContractStatus
from apps.contract.tests.conftest import agent, company_admin
from apps.contract.versioning import (
    assert_eligible_base,
    create_amendment_draft,
    create_replacement_draft,
    governing_terms_payload,
    lock_family,
    next_version_number,
    term_diff,
)


def _active_contract(admin, recipient, **kwargs) -> AgentContract:
    contract = create_draft_contract(
        admin,
        recipient=recipient,
        effective_on=date.today(),
        agent_split_percent="70",
        office_split_percent="30",
        **kwargs,
    )
    with allow_status_write():
        contract.status = ContractStatus.ACTIVE
        contract.save(update_fields=["status", "updated_at"])
    return contract


@pytest.mark.django_db
def test_signed_legal_fields_are_immutable(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    contract = _active_contract(admin, recipient)
    contract.agent_split_percent = Decimal("55.000")
    with pytest.raises(ValidationError) as exc:
        contract.save()
    assert "immutable" in str(exc.value).lower()


@pytest.mark.django_db
def test_artifact_bytes_are_immutable_after_create(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    contract = create_draft_contract(
        admin, recipient=recipient, effective_on=date.today()
    )
    artifact = ContractArtifact(
        contract=contract,
        kind=ContractArtifact.Kind.GENERATED_PDF,
        display_name="a.pdf",
        media_type="application/pdf",
        byte_size=12,
        checksum="a" * 64,
        created_by=admin,
    )
    artifact.file.save("a.pdf", ContentFile(b"%PDF-test%"), save=False)
    artifact.full_clean()
    artifact.save()
    artifact.checksum = "b" * 64
    with pytest.raises(ValidationError):
        artifact.save()


@pytest.mark.django_db
def test_create_amendment_and_replacement_drafts(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    base = _active_contract(admin, recipient)
    amendment = create_amendment_draft(
        admin,
        base,
        change_summary="Reduce agent split to 65%.",
    )
    assert amendment.change_kind == ContractChangeKind.AMENDMENT
    assert amendment.amends_id == base.pk
    assert amendment.family_id == base.family_id
    assert amendment.version_number == 2
    assert amendment.status == ContractStatus.DRAFT
    assert amendment.agent_split_percent == base.agent_split_percent
    assert amendment.change_summary.startswith("Reduce")

    # Branch blocked while amendment is in flight.
    with pytest.raises(ValidationError):
        create_replacement_draft(admin, base)

    with allow_status_write():
        amendment.status = ContractStatus.SUPERSEDED
        amendment.save(update_fields=["status", "updated_at"])

    replacement = create_replacement_draft(admin, base)
    assert replacement.change_kind == ContractChangeKind.REPLACEMENT
    assert replacement.supersedes_id == base.pk
    assert replacement.version_number == 3
    assert replacement.amends_id is None


@pytest.mark.django_db
def test_amendment_against_draft_base_refused(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    draft = create_draft_contract(admin, recipient=recipient, effective_on=date.today())
    with pytest.raises(ValidationError):
        assert_eligible_base(draft, change_kind=ContractChangeKind.AMENDMENT)


@pytest.mark.django_db
def test_family_version_numbers_unique_under_lock(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    base = _active_contract(admin, recipient)
    with transaction.atomic():
        lock_family(base.family_id)
        first = next_version_number(base.family_id)
        # Simulate a concurrent insert by creating the row that claims `first`.
        sibling = create_amendment_draft(admin, base)
        assert sibling.version_number == first
        second = next_version_number(base.family_id)
        assert second == first + 1


@pytest.mark.django_db
def test_duplicate_family_version_rejected_by_constraint(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    base = _active_contract(admin, recipient)
    amendment = create_amendment_draft(admin, base)
    twin = AgentContract(
        recipient=recipient,
        office=base.office,
        created_by=admin,
        status=ContractStatus.DRAFT,
        effective_on=date.today(),
        family_id=base.family_id,
        version_number=amendment.version_number,
        change_kind=ContractChangeKind.AMENDMENT,
        amends=base,
        root_agreement=base,
        agent_split_percent=Decimal("70.000"),
        office_split_percent=Decimal("30.000"),
        party_snapshot={"email": recipient.email},
        office_snapshot={"name": base.office.name},
        terms_snapshot={},
    )
    with pytest.raises((IntegrityError, ValidationError)), transaction.atomic():
        twin.save()


@pytest.mark.django_db
def test_activate_replacement_supersedes_prior_without_erase(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    base = _active_contract(admin, recipient)
    replacement = create_replacement_draft(admin, base)
    with allow_status_write():
        replacement.status = ContractStatus.SIGNED
        replacement.save(update_fields=["status", "updated_at"])

    activated = transition(
        actor=admin,
        contract=replacement,
        action="activate",
        expected_version=contract_version(replacement),
        confirmed=True,
    )
    base.refresh_from_db()
    assert activated.status == ContractStatus.ACTIVE
    assert base.status == ContractStatus.SUPERSEDED
    assert base.agent_split_percent == Decimal("70.000")
    assert AgentContract.objects.filter(pk=base.pk).exists()


@pytest.mark.django_db
def test_term_diff_and_governing_payload(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    base = _active_contract(admin, recipient)
    amendment = create_amendment_draft(admin, base, change_summary="Cap change")
    amendment.annual_cap_amount = Decimal("25000.00")
    amendment.terms_snapshot = {
        **(amendment.terms_snapshot or {}),
        "annualCapAmount": "25000.00",
    }
    amendment.save(update_fields=["annual_cap_amount", "terms_snapshot", "updated_at"])
    rows = term_diff(base, amendment)
    keys = {row["key"] for row in rows}
    assert "annualCapAmount" in keys
    governing = governing_terms_payload(base)
    assert governing["isGoverning"] is True
    assert governing["versionNumber"] == 1


@pytest.mark.django_db
def test_scope_blocks_out_of_scope_amendment(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, email="local@example.com", slug="fairfax-va")
    outsider = agent(seeded_offices, email="outsider@example.com", slug="harrisburg")
    base = _active_contract(admin, recipient)
    from apps.contract.tests.conftest import assign, office
    from apps.user.tests.test_profile import completed_user

    branch = completed_user(
        email="branch.harrisburg@example.com", office=office("harrisburg")
    )
    assign(branch, "branch_manager", "office", office("harrisburg"))
    with pytest.raises(PermissionDenied):
        create_amendment_draft(branch, base)
    # Outsider cannot be used as actor without manage — same path.
    with pytest.raises(PermissionDenied):
        create_replacement_draft(outsider, base)


@pytest.mark.django_db
def test_cycle_prevention_on_self_amend(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    base = _active_contract(admin, recipient)
    amendment = create_amendment_draft(admin, base)
    with allow_status_write():
        base.status = ContractStatus.SUPERSEDED
        base.save(update_fields=["status", "updated_at"])
        amendment.status = ContractStatus.ACTIVE
        amendment.save(update_fields=["status", "updated_at"])
    # Amending the active tip is allowed; the amends chain stays acyclic.
    child = create_amendment_draft(admin, amendment)
    assert child.amends_id == amendment.pk
    assert child.version_number == 3
