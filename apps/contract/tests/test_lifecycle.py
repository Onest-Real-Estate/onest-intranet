"""Agent contract lifecycle transition service."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.audit.models import AuditEvent, DomainEvent
from apps.contract.lifecycle import (
    ConfirmationRequired,
    StaleContractVersion,
    TransitionRefused,
    allow_status_write,
    allowed_actions,
    contract_version,
    expire_due_contracts,
    transition,
)
from apps.contract.models import (
    AgentContract,
    ContractTemplate,
    ContractTemplateVersion,
)
from apps.contract.services import create_draft_contract
from apps.contract.statuses import ContractStatus
from apps.contract.tests.conftest import agent, branch_admin, company_admin


def _published_template(*, key="ica-v1") -> ContractTemplateVersion:
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


def _ready_contract(admin, recipient, **kwargs):
    version = kwargs.pop("template_version", None) or _published_template()
    contract = create_draft_contract(
        admin,
        recipient=recipient,
        effective_on=date.today(),
        template_version=version,
        agent_split_percent="70",
        office_split_percent="30",
        **kwargs,
    )
    return transition(
        actor=admin,
        contract=contract,
        action="submit_for_review",
        expected_version=contract_version(contract),
    )


def _advance(admin, contract, *actions, confirmed=True):
    current = contract
    for action in actions:
        needs_confirm = action in {
            "issue",
            "activate",
            "supersede",
            "terminate",
        }
        current = transition(
            actor=admin,
            contract=current,
            action=action,
            expected_version=contract_version(current),
            confirmed=confirmed if needs_confirm else False,
        )
    return current


@pytest.mark.django_db
def test_happy_path_draft_to_active(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    ready = _ready_contract(admin, recipient)
    issued = _advance(admin, ready, "issue")
    assert issued.status == ContractStatus.SENT
    assert issued.sent_at is not None
    assert issued.party_snapshot
    assert issued.terms_snapshot

    viewed = _advance(admin, issued, "mark_viewed")
    signed = _advance(admin, viewed, "mark_signed")
    active = _advance(admin, signed, "activate")
    assert active.status == ContractStatus.ACTIVE
    assert active.activated_at is not None


@pytest.mark.django_db
def test_issue_requires_confirmation_and_published_template(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    ready = _ready_contract(admin, recipient)
    with pytest.raises(ConfirmationRequired):
        transition(
            actor=admin,
            contract=ready,
            action="issue",
            expected_version=contract_version(ready),
            confirmed=False,
        )

    draft = create_draft_contract(admin, recipient=recipient, effective_on=date.today())
    ready_no_template = transition(
        actor=admin,
        contract=draft,
        action="submit_for_review",
        expected_version=contract_version(draft),
    )
    with pytest.raises(TransitionRefused):
        transition(
            actor=admin,
            contract=ready_no_template,
            action="issue",
            expected_version=contract_version(ready_no_template),
            confirmed=True,
        )


@pytest.mark.django_db
def test_stale_version_rejected(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    contract = create_draft_contract(
        admin, recipient=recipient, effective_on=date.today()
    )
    stale = contract_version(contract)
    contract.special_arrangements = "edited"
    contract.save(update_fields=["special_arrangements", "updated_at"])
    with pytest.raises(StaleContractVersion):
        transition(
            actor=admin,
            contract=contract,
            action="submit_for_review",
            expected_version=stale,
        )


@pytest.mark.django_db
def test_idempotent_issue_no_duplicate_events(
    seeded_offices, django_capture_on_commit_callbacks
):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    ready = _ready_contract(admin, recipient)
    with (
        patch("apps.audit.tasks.dispatch_event.delay"),
        patch("apps.contract.tasks.generate_contract_pdf.delay") as pdf_delay,
        django_capture_on_commit_callbacks(execute=True),
    ):
        first = transition(
            actor=admin,
            contract=ready,
            action="issue",
            expected_version=contract_version(ready),
            confirmed=True,
            idempotency_key="issue-1",
        )
        audits = AuditEvent.objects.filter(action="contract.issued").count()
        domains = DomainEvent.objects.filter(name="contract.issued").count()
        second = transition(
            actor=admin,
            contract=first,
            action="issue",
            expected_version=contract_version(first),
            confirmed=True,
            idempotency_key="issue-1",
        )
    assert first.pk == second.pk
    assert second.status == ContractStatus.SENT
    assert AuditEvent.objects.filter(action="contract.issued").count() == audits
    assert DomainEvent.objects.filter(name="contract.issued").count() == domains
    assert pdf_delay.call_count == 1


@pytest.mark.django_db
def test_activate_supersedes_prior_active(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    first = _advance(
        admin,
        _ready_contract(admin, recipient, template_version=_published_template()),
        "issue",
        "mark_signed",
        "activate",
    )
    assert first.status == ContractStatus.ACTIVE

    second = _advance(
        admin,
        _ready_contract(
            admin,
            recipient,
            template_version=_published_template(key="ica-v2"),
        ),
        "issue",
        "mark_signed",
        "activate",
    )
    first.refresh_from_db()
    assert second.status == ContractStatus.ACTIVE
    assert first.status == ContractStatus.SUPERSEDED
    assert first.superseded_at is not None


@pytest.mark.django_db
def test_direct_status_save_refused(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    contract = create_draft_contract(
        admin, recipient=recipient, effective_on=date.today()
    )
    contract.status = ContractStatus.SENT
    with pytest.raises(ValidationError):
        contract.save()


@pytest.mark.django_db
def test_permission_and_scope_matrix(seeded_offices):
    company = company_admin(seeded_offices)
    branch = branch_admin(seeded_offices, slug="fairfax-va")
    local = agent(seeded_offices, email="local@example.com", slug="fairfax-va")
    plain = agent(seeded_offices, email="plain@example.com", slug="harrisburg")

    ready = _ready_contract(company, local)
    with pytest.raises(PermissionDenied):
        transition(
            actor=plain,
            contract=ready,
            action="issue",
            expected_version=contract_version(ready),
            confirmed=True,
        )

    issued = _advance(branch, ready, "issue")
    viewed = transition(
        actor=local,
        contract=issued,
        action="mark_viewed",
        expected_version=contract_version(issued),
    )
    assert viewed.status == ContractStatus.VIEWED
    assert "issue" not in allowed_actions(branch, viewed)
    assert "mark_signed" in allowed_actions(branch, viewed)


@pytest.mark.django_db
def test_expire_due_contracts_idempotent(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    active = _advance(
        admin,
        _ready_contract(admin, recipient),
        "issue",
        "mark_signed",
        "activate",
    )
    # Simulate calendar time passing without rewriting immutable issued fields
    # through the model save path.
    AgentContract.objects.filter(pk=active.pk).update(
        effective_on=date.today() - timedelta(days=30),
        expires_on=date.today() - timedelta(days=1),
    )

    with patch("apps.audit.tasks.dispatch_event.delay"):
        assert expire_due_contracts() == 1
        active.refresh_from_db()
        assert active.status == ContractStatus.EXPIRED
        assert expire_due_contracts() == 0


@pytest.mark.django_db
def test_illegal_jumps_refused(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    draft = create_draft_contract(admin, recipient=recipient, effective_on=date.today())
    with pytest.raises(TransitionRefused):
        transition(
            actor=admin,
            contract=draft,
            action="activate",
            expected_version=contract_version(draft),
            confirmed=True,
        )


@pytest.mark.django_db
def test_reopen_and_generation_error_retry(
    seeded_offices, django_capture_on_commit_callbacks
):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    ready = _ready_contract(admin, recipient)
    draft = transition(
        actor=admin,
        contract=ready,
        action="reopen",
        expected_version=contract_version(ready),
    )
    assert draft.status == ContractStatus.DRAFT

    ready2 = transition(
        actor=admin,
        contract=draft,
        action="submit_for_review",
        expected_version=contract_version(draft),
    )
    with (
        patch("apps.contract.tasks.generate_contract_pdf.delay") as pdf_delay,
        django_capture_on_commit_callbacks(execute=True),
    ):
        issued = _advance(admin, ready2, "issue")
        errored = transition(
            actor=None,
            contract=issued,
            action="mark_generation_error",
            expected_version=contract_version(issued),
        )
        retried = transition(
            actor=admin,
            contract=errored,
            action="retry_generation",
            expected_version=contract_version(errored),
        )
    assert retried.status == ContractStatus.SENT
    assert pdf_delay.call_count == 2


@pytest.mark.django_db
def test_allow_status_write_context_for_tests(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    contract = create_draft_contract(
        admin, recipient=recipient, effective_on=date.today()
    )
    contract.status = ContractStatus.TERMINATED
    with allow_status_write():
        contract.save()
    contract.refresh_from_db()
    assert contract.status == ContractStatus.TERMINATED
