"""Office confirmation, contact resolution, and notification handoff."""

from __future__ import annotations

import json
from datetime import timedelta
from importlib import import_module

import pytest
from django.apps import apps as django_apps
from django.urls import reverse
from django.utils import timezone

from apps.audit.events import EventEnvelope
from apps.audit.models import DomainEvent
from apps.notifications.consumers import deliver_for_event
from apps.notifications.models import Notification, NotificationEmail
from apps.notifications.payloads import serialize_page
from apps.user.models import (
    Office,
    OfficeContactAssignment,
    User,
    UserOnboardingCase,
    UserRoleAssignment,
)
from apps.user.roles import BRANCH_ADMIN, ScopeType
from apps.user.services.onboarding_office import (
    OFFICE_HANDOFF_EVENT,
    OfficeAdminResolutionLevel,
    OfficeHandoffDeliveryUnavailable,
    office_confirmation_payload,
    resolve_office_administrator,
)
from apps.user.services.onboarding_state import agent_journey_payload, journey_for_user
from apps.user.tests.test_onboarding_profile import (
    agent,
    complete_profile,
    fill_sections,
    upload_headshot,
)

INERTIA = {"HTTP_X_INERTIA": "true"}


@pytest.fixture
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


def office(slug: str = "fairfax-va") -> Office:
    return Office.assignable_queryset().get(slug=slug)


def clear_branch_admins() -> None:
    OfficeContactAssignment.objects.filter(
        assignment_type=OfficeContactAssignment.AssignmentType.ADMIN
    ).delete()


