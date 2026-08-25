"""Self-service My Contract page: scope, viewed, props, artifacts."""

from __future__ import annotations

import json
from datetime import date
from uuid import uuid4

import pytest
from django.core.files.base import ContentFile
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.audit.models import AuditEvent
from apps.contract.lifecycle import allow_status_write, contract_version, transition
from apps.contract.models import (
    ContractArtifact,
    ContractTemplate,
    ContractTemplateVersion,
)
from apps.contract.my_contract import (
    is_signable,
    my_contract_page_payload,
    presentation_state,
    recipient_visible_queryset,
    select_current_contract,
)
from apps.contract.services import create_draft_contract
from apps.contract.statuses import ContractStatus
from apps.contract.tests.conftest import agent, assign, company_admin, office
from apps.user.tests.test_profile import completed_user


def _published_template(*, key="ica-my") -> ContractTemplateVersion:
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


def _issued(admin, recipient, **kwargs):
    version = kwargs.pop("template_version", None) or _published_template()
    contract = create_draft_contract(
        admin,
        recipient=recipient,
        effective_on=date.today(),
        template_version=version,
        agent_split_percent="70",
        office_split_percent="30",
        mentor_percent="5",
        mentor_basis="gross_commission",
        mentor_payee=admin,
        **kwargs,
    )
    contract = transition(
        actor=admin,
        contract=contract,
        action="submit_for_review",
        expected_version=contract_version(contract),
    )
    return transition(
        actor=admin,
        contract=contract,
        action="issue",
        expected_version=contract_version(contract),
        confirmed=True,
    )


def _attach_pdf(contract, *, name="agreement.pdf") -> ContractArtifact:
    artifact = ContractArtifact(
        contract=contract,
        kind=ContractArtifact.Kind.GENERATED_PDF,
        display_name=name,
        media_type="application/pdf",
        byte_size=12,
        checksum="a" * 64,
    )
    artifact.file.save(name, ContentFile(b"%PDF-1.4 test"), save=False)
    artifact.save()
    contract.generated_pdf = artifact
    contract.save(update_fields=["generated_pdf", "updated_at"])
    return artifact


@pytest.mark.django_db
def test_page_is_self_only_and_omits_other_agents(client, seeded_offices):
    admin = company_admin(seeded_offices)
    me = agent(seeded_offices, email="me@example.com")
    assign(me, "realtor", "office", office("fairfax-va"))
    other = agent(seeded_offices, email="other@example.com", slug="harrisburg")
    mine = _issued(admin, me)
    _attach_pdf(mine)
    theirs = _issued(
        admin, other, template_version=_published_template(key="ica-other")
    )
    _attach_pdf(theirs)

    client.force_login(me)
    response = client.get(reverse("my_contract"), HTTP_X_INERTIA="true")
    assert response.status_code == 200
    page = json.loads(response.content)
    assert page["component"] == "MyContract"
    props = page["props"]
    assert props["contract"]["publicId"] == str(mine.public_id)
    assert "internalNotes" not in (props["contract"] or {})
    assert props["contract"]["commission"]["mentor"]["percent"] == "5.000"
    assert any("Mentor" in line for line in props["contract"]["summaryLines"])
    history_ids = {row["publicId"] for row in props["history"]}
    assert str(mine.public_id) in history_ids
    assert str(theirs.public_id) not in history_ids


