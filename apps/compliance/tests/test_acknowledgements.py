"""Acknowledgement create/idempotency, access gate, replacement, and reports."""

from __future__ import annotations

import json
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.urls import reverse
from django.utils import timezone

from apps.compliance.acknowledgements import (
    access_gate,
    acknowledge,
    correct_acknowledgement,
    expire_ack_reminders,
    on_policy_published,
    open_requirements_for,
    record_access,
    report_filter_options,
    scoped_report,
    user_ack_status,
    waive,
)
from apps.compliance.action_items import collect_compliance_actions
from apps.compliance.administration import (
    build_admin_index,
    duplicate_version,
    policy_version_token,
    transition,
    update_draft,
)
from apps.compliance.audience import AudienceSelector
from apps.compliance.models import (
    PolicyAcknowledgement,
    PolicyAcknowledgementCorrection,
    PolicyAcknowledgementWaiver,
    PolicyFile,
    PolicyRequirement,
    PolicyVersionAccess,
)
from apps.compliance.notification_schedule import publish_ack_reminders
from apps.compliance.tests.factories import (
    agent,
    attach_ready_document,
    office,
    publish_policy,
    publisher,
)
from apps.notifications.contract import NotificationPriority, NotificationType
from apps.notifications.models import Notification
from apps.notifications.producers import policy_ack_reminder
from apps.notifications.resolvers import resolve_compliance_policies
from apps.notifications.service import deliver
from apps.web.action_items.contract import ActionPriority, ActionSourceContext


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def _open(user, version):
    record_access(user, version, kind=PolicyVersionAccess.Kind.DETAIL)


def _ack(user, version):
    _open(user, version)
    return acknowledge(
        user,
        version.pk,
        expected_checksum=version.content_checksum,
        disclosure_version=version.disclosure_version,
    )


def test_publish_mandatory_creates_requirement(seeded):
    version = publish_policy(title="Mandatory handbook", is_mandatory=True)
    assert PolicyRequirement.objects.filter(
        policy_version=version, is_active=True
    ).exists()
    status = user_ack_status(agent(), version)
    assert status["required"] is True
    assert status["canAcknowledge"] is True
    assert status["acknowledged"] is False


def test_acknowledge_is_idempotent(seeded):
    version = publish_policy(title="Ack me", is_mandatory=True)
    reader = agent()
    first = _ack(reader, version)
    second = _ack(reader, version)
    assert first.pk == second.pk
    assert (
        PolicyAcknowledgement.objects.filter(
            user=reader, policy_version=version
        ).count()
        == 1
    )
    status = user_ack_status(reader, version)
    assert status["acknowledged"] is True
    assert status["required"] is False
    assert status["canAcknowledge"] is False
    assert first.disclosure_text == version.acknowledgement_disclosure


def test_acknowledge_refuses_checksum_mismatch(seeded):
    version = publish_policy(title="Checksum gate", is_mandatory=True)
    reader = agent()
    _open(reader, version)
    with pytest.raises(ValidationError):
        acknowledge(
            reader,
            version.pk,
            expected_checksum="deadbeef",
            disclosure_version=version.disclosure_version,
        )


def test_acknowledge_refuses_disclosure_mismatch(seeded):
    version = publish_policy(title="Disclosure gate", is_mandatory=True)
    reader = agent()
    _open(reader, version)
    with pytest.raises(ValidationError):
        acknowledge(
            reader,
            version.pk,
            expected_checksum=version.content_checksum,
            disclosure_version=version.disclosure_version + 1,
        )


def test_acknowledge_refuses_without_detail_access(seeded):
    version = publish_policy(title="Need to open", is_mandatory=True)
    with pytest.raises(ValidationError):
        acknowledge(
            agent(),
            version.pk,
            expected_checksum=version.content_checksum,
            disclosure_version=version.disclosure_version,
        )