def administrator(email: str, *, office_scope: Office) -> User:
    user = User.objects.create_user(
        email=email,
        first_name=email.split("@")[0].title(),
        phone_number="(703) 555-0199",
        office=office_scope,
        profile_completed=True,
    )
    assignment = UserRoleAssignment(
        user=user,
        role=BRANCH_ADMIN,
        scope_type=ScopeType.OFFICE,
        scope_office=office_scope,
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()
    return user


def contact(
    user: User,
    *,
    contact_office: Office,
    primary: bool = False,
    starts_at=None,
    ends_at=None,
) -> OfficeContactAssignment:
    return OfficeContactAssignment.objects.create(
        office=contact_office,
        user=user,
        assignment_type=OfficeContactAssignment.AssignmentType.ADMIN,
        is_primary=primary,
        starts_at=starts_at,
        ends_at=ends_at,
    )


def envelope(event: DomainEvent) -> EventEnvelope:
    return EventEnvelope(
        id=event.id,
        name=event.name,
        version=event.version,
        occurred_at=event.occurred_at,
        actor_id=event.actor_id,
        subject=event.subject,
        organization_id=event.organization_id,
        correlation_id=event.correlation_id,
        causation_id=event.causation_id,
        payload=event.payload,
    )


@pytest.mark.django_db
def test_resolution_prefers_primary_current_office_admin():
    clear_branch_admins()
    selected = office()
    first = administrator("first@example.com", office_scope=selected)
    primary = administrator("primary@example.com", office_scope=selected)
    contact(first, contact_office=selected)
    contact(primary, contact_office=selected, primary=True)

    resolved = resolve_office_administrator(selected)

    assert resolved is not None
    assert resolved.user == primary
    assert resolved.level == OfficeAdminResolutionLevel.OFFICE


@pytest.mark.django_db
def test_resolution_uses_deterministic_first_current_admin_without_primary():
    clear_branch_admins()
    selected = office()
    later = administrator("zebra@example.com", office_scope=selected)
    first = administrator("alpha@example.com", office_scope=selected)
    contact(later, contact_office=selected)
    contact(first, contact_office=selected)

    resolved = resolve_office_administrator(selected)

    assert resolved is not None
    assert resolved.user == first


@pytest.mark.django_db
def test_resolution_ignores_inactive_future_and_expired_contacts_then_falls_back():
    clear_branch_admins()
    selected = office()
    today = timezone.localdate()
    inactive = administrator("inactive@example.com", office_scope=selected)
    inactive.is_active = False
    inactive.save(update_fields=["is_active"])
    future = administrator("future@example.com", office_scope=selected)
    expired = administrator("expired@example.com", office_scope=selected)
    regional = administrator("regional@example.com", office_scope=selected)
    contact(inactive, contact_office=selected, primary=True)
    contact(future, contact_office=selected, starts_at=today + timedelta(days=1))
    contact(expired, contact_office=selected, ends_at=today - timedelta(days=1))
    assert selected.region is not None
    contact(regional, contact_office=selected.region)

    resolved = resolve_office_administrator(selected, on_date=today)

    assert resolved is not None
    assert resolved.user == regional
    assert resolved.level == OfficeAdminResolutionLevel.REGION


@pytest.mark.django_db
def test_resolution_uses_company_fallback_and_is_one_query(django_assert_num_queries):
    clear_branch_admins()
    selected = office()
    head = Office.objects.get(kind=Office.Kind.HEAD_OFFICE)
    company = administrator("company@example.com", office_scope=selected)
    contact(company, contact_office=head)

    with django_assert_num_queries(1):
        resolved = resolve_office_administrator(selected)

    assert resolved is not None
    assert resolved.user == company
    assert resolved.level == OfficeAdminResolutionLevel.COMPANY


@pytest.mark.django_db
def test_office_choices_and_selected_contact_have_a_fixed_two_query_cost(
    django_assert_num_queries,
):
    clear_branch_admins()
    selected = office()
    admin = administrator("bounded@example.com", office_scope=selected)
    contact(admin, contact_office=selected, primary=True)

    with django_assert_num_queries(2):
        choices = list(Office.assignable_queryset())
        chosen = next(item for item in choices if item.pk == selected.pk)
        payload = office_confirmation_payload(chosen)

    assert payload["administrator"]["name"] == "Bounded"


@pytest.mark.django_db
def test_preview_exposes_public_office_and_only_resolved_contact(client):
    clear_branch_admins()
    selected = office()
    selected.street_address = "4000 Chain Bridge Road"
    selected.city = "Fairfax"
    selected.state = "VA"
    selected.zip_code = "22030"
    selected.main_phone = "(703) 555-0100"
    selected.public_email = "fairfax@example.com"
    selected.office_hours = ["Monday–Friday: 9–5"]
    selected.parking_instructions = "Internal parking secret"
    selected.access_instructions = "Internal access secret"
    selected.save()
    admin = administrator("admin@example.com", office_scope=selected)
    contact(admin, contact_office=selected, primary=True)
    user = agent(email="preview@example.com")
    client.force_login(user)

    response = client.get(reverse("onboarding_office_preview", args=[selected.pk]))
    payload = response.json()

    assert response.status_code == 200
    assert payload["office"]["streetAddress"] == "4000 Chain Bridge Road"
    assert payload["administrator"]["name"] == "Admin"
    assert "parkingInstructions" not in json.dumps(payload)
    assert "accessInstructions" not in json.dumps(payload)
    assert "Internal parking secret" not in json.dumps(payload)


@pytest.mark.django_db
def test_office_payload_reports_missing_address_without_inventing_one():
    clear_branch_admins()
    selected = office()
    Office.objects.filter(pk=selected.pk).update(
        street_address="", city="", state="", zip_code=""
    )
    selected.refresh_from_db()

    payload = office_confirmation_payload(selected)

    assert payload["office"]["streetAddress"] == ""
    assert payload["office"]["city"] == ""
    assert payload["office"]["state"] == ""
    assert payload["office"]["zipCode"] == ""


@pytest.mark.django_db
def test_preview_rejects_inactive_or_nonassignable_office(client):
    selected = office()
    user = agent(email="preview@example.com")
    client.force_login(user)
    Office.objects.filter(pk=selected.pk).update(is_active=False)

    response = client.get(reverse("onboarding_office_preview", args=[selected.pk]))

    assert response.status_code == 404


@pytest.mark.django_db
def test_preview_is_limited_to_authenticated_incomplete_agents(client):
    selected = office()
    url = reverse("onboarding_office_preview", args=[selected.pk])

    assert client.get(url).status_code == 401
    ordinary = User.objects.create_user(email="ordinary@example.com")
    client.force_login(ordinary)
    assert client.get(url).status_code == 404
    completed = agent(email="completed@example.com", profile_completed=True)
    client.force_login(completed)
    assert client.get(url).status_code == 404


@pytest.mark.django_db
def test_finalization_creates_one_scoped_redacted_handoff(client, media_root):
    clear_branch_admins()
    selected = office("charlottesville-va")
    admin = administrator("branch-admin@example.com", office_scope=selected)
    contact(admin, contact_office=selected, primary=True)
    user = agent(email="new-agent@example.com")
    client.force_login(user)

    complete_profile(client)

    case = UserOnboardingCase.objects.get(user=user)
    assert case.owner == admin
    assert case.office_handoff_state == UserOnboardingCase.OfficeHandoffState.PENDING
    event = DomainEvent.objects.get(name=OFFICE_HANDOFF_EVENT)
    assert event.payload == {
        "user_id": user.pk,
        "office_id": selected.pk,
        "recipient_id": admin.pk,
        "onboarding_version": user.onboarding_version,
    }
    sensitive = json.dumps(event.payload)
    for forbidden in (
        "1 Main St",
        "202.555.0100",
        "123-456-789",
        "headshot",
    ):
        assert forbidden not in sensitive

    deliver_for_event(envelope(event))
    deliver_for_event(envelope(event))

    notification = Notification.objects.get(
        recipient=admin, event_key=OFFICE_HANDOFF_EVENT
    )
    assert notification.action_key == "open_onboarding_case"
    assert notification.action_args == [user.pk]
    [notification_payload] = serialize_page(admin, [notification], now=timezone.now())
    # The agent's preferred name, as every other notification addresses people.
    assert notification_payload["detail"] == (
        "Onboarding for Bobby B · Charlottesville VA"
    )
    serialized_notification = json.dumps(notification_payload)
    for forbidden in ("1 Main St", "202.555.0100", "123-456-789", "headshot"):
        assert forbidden not in serialized_notification
    assert (
        Notification.objects.filter(
            recipient=admin, event_key=OFFICE_HANDOFF_EVENT
        ).count()
        == 1
    )
    case.refresh_from_db()
    assert case.office_handoff_state == UserOnboardingCase.OfficeHandoffState.NOTIFIED
    assert (
        NotificationEmail.objects.filter(notification=notification)
        .exclude(status=NotificationEmail.Status.SUPPRESSED)
        .exists()
    )
    journey = agent_journey_payload(journey_for_user(User.objects.get(pk=user.pk)))
    assert journey["officeHandoff"]["message"] == (
        "We notified Branch-Admin. Their onboarding workspace is ready."
    )
    assert journey["officeHandoff"]["delivery"]["channels"]


@pytest.mark.django_db
def test_existing_explicit_owner_is_preserved(client, media_root):
    clear_branch_admins()
    selected = office("charlottesville-va")
    resolved = administrator("resolved@example.com", office_scope=selected)
    explicit = administrator("explicit@example.com", office_scope=selected)
    contact(resolved, contact_office=selected, primary=True)
    user = agent(email="owned-agent@example.com")
    client.force_login(user)
    upload_headshot(client)
    fill_sections(client)
    case = UserOnboardingCase.objects.get(user=user)
    case.owner = explicit
    case.save(update_fields=["owner"])

    response = client.post(
        reverse("onboarding_profile_finalize"),
        {
            "confirm_review": "true",
            "expected_onboarding_version": user.onboarding_version,
        },
        **INERTIA,
    )

    assert response.status_code == 302
    case.refresh_from_db()
    assert case.owner == explicit


@pytest.mark.django_db
def test_missing_contact_releases_profile_gate_but_records_truthful_blocker(
    client, media_root
):
    clear_branch_admins()
    user = agent(email="no-contact@example.com")
    client.force_login(user)

    complete_profile(client)

    case = UserOnboardingCase.objects.get(user=user)
    assert case.office_handoff_state == (
        UserOnboardingCase.OfficeHandoffState.NOTIFICATION_FAILED
    )
    assert not DomainEvent.objects.filter(name=OFFICE_HANDOFF_EVENT).exists()
    refreshed = User.objects.select_related("office").get(pk=user.pk)
    journey = journey_for_user(refreshed)
    assert journey.required_setup_complete is True
    assert any(
        blocker["key"] == "office_handoff_failed" for blocker in journey.blockers
    )
    payload = office_confirmation_payload(refreshed.office)
    assert payload["administrator"] is None
    assert payload["support"]["available"] is True


@pytest.mark.django_db
def test_handoff_event_failure_rolls_back_profile_and_required_setup(
    client, media_root, monkeypatch
):
    clear_branch_admins()
    selected = office("charlottesville-va")
    admin = administrator("admin@example.com", office_scope=selected)
    contact(admin, contact_office=selected, primary=True)
    user = agent(email="rollback@example.com")
    client.force_login(user)
    upload_headshot(client)
    fill_sections(client)

    def fail_publish(*args, **kwargs):
        raise RuntimeError("outbox write failed")

    monkeypatch.setattr("apps.audit.events.publish", fail_publish)
    with pytest.raises(RuntimeError, match="outbox write failed"):
        client.post(
            reverse("onboarding_profile_finalize"),
            {
                "confirm_review": "true",
                "expected_onboarding_version": user.onboarding_version,
            },
            **INERTIA,
        )

    user.refresh_from_db()
    case = UserOnboardingCase.objects.get(user=user)
    assert user.profile_completed is False
    assert case.required_setup_completed_at is None
    assert not DomainEvent.objects.filter(name=OFFICE_HANDOFF_EVENT).exists()


@pytest.mark.django_db
def test_unauthorized_recipient_records_retryable_failure_then_recovers(
    client, media_root
):
    clear_branch_admins()
    selected = office("charlottesville-va")
    admin = User.objects.create_user(
        email="unscoped@example.com",
        first_name="Unscoped",
        office=selected,
        profile_completed=True,
    )
    contact(admin, contact_office=selected, primary=True)
    user = agent(email="retry-agent@example.com")
    client.force_login(user)
    complete_profile(client)
    event = DomainEvent.objects.get(name=OFFICE_HANDOFF_EVENT)

    with pytest.raises(OfficeHandoffDeliveryUnavailable):
        deliver_for_event(envelope(event))
    case = UserOnboardingCase.objects.get(user=user)
    assert case.office_handoff_state == (
        UserOnboardingCase.OfficeHandoffState.NOTIFICATION_FAILED
    )
    assert not Notification.objects.filter(recipient=admin).exists()

    assignment = UserRoleAssignment(
        user=admin,
        role=BRANCH_ADMIN,
        scope_type=ScopeType.OFFICE,
        scope_office=selected,
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()
    deliver_for_event(envelope(event))

    case.refresh_from_db()
    assert case.office_handoff_state == UserOnboardingCase.OfficeHandoffState.NOTIFIED
    assert Notification.objects.filter(recipient=admin).count() == 1


@pytest.mark.django_db
def test_office_correlation_backfill_is_explicit_and_idempotent():
    selected = office()
    user = User.objects.create_user(
        email="legacy-office@example.com",
        office=selected,
        profile_completed=True,
        onboarding_version=3,
    )
    case = UserOnboardingCase.objects.create(
        user=user,
        office_confirmed_at=timezone.now(),
        required_setup_completed_at=timezone.now(),
        office_handoff_state=UserOnboardingCase.OfficeHandoffState.NOTIFIED,
    )
    migration = import_module(
        "apps.user.migrations.0032_useronboardingcase_office_confirmation_version_and_more"
    )

    migration.backfill_onboarding_office_correlations(django_apps, None)
    migration.backfill_onboarding_office_correlations(django_apps, None)

    case.refresh_from_db()
    assert case.office_confirmed_for == selected
    assert case.office_confirmation_version == 3
    assert case.office_handoff_office == selected
    assert case.office_handoff_onboarding_version == 3