@pytest.mark.django_db
def test_drafts_are_hidden_as_no_contract(client, seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    assign(recipient, "realtor", "office", office("fairfax-va"))
    create_draft_contract(
        admin,
        recipient=recipient,
        effective_on=date.today(),
        template_version=_published_template(),
    )
    client.force_login(recipient)
    props = json.loads(
        client.get(reverse("my_contract"), HTTP_X_INERTIA="true").content
    )["props"]
    assert props["state"] == "no_contract"
    assert props["contract"] is None
    assert props["empty"]["kind"] == "no_contract"


@pytest.mark.django_db
def test_viewed_is_recorded_once_through_lifecycle(client, seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    assign(recipient, "realtor", "office", office("fairfax-va"))
    contract = _issued(admin, recipient)
    _attach_pdf(contract)
    assert contract.status == ContractStatus.SENT

    client.force_login(recipient)
    first = client.get(reverse("my_contract"), HTTP_X_INERTIA="true")
    assert first.status_code == 200
    contract.refresh_from_db()
    assert contract.status == ContractStatus.VIEWED
    viewed_at = contract.viewed_at
    assert viewed_at is not None
    audits = AuditEvent.objects.filter(action="contract.viewed").count()
    assert audits == 1

    second = client.get(reverse("my_contract"), HTTP_X_INERTIA="true")
    assert second.status_code == 200
    contract.refresh_from_db()
    assert contract.viewed_at == viewed_at
    assert AuditEvent.objects.filter(action="contract.viewed").count() == 1


@pytest.mark.django_db
def test_viewed_not_recorded_while_pdf_generating(client, seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    assign(recipient, "realtor", "office", office("fairfax-va"))
    contract = _issued(admin, recipient)
    assert contract.generated_pdf_id is None

    client.force_login(recipient)
    props = json.loads(
        client.get(reverse("my_contract"), HTTP_X_INERTIA="true").content
    )["props"]
    assert props["state"] == "generating"
    contract.refresh_from_db()
    assert contract.status == ContractStatus.SENT
    assert not AuditEvent.objects.filter(action="contract.viewed").exists()


@pytest.mark.django_db
def test_version_query_cannot_open_another_agents_contract(client, seeded_offices):
    admin = company_admin(seeded_offices)
    me = agent(seeded_offices, email="me@example.com")
    assign(me, "realtor", "office", office("fairfax-va"))
    other = agent(seeded_offices, email="other@example.com", slug="harrisburg")
    mine = _issued(admin, me)
    _attach_pdf(mine)
    theirs = _issued(admin, other, template_version=_published_template(key="ica-x"))
    _attach_pdf(theirs)

    client.force_login(me)
    props = json.loads(
        client.get(
            reverse("my_contract"),
            {"v": str(theirs.public_id)},
            HTTP_X_INERTIA="true",
        ).content
    )["props"]
    assert props["contract"] is not None
    assert props["contract"]["publicId"] == str(mine.public_id)
    assert props["contract"]["publicId"] != str(theirs.public_id)


@pytest.mark.django_db
def test_sign_eligibility_only_for_signable_state(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    assign(recipient, "realtor", "office", office("fairfax-va"))
    contract = _issued(admin, recipient)
    assert not is_signable(contract)
    _attach_pdf(contract)
    contract.refresh_from_db()
    assert is_signable(contract)

    payload = my_contract_page_payload(recipient, record_viewed=False)
    assert payload["capabilities"]["canSign"] is True
    assert payload["capabilities"]["signingReady"] is False

    with allow_status_write():
        contract.status = ContractStatus.ACTIVE
        contract.save(update_fields=["status", "updated_at"])
    assert not is_signable(contract)


@pytest.mark.django_db
def test_generation_failed_state(client, seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    assign(recipient, "realtor", "office", office("fairfax-va"))
    contract = _issued(admin, recipient)
    contract = transition(
        actor=admin,
        contract=contract,
        action="mark_generation_error",
        expected_version=contract_version(contract),
    )
    assert presentation_state(contract) == "generation_failed"
    client.force_login(recipient)
    props = json.loads(
        client.get(reverse("my_contract"), HTTP_X_INERTIA="true").content
    )["props"]
    assert props["state"] == "generation_failed"
    assert "failed" in props["nextAction"]["title"].lower()


@pytest.mark.django_db
def test_family_history_lists_superseded_versions(client, seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    assign(recipient, "realtor", "office", office("fairfax-va"))
    first = _issued(admin, recipient)
    _attach_pdf(first)
    # Force first into superseded and mint a sibling in the same family.
    with allow_status_write():
        first.status = ContractStatus.SUPERSEDED
        first.save(update_fields=["status", "updated_at"])

    second = create_draft_contract(
        admin,
        recipient=recipient,
        effective_on=date.today(),
        template_version=_published_template(key="ica-v2"),
        agent_split_percent="75",
        office_split_percent="25",
        root_agreement=first,
        supersedes=first,
    )
    # Align family explicitly (create_draft should share family when root set).
    second.family_id = first.family_id
    second.version_number = 2
    second.save(update_fields=["family_id", "version_number", "updated_at"])
    second = transition(
        actor=admin,
        contract=second,
        action="submit_for_review",
        expected_version=contract_version(second),
    )
    second = transition(
        actor=admin,
        contract=second,
        action="issue",
        expected_version=contract_version(second),
        confirmed=True,
    )
    _attach_pdf(second)

    client.force_login(recipient)
    props = json.loads(
        client.get(reverse("my_contract"), HTTP_X_INERTIA="true").content
    )["props"]
    assert props["contract"]["publicId"] == str(second.public_id)
    assert {row["versionNumber"] for row in props["history"]} >= {1, 2}


@pytest.mark.django_db
def test_preview_and_download_are_authorized_self_only(
    client, settings, tmp_path, seeded_offices
):
    settings.MEDIA_ROOT = str(tmp_path)
    admin = company_admin(seeded_offices)
    me = agent(seeded_offices, email="me@example.com")
    assign(me, "realtor", "office", office("fairfax-va"))
    outsider = completed_user(email="outsider@example.com", office=office("harrisburg"))
    contract = _issued(admin, me)
    artifact = _attach_pdf(contract)

    client.force_login(me)
    preview = client.get(
        reverse(
            "my_contract_artifact_preview",
            kwargs={
                "public_id": contract.public_id,
                "artifact_public_id": artifact.public_id,
            },
        )
    )
    assert preview.status_code == 200
    assert preview["Content-Disposition"].startswith("inline")
    assert preview["X-Frame-Options"] == "SAMEORIGIN"
    assert b"".join(preview.streaming_content) == b"%PDF-1.4 test"

    download = client.get(
        reverse(
            "agent_contract_artifact_download",
            kwargs={
                "public_id": contract.public_id,
                "artifact_public_id": artifact.public_id,
            },
        )
    )
    assert download.status_code == 200
    assert "attachment" in download["Content-Disposition"]

    client.force_login(outsider)
    denied = client.get(
        reverse(
            "my_contract_artifact_preview",
            kwargs={
                "public_id": contract.public_id,
                "artifact_public_id": artifact.public_id,
            },
        )
    )
    assert denied.status_code == 404


@pytest.mark.django_db
def test_serialized_props_omit_internal_notes_and_admin_ids(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    assign(recipient, "realtor", "office", office("fairfax-va"))
    contract = _issued(
        admin,
        recipient,
        internal_notes="Broker only",
    )
    _attach_pdf(contract)
    payload = my_contract_page_payload(recipient, record_viewed=False)
    body = payload["contract"]
    assert body is not None
    assert "internalNotes" not in body
    assert "recipientId" not in body
    assert "createdById" not in body
    assert "mentor" in body["commission"]
    assert "referral" in body["commission"]
    assert "payeeId" not in body["commission"]["mentor"]


@pytest.mark.django_db
def test_my_contract_page_query_count_bounded(client, seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    assign(recipient, "realtor", "office", office("fairfax-va"))
    root = _issued(admin, recipient)
    _attach_pdf(root)
    for index in range(3):
        sibling = create_draft_contract(
            admin,
            recipient=recipient,
            effective_on=date.today(),
            template_version=_published_template(key=f"ica-hist-{index}"),
            agent_split_percent="70",
            office_split_percent="30",
            root_agreement=root,
        )
        sibling.family_id = root.family_id
        sibling.version_number = index + 2
        sibling.save(update_fields=["family_id", "version_number", "updated_at"])
        sibling = transition(
            actor=admin,
            contract=sibling,
            action="submit_for_review",
            expected_version=contract_version(sibling),
        )
        sibling = transition(
            actor=admin,
            contract=sibling,
            action="issue",
            expected_version=contract_version(sibling),
            confirmed=True,
        )
        with allow_status_write():
            sibling.status = ContractStatus.SUPERSEDED
            sibling.save(update_fields=["status", "updated_at"])

    client.force_login(recipient)
    with CaptureQueriesContext(connection) as context:
        client.get(reverse("my_contract"), HTTP_X_INERTIA="true")
    # Shared Inertia middleware + auth + lifecycle mark_viewed dominate; history
    # must stay flat rather than N+1 per family row.
    assert len(context) < 110


@pytest.mark.django_db
def test_select_current_prefers_active(seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    older = _issued(admin, recipient)
    with allow_status_write():
        older.status = ContractStatus.SUPERSEDED
        older.save(update_fields=["status", "updated_at"])
    newer = _issued(admin, recipient, template_version=_published_template(key="new"))
    with allow_status_write():
        newer.status = ContractStatus.ACTIVE
        newer.save(update_fields=["status", "updated_at"])
    current = select_current_contract(recipient)
    assert current is not None
    assert current.pk == newer.pk
    assert recipient_visible_queryset(recipient).count() == 2


@pytest.mark.django_db
def test_anonymous_is_redirected(client):
    response = client.get(reverse("my_contract"))
    assert response.status_code == 302
    assert reverse("login") in response.url


@pytest.mark.django_db
def test_bogus_version_uuid_does_not_500(client, seeded_offices):
    recipient = agent(seeded_offices)
    assign(recipient, "realtor", "office", office("fairfax-va"))
    client.force_login(recipient)
    response = client.get(
        reverse("my_contract"),
        {"v": "not-a-uuid"},
        HTTP_X_INERTIA="true",
    )
    assert response.status_code == 200
    props = json.loads(response.content)["props"]
    assert props["state"] == "no_contract"


@pytest.mark.django_db
def test_unknown_version_uuid_falls_back_safely(client, seeded_offices):
    admin = company_admin(seeded_offices)
    recipient = agent(seeded_offices)
    assign(recipient, "realtor", "office", office("fairfax-va"))
    mine = _issued(admin, recipient)
    _attach_pdf(mine)
    client.force_login(recipient)
    props = json.loads(
        client.get(
            reverse("my_contract"),
            {"v": str(uuid4())},
            HTTP_X_INERTIA="true",
        ).content
    )["props"]
    assert props["contract"]["publicId"] == str(mine.public_id)