def test_acknowledge_requires_document_access(seeded):
    version = publish_policy(title="With file", is_mandatory=True, with_document=True)
    reader = agent()
    _open(reader, version)
    gate = access_gate(reader, version)
    assert gate["mustOpenDocument"] is True
    assert gate["documentAccessed"] is False
    with pytest.raises(ValidationError):
        acknowledge(
            reader,
            version.pk,
            expected_checksum=version.content_checksum,
            disclosure_version=version.disclosure_version,
        )
    document = PolicyFile.objects.filter(
        policy_version=version, role=PolicyFile.Role.DOCUMENT
    ).get()
    record_access(
        reader,
        version,
        kind=PolicyVersionAccess.Kind.DOCUMENT,
        policy_file=document,
    )
    row = acknowledge(
        reader,
        version.pk,
        expected_checksum=version.content_checksum,
        disclosure_version=version.disclosure_version,
    )
    assert row.pk


def test_acknowledge_cannot_target_another_user(seeded):
    version = publish_policy(title="Self only", is_mandatory=True)
    owner = agent()
    other = agent()
    _ack(owner, version)
    assert not PolicyAcknowledgement.objects.filter(
        user=other, policy_version=version
    ).exists()


def test_acknowledge_refuses_unpublished(seeded):
    version = publish_policy(title="Then retire", is_mandatory=True)
    actor = publisher()
    transition(
        actor=actor,
        version=version,
        action="retire",
        expected_version=policy_version_token(version),
    )
    version.refresh_from_db()
    reader = agent()
    _open(reader, version)
    with pytest.raises((ValidationError, Http404)):
        acknowledge(
            reader,
            version.pk,
            expected_checksum=version.content_checksum,
            disclosure_version=version.disclosure_version,
        )


def test_acknowledge_recovers_from_unique_conflict(seeded):
    version = publish_policy(title="Race", is_mandatory=True)
    reader = agent()
    existing = _ack(reader, version)
    real_filter = PolicyAcknowledgement.objects.filter
    calls = {"n": 0}

    def wrapped(*args, **kwargs):
        calls["n"] += 1
        qs = real_filter(*args, **kwargs)
        if calls["n"] == 1:
            return qs.none()
        return qs

    with patch.object(PolicyAcknowledgement.objects, "filter", wrapped):
        row = acknowledge(
            reader,
            version.pk,
            expected_checksum=version.content_checksum,
            disclosure_version=version.disclosure_version,
        )
    assert row.pk == existing.pk


def test_on_policy_published_skips_optional(seeded):
    version = publish_policy(title="Optional", is_mandatory=False)
    assert not PolicyRequirement.objects.filter(policy_version=version).exists()
    on_policy_published(version, publisher())
    assert not PolicyRequirement.objects.filter(policy_version=version).exists()


def test_publish_accepts_due_at_override(seeded):
    due = timezone.now() + timedelta(days=3)
    version = publish_policy(title="Custom due", is_mandatory=True, ack_due_at=due)
    requirement = PolicyRequirement.objects.get(policy_version=version, is_active=True)
    assert requirement.due_at is not None
    assert abs(requirement.due_at - due) < timedelta(seconds=2)


def test_disclosure_version_bumps_when_text_changes(seeded):
    actor = publisher()
    version = publish_policy(title="Draft bump", actor=actor)
    draft = duplicate_version(
        actor=actor, version=version, expected_version=policy_version_token(version)
    )
    from apps.compliance.audience import selectors_for

    selectors = [
        AudienceSelector(kind=row.kind, role=row.role, office=row.office, user=row.user)
        for row in selectors_for(draft)
    ]
    update_draft(
        actor=actor,
        version=draft,
        cleaned={
            "title": draft.title,
            "summary": draft.summary,
            "body": draft.body,
            "category": draft.category,
            "acknowledgement_disclosure": "A new disclosure.",
            "disclosure_version": draft.disclosure_version,
            "is_mandatory": True,
            "reacknowledge_on_supersede": True,
            "jurisdiction_state_codes": [],
            "display_order": 100,
        },
        selectors=selectors,
        expected_version=policy_version_token(draft),
    )
    draft.refresh_from_db()
    assert draft.disclosure_version == version.disclosure_version + 1


