"""Admin create/update/preview/issue services for agent contracts."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.contract.administration import (
    applicable_template_versions,
    assert_template_applicable,
    commercial_preview,
    issue_contract,
    search_contract_recipients,
    update_draft_contract,
    workspace_payload,
)
from apps.contract.lifecycle import contract_version, transition
from apps.contract.models import ContractTemplate, ContractTemplateVersion
from apps.contract.services import create_draft_contract
from apps.contract.statuses import ContractStatus
from apps.contract.tests.conftest import agent, branch_admin, company_admin, office


def _template(*, key="ica-admin", company_wide=True, states=None, offices=None):
    template = ContractTemplate.objects.create(
        stable_key=key,
        name=key,
        status=ContractTemplate.Status.ACTIVE,
        company_wide=company_wide,
        jurisdiction_state_codes=states or [],
    )
    version = ContractTemplateVersion.objects.create(
        template=template,
        version_label="1.0.0",
        status=ContractTemplateVersion.Status.PUBLISHED,
    )
    template.active_version = version
    template.save(update_fields=["active_version", "updated_at"])
    if offices:
        template.applicable_offices.set(offices)
    return version


@pytest.mark.django_db
def test_applicable_templates_respect_office_and_jurisdiction(seeded_offices):
    fairfax = office("fairfax-va")
    fairfax.state = "VA"
    fairfax.save(update_fields=["state"])
    wide = _template(key="wide", company_wide=True)
    va_only = _template(key="va-only", company_wide=True, states=["VA"])
    md_only = _template(key="md-only", company_wide=True, states=["MD"])
    local = _template(key="local-only", company_wide=False, offices=[fairfax])
    ids = set(
        applicable_template_versions(fairfax, date.today()).values_list("pk", flat=True)
    )
    assert wide.pk in ids
    assert va_only.pk in ids
    assert md_only.pk not in ids
    assert local.pk in ids


@pytest.mark.django_db
def test_create_rejects_inapplicable_template(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices, slug="fairfax-va")
    assert recipient.office is not None
    recipient.office.state = "VA"
    recipient.office.save(update_fields=["state"])
    md_only = _template(key="md-create", company_wide=True, states=["MD"])
    with pytest.raises(ValidationError):
        create_draft_contract(
            admin,
            recipient=recipient,
            effective_on=date.today(),
            template_version=md_only,
        )


@pytest.mark.django_db
def test_recipient_search_scope_and_min_length(seeded_offices):
    admin = branch_admin(seeded_offices, slug="fairfax-va")
    local = agent(seeded_offices, email="local.search@example.com", slug="fairfax-va")
    agent(seeded_offices, email="remote.search@example.com", slug="harrisburg")
    assert search_contract_recipients(admin, "l") == []
    results = search_contract_recipients(admin, "local.search")
    assert [row["id"] for row in results] == [local.pk]


@pytest.mark.django_db
def test_update_draft_preserves_and_audits(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    version = _template()
    contract = create_draft_contract(
        admin,
        recipient=recipient,
        effective_on=date.today(),
        template_version=version,
        agent_split_percent="70",
        office_split_percent="30",
    )
    updated = update_draft_contract(
        admin,
        contract,
        expected_version=contract_version(contract),
        agent_split_percent="65",
        office_split_percent="35",
    )
    assert updated.agent_split_percent == updated.agent_split_percent
    assert str(updated.agent_split_percent) == "65.000"
    assert updated.terms_snapshot["agentSplitPercent"] == "65.000"


@pytest.mark.django_db
def test_issue_idempotent_and_queues_pdf(
    seeded_offices, django_capture_on_commit_callbacks
):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    version = _template()
    contract = create_draft_contract(
        admin,
        recipient=recipient,
        effective_on=date.today(),
        template_version=version,
        agent_split_percent="70",
        office_split_percent="30",
    )
    ready = transition(
        actor=admin,
        contract=contract,
        action="submit_for_review",
        expected_version=contract_version(contract),
    )
    with (
        patch("apps.contract.tasks.generate_contract_pdf.delay") as pdf_delay,
        django_capture_on_commit_callbacks(execute=True),
    ):
        first = issue_contract(
            admin,
            ready,
            expected_version=contract_version(ready),
            confirmed=True,
            idempotency_key="k1",
            company_signatory=admin,
        )
        second = issue_contract(
            admin,
            first,
            expected_version=contract_version(first),
            confirmed=True,
            idempotency_key="k1",
            company_signatory=admin,
        )
    assert first.status == ContractStatus.AWAITING_COMPANY_SIGNATURE
    assert second.status == ContractStatus.AWAITING_COMPANY_SIGNATURE
    assert first.company_signatory_id == admin.pk
    assert pdf_delay.call_count == 1


@pytest.mark.django_db
def test_stale_agent_blocks_issue(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    version = _template()
    contract = create_draft_contract(
        admin,
        recipient=recipient,
        effective_on=date.today(),
        template_version=version,
    )
    ready = transition(
        actor=admin,
        contract=contract,
        action="submit_for_review",
        expected_version=contract_version(contract),
    )
    recipient.is_active = False
    recipient.save(update_fields=["is_active"])
    with pytest.raises(ValidationError):
        issue_contract(
            admin,
            ready,
            expected_version=contract_version(ready),
            confirmed=True,
            company_signatory=admin,
        )


@pytest.mark.django_db
def test_commercial_preview_permission(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    contract = create_draft_contract(
        admin,
        recipient=recipient,
        effective_on=date.today(),
        agent_split_percent="70",
        office_split_percent="30",
    )
    payload = commercial_preview(admin, contract)
    assert payload["breakdown"] is not None
    plain = agent(seeded_offices, email="noperm@example.com", slug="harrisburg")
    with pytest.raises(PermissionDenied):
        commercial_preview(plain, contract)


@pytest.mark.django_db
def test_assert_template_applicable_helper(seeded_offices):
    fairfax = office("fairfax-va")
    fairfax.state = "VA"
    fairfax.save(update_fields=["state"])
    version = _template(key="assert-md", company_wide=True, states=["MD"])
    with pytest.raises(ValidationError):
        assert_template_applicable(version, office=fairfax, effective_on=date.today())


@pytest.mark.django_db
def test_workspace_payload_includes_basis_options(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    contract = create_draft_contract(
        admin,
        recipient=recipient,
        effective_on=date.today(),
        template_version=_template(),
    )
    payload = workspace_payload(admin, contract)
    values = {row["value"] for row in payload["commissionBasisOptions"]}
    assert "agent_side_before_fees" in values
    assert all("label" in row for row in payload["commissionBasisOptions"])
