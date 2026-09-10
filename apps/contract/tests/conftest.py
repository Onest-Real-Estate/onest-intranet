"""Fixtures for agent contract domain tests."""

from __future__ import annotations

import base64
from datetime import date
from unittest.mock import patch

import pytest
from django.core.files.base import ContentFile
from django.utils import timezone

from apps.contract.lifecycle import contract_version, transition
from apps.contract.models import (
    AgentContract,
    ContractArtifact,
    ContractSignature,
    ContractSigningIntent,
    ContractTemplate,
    ContractTemplateVersion,
)
from apps.contract.signing_disclosure import DISCLOSURE_VERSION
from apps.contract.statuses import ContractStatus
from apps.contract.template_security import checksum_of
from apps.user.models import Office, User, UserRoleAssignment
from apps.user.tests.test_profile import completed_user


@pytest.fixture
def seeded_offices():
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def office(slug: str) -> Office:
    return Office.objects.get(slug=slug)


def assign(user: User, role: str, scope_type: str, scope_office=None) -> None:
    assignment = UserRoleAssignment(
        user=user, role=role, scope_type=scope_type, scope_office=scope_office
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()


def company_admin(seeded_offices) -> User:
    user = completed_user(
        email="contract.admin@example.com", office=office("onest-head-office")
    )
    assign(user, "system_admin", "company")
    return user


def branch_admin(seeded_offices, slug="fairfax-va") -> User:
    user = completed_user(email=f"branch.{slug}@example.com", office=office(slug))
    assign(user, "branch_manager", "office", office(slug))
    return user


def agent(seeded_offices, *, email="agent@example.com", slug="fairfax-va") -> User:
    return completed_user(email=email, office=office(slug))


def published_template(*, key: str = "ica-v1") -> ContractTemplateVersion:
    template = ContractTemplate.objects.create(
        stable_key=key,
        name="ICA",
        status=ContractTemplate.Status.ACTIVE,
        company_wide=True,
    )
    version = ContractTemplateVersion.objects.create(
        template=template,
        version_label="1.0.0",
        status=ContractTemplateVersion.Status.PUBLISHED,
    )
    template.active_version = version
    template.save(update_fields=["active_version", "updated_at"])
    return version


def issue_awaiting_company(
    admin: User,
    contract: AgentContract,
    *,
    company_signatory: User | None = None,
) -> AgentContract:
    """Issue a ready-for-review contract to ``awaiting_company_signature``."""
    signatory = company_signatory or admin
    with (
        patch("apps.contract.lifecycle._queue_pdf_generation"),
        patch("apps.contract.lifecycle._queue_agent_status_email"),
        patch("apps.contract.lifecycle._queue_company_signatory_invite"),
    ):
        return transition(
            actor=admin,
            contract=contract,
            action="issue",
            expected_version=contract_version(contract),
            confirmed=True,
            company_signatory=signatory,
        )


def attach_stub_generated_pdf(contract: AgentContract) -> ContractArtifact:
    """Minimal review PDF so company/agent ceremonies can proceed in tests."""
    pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
    artifact = ContractArtifact(
        contract=contract,
        kind=ContractArtifact.Kind.GENERATED_PDF,
        display_name="review.pdf",
        media_type="application/pdf",
        byte_size=len(pdf),
        checksum="a" * 64,
        renderer_version="hub-pdf-1.0.0",
        input_fingerprint="fp",
    )
    artifact.file.save("review.pdf", ContentFile(pdf), save=False)
    artifact.save()
    contract.generated_pdf = artifact
    contract.save(update_fields=["generated_pdf", "updated_at"])
    return artifact


def record_company_signature(
    signatory: User,
    contract: AgentContract,
    *,
    appearance: bytes | None = None,
) -> ContractSignature:
    """Create a durable Company signature row (without the full ceremony UI)."""
    # Same 1x1 PNG used by signing ceremony tests (PIL-readable).
    if appearance is None:
        appearance = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
            "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
    now = timezone.now()
    artifact = contract.generated_pdf
    checksum = artifact.checksum if artifact is not None else "a" * 64
    intent = ContractSigningIntent(
        contract=contract,
        actor=signatory,
        signer_role=ContractSigningIntent.SignerRole.COMPANY,
        contract_version=contract_version(contract),
        artifact=artifact,
        artifact_checksum=checksum,
        session_key_hash="s" * 64,
        request_ip_hash="i" * 64,
        request_ua_hash="u" * 64,
        disclosure_version=DISCLOSURE_VERSION,
        consent_accepted_at=now,
        status=ContractSigningIntent.Status.CONSUMED,
        expires_at=now,
        consumed_at=now,
    )
    intent.save()
    signature = ContractSignature(
        contract=contract,
        intent=intent,
        signer=signatory,
        signer_role=ContractSignature.SignerRole.COMPANY,
        signed_at=now,
        disclosure_version=DISCLOSURE_VERSION,
        signature_method=ContractSignature.Method.HUB_EMBEDDED,
        appearance_checksum=checksum_of(appearance),
        source_checksum=checksum,
        signed_date_value=date.today().isoformat(),
        finalization_status=ContractSignature.FinalizationStatus.READY,
        request_ip_hash=intent.request_ip_hash,
        request_ua_hash=intent.request_ua_hash,
    )
    signature.appearance_file.save(
        f"company-{signature.public_id}.png",
        ContentFile(appearance),
        save=False,
    )
    signature.save()
    return signature


def release_to_agent(
    signatory: User,
    contract: AgentContract,
    *,
    attach_pdf: bool = True,
) -> AgentContract:
    """Attach PDF if needed, record company signature, transition to ``sent``."""
    if attach_pdf and not contract.generated_pdf_id:
        attach_stub_generated_pdf(contract)
        contract.refresh_from_db()
    if not ContractSignature.objects.filter(
        contract=contract,
        signer_role=ContractSignature.SignerRole.COMPANY,
    ).exists():
        record_company_signature(signatory, contract)
    with (
        patch("apps.contract.lifecycle._queue_agent_release_invite"),
        patch("apps.contract.lifecycle._queue_agent_status_email"),
    ):
        return transition(
            actor=signatory,
            contract=contract,
            action="mark_company_signed",
            expected_version=contract_version(contract),
        )


def issue_sent_to_agent(
    admin: User,
    contract: AgentContract,
    *,
    company_signatory: User | None = None,
) -> AgentContract:
    """Issue then complete company countersign so the agent may sign."""
    signatory = company_signatory or admin
    awaiting = issue_awaiting_company(admin, contract, company_signatory=signatory)
    assert awaiting.status == ContractStatus.AWAITING_COMPANY_SIGNATURE
    return release_to_agent(signatory, awaiting)