def test_replacement_requires_reack_by_default(seeded):
    actor = publisher()
    v1 = publish_policy(title="Family v1", is_mandatory=True, actor=actor)
    reader = agent()
    _ack(reader, v1)
    draft = duplicate_version(
        actor=actor, version=v1, expected_version=policy_version_token(v1)
    )
    for action in ("submit", "approve", "publish"):
        transition(
            actor=actor,
            version=draft,
            action=action,
            expected_version=policy_version_token(draft),
        )
        draft.refresh_from_db()
    status = user_ack_status(reader, draft)
    assert status["required"] is True
    assert status["acknowledged"] is False
    assert PolicyAcknowledgement.objects.filter(policy_version=v1, user=reader).exists()


def test_replacement_carries_forward_when_reack_disabled(seeded):
    actor = publisher()
    v1 = publish_policy(
        title="Family carry",
        is_mandatory=True,
        reacknowledge_on_supersede=False,
        actor=actor,
    )
    reader = agent()
    other = agent()
    _ack(reader, v1)
    draft = duplicate_version(
        actor=actor, version=v1, expected_version=policy_version_token(v1)
    )
    for action in ("submit", "approve", "publish"):
        transition(
            actor=actor,
            version=draft,
            action=action,
            expected_version=policy_version_token(draft),
        )
        draft.refresh_from_db()
    assert user_ack_status(reader, draft)["required"] is False
    assert user_ack_status(other, draft)["required"] is True


def test_action_items_include_pending_and_omit_completed(seeded):
    version = publish_policy(title="Due soon", is_mandatory=True)
    reader = agent()
    context = ActionSourceContext(user=reader, now=timezone.now(), access=None)
    items = collect_compliance_actions(context)
    assert any(item.source_record_id == str(version.pk) for item in items)
    assert items[0].priority == ActionPriority.HIGH
    _ack(reader, version)
    assert collect_compliance_actions(context) == []


def test_action_items_mark_overdue_critical(seeded):
    version = publish_policy(title="Overdue", is_mandatory=True)
    PolicyRequirement.objects.filter(policy_version=version, is_active=True).update(
        due_at=timezone.now() - timedelta(days=1)
    )
    reader = agent()
    items = collect_compliance_actions(
        ActionSourceContext(user=reader, now=timezone.now(), access=None)
    )
    assert items[0].priority == ActionPriority.CRITICAL


def test_waive_requires_separate_permission(seeded):
    version = publish_policy(title="Waiver gate", is_mandatory=True)
    target = agent()
    with pytest.raises(PermissionDenied):
        waive(
            target,
            user_id=target.pk,
            version_id=version.pk,
            reason="Paper already signed in the office.",
        )


def test_waive_and_revoke_keep_evidence(seeded):
    version = publish_policy(title="Waiver keep", is_mandatory=True)
    actor = publisher()
    target = agent()
    waiver = waive(
        actor,
        user_id=target.pk,
        version_id=version.pk,
        reason="Paper already signed in the office.",
    )
    assert waiver.is_active is True
    assert user_ack_status(target, version)["required"] is False
    correction = correct_acknowledgement(
        actor,
        user_id=target.pk,
        version_id=version.pk,
        kind=PolicyAcknowledgementCorrection.Kind.REVOKE_WAIVER,
        reason="Waiver was granted to the wrong person.",
    )
    waiver.refresh_from_db()
    assert waiver.is_active is False
    assert PolicyAcknowledgementWaiver.objects.filter(pk=waiver.pk).exists()
    assert correction.pk
    assert user_ack_status(target, version)["required"] is True


def test_report_summary_counts_before_status_filter(seeded):
    version = publish_policy(title="Handbook", is_mandatory=True)
    person = agent()
    actor = publisher()
    _ack(person, version)
    report = scoped_report(actor, {"policy": str(version.pk), "status": "pending"})
    assert report["summary"]["acknowledged"] >= 1
    assert all(row["status"] == "pending" for row in report["items"])


def test_report_excludes_users_outside_audience(seeded):
    version = publish_policy(
        title="Office only",
        is_mandatory=True,
        owner_office=office("fairfax-va"),
        audience=(AudienceSelector(kind="office", office=office("fairfax-va")),),
    )
    insider = agent(office=office("fairfax-va"))
    outsider = agent(email="cville@example.com", office=office("charlottesville-va"))
    actor = publisher()
    report = scoped_report(actor, {"policy": str(version.pk)})
    ids = {row["userId"] for row in report["items"]}
    assert insider.pk in ids
    assert outsider.pk not in ids


def test_admin_index_summary_counts_scoped_policies(seeded):
    actor = publisher()
    publish_policy(title="Live one", is_mandatory=True)
    payload = build_admin_index(actor, params={}, page=1)
    assert payload["summary"]["published"] >= 1
    assert "draft" in payload["summary"]
    assert "inReview" in payload["summary"]


def test_report_filter_options_include_scoped_offices_and_regions(seeded):
    actor = publisher()
    options = report_filter_options(actor)
    office_values = {row["value"] for row in options["offices"]}
    region_values = {row["value"] for row in options["regions"]}
    assert "fairfax-va" in office_values
    assert region_values
    assert all(row["label"] for row in options["regions"])


def test_json_acknowledge_post_is_idempotent(seeded, client):
    version = publish_policy(title="JSON ack", is_mandatory=True)
    reader = agent()
    client.force_login(reader)
    client.get(reverse("policy_detail", args=[version.pk]), HTTP_X_INERTIA="true")
    payload = {
        "expectedChecksum": version.content_checksum,
        "disclosureVersion": version.disclosure_version,
    }
    first = client.post(
        reverse("policy_acknowledge", args=[version.pk]),
        data=json.dumps(payload),
        content_type="application/json",
    )
    second = client.post(
        reverse("policy_acknowledge", args=[version.pk]),
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert first.status_code in {302, 303}
    assert second.status_code in {302, 303}
    assert (
        PolicyAcknowledgement.objects.filter(
            user=reader, policy_version=version
        ).count()
        == 1
    )


def test_reminders_are_idempotent_and_stop_after_ack(seeded):
    from apps.audit.events import EventEnvelope

    reader = agent()
    version = publish_policy(
        title="Remind me",
        is_mandatory=True,
        audience=(AudienceSelector(kind="user", user=reader),),
    )
    PolicyRequirement.objects.filter(policy_version=version, is_active=True).update(
        due_at=timezone.now() - timedelta(days=1)
    )
    envelope = EventEnvelope(
        id=uuid4(),
        name="policy.ack_reminder",
        version=1,
        occurred_at=timezone.now(),
        actor_id="system",
        subject=f"policy:{version.pk}:{reader.pk}",
        organization_id="",
        correlation_id=None,
        causation_id=None,
        payload={
            "policy_id": str(version.pk),
            "recipient_id": str(reader.pk),
            "due_at": timezone.now().isoformat(),
            "occurred_at": timezone.now().isoformat(),
        },
    )
    [request] = policy_ack_reminder(envelope)
    first = deliver(request)
    second = deliver(request)
    assert first is not None
    assert second is not None
    assert first.pk == second.pk
    _ack(reader, version)
    expire_ack_reminders(reader, version)
    first.refresh_from_db()
    assert first.expires_at is not None
    assert publish_ack_reminders() == 0


def test_reminder_resolver_fails_closed_after_completion(seeded):
    version = publish_policy(title="Resolver", is_mandatory=True)
    reader = agent()
    _ack(reader, version)
    note = Notification(
        recipient=reader,
        notification_type=NotificationType.ADMINISTRATIVE,
        event_key="policy.ack_reminder",
        title="A required policy acknowledgement is overdue",
        dedupe_key=f"policy-ack-reminder:{version.pk}:{reader.pk}:test",
        priority=NotificationPriority.HIGH,
        is_mandatory=True,
        source_module="compliance",
        source_record_type="policy_version",
        source_record_id=str(version.pk),
        action_key="open_policy_detail",
        action_args=[version.pk],
    )
    note.full_clean()
    note.save()
    assert resolve_compliance_policies(reader, [note]) == {}


def test_open_requirements_omit_satisfied_users(seeded):
    version = publish_policy(title="Open items", is_mandatory=True)
    reader = agent()
    assert len(open_requirements_for(reader)) == 1
    _ack(reader, version)
    assert open_requirements_for(reader) == []


def test_attach_document_helper_exists(seeded):
    version = publish_policy(title="No file")
    attach_ready_document(version)
    assert PolicyFile.objects.filter(policy_version=version).exists()
