"""Notification domain: idempotency, self-only state, sources, and fan-out."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.audit.events import EventEnvelope
from apps.notifications import service
from apps.notifications.actions import (
    InvalidActionArguments,
    resolve_action_href,
    validate_action_args,
)
from apps.notifications.consumers import deliver_for_event
from apps.notifications.contract import (
    InvalidNotification,
    NotificationPriority,
    NotificationRequest,
    NotificationType,
)
from apps.notifications.models import Notification
from apps.notifications.payloads import serialize_page
from apps.notifications.queries import (
    STATUS_ALL,
    STATUS_ARCHIVED,
    NotificationFilters,
    build_page,
    parse_filters,
    parse_page,
)
from apps.notifications.resolvers import ONBOARDING_MODULE
from apps.notifications.sources import (
    SourceResolution,
    register_resolver,
    resolve_sources,
)
from apps.notifications.tasks import fan_out_notifications
from apps.user.models import Office, User, UserRoleAssignment
from apps.user.roles import ADMIN, AGENT, BRANCH_MANAGER, ScopeType


def office(slug: str) -> Office:
    return Office.objects.get(slug=slug)


def assign(user: User, role: str, scope_type: str, scope_office=None) -> None:
    assignment = UserRoleAssignment(
        user=user, role=role, scope_type=scope_type, scope_office=scope_office
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()


def account(email: str, slug: str = "fairfax-va", **extra) -> User:
    user = User.objects.create_user(
        email=email,
        first_name=email.split("@")[0].title(),
        office=office(slug),
        profile_completed=True,
        **extra,
    )
    assign(user, AGENT, ScopeType.OFFICE, user.office)
    return user


def manager(email: str, slug: str = "fairfax-va") -> User:
    user = account(email, slug)
    assign(user, BRANCH_MANAGER, ScopeType.OFFICE, user.office)
    return User.objects.get(pk=user.pk)


def request_for(user: User, **overrides) -> NotificationRequest:
    payload: dict = {
        "recipient_id": user.pk,
        "notification_type": NotificationType.ACCOUNT,
        "event_key": "test.event",
        "title": "Something needs your attention",
        "dedupe_key": "test:1",
        "action_key": "open_dashboard",
    }
    payload.update(overrides)
    return NotificationRequest(**payload)


# --------------------------------------------------------------------------- #
# Contract validation
# --------------------------------------------------------------------------- #


def test_contract_rejects_unknown_type_priority_and_action():
    with pytest.raises(InvalidNotification):
        NotificationRequest(
            recipient_id=1,
            notification_type="wat",
            event_key="e",
            title="t",
            dedupe_key="k",
        )
    with pytest.raises(InvalidNotification):
        NotificationRequest(
            recipient_id=1,
            notification_type=NotificationType.LEAD,
            event_key="e",
            title="t",
            dedupe_key="k",
            priority=99,
        )
    with pytest.raises(InvalidNotification):
        NotificationRequest(
            recipient_id=1,
            notification_type=NotificationType.LEAD,
            event_key="e",
            title="t",
            dedupe_key="k",
            action_key="https://evil.example.com",
        )


def test_contract_requires_title_and_idempotency_key():
    with pytest.raises(InvalidNotification):
        NotificationRequest(
            recipient_id=1,
            notification_type=NotificationType.LEAD,
            event_key="e",
            title="   ",
            dedupe_key="k",
        )
    with pytest.raises(InvalidNotification):
        NotificationRequest(
            recipient_id=1,
            notification_type=NotificationType.LEAD,
            event_key="e",
            title="t",
            dedupe_key="   ",
        )
    with pytest.raises(InvalidNotification):
        NotificationRequest(
            recipient_id=1,
            notification_type=NotificationType.LEAD,
            event_key="  ",
            title="t",
            dedupe_key="k",
        )


def test_mandatory_notifications_need_an_action_and_never_expire():
    with pytest.raises(InvalidNotification):
        NotificationRequest(
            recipient_id=1,
            notification_type=NotificationType.TRAINING,
            event_key="e",
            title="t",
            dedupe_key="k",
            is_mandatory=True,
        )
    with pytest.raises(InvalidNotification):
        NotificationRequest(
            recipient_id=1,
            notification_type=NotificationType.TRAINING,
            event_key="e",
            title="t",
            dedupe_key="k",
            is_mandatory=True,
            action_key="open_dashboard",
            expires_at=timezone.now() + timedelta(days=1),
        )


# --------------------------------------------------------------------------- #
# Safe typed actions
# --------------------------------------------------------------------------- #


def test_action_arguments_are_validated_against_the_route_signature():
    assert validate_action_args("open_onboarding_case", ("42",)) == (42,)
    with pytest.raises(InvalidActionArguments):
        validate_action_args("open_onboarding_case", ())
    with pytest.raises(InvalidActionArguments):
        validate_action_args("open_onboarding_case", ("not-a-number",))
    with pytest.raises(InvalidActionArguments):
        validate_action_args("open_dashboard", (1,))


def test_action_resolution_fails_closed_and_never_returns_a_foreign_url():
    assert resolve_action_href("open_dashboard", []) == "/dashboard"
    assert resolve_action_href("open_onboarding_case", [7]).startswith("/operations/")
    assert resolve_action_href("unregistered", []) == ""
    assert resolve_action_href("open_onboarding_case", ["nope"]) == ""


# --------------------------------------------------------------------------- #
# Producer: idempotency and validation
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_producer_creates_one_row_per_recipient_and_idempotency_key():
    user = account("agent@example.com")
    first = service.deliver(request_for(user))
    second = service.deliver(request_for(user))

    assert first is not None and second is not None
    assert first.pk == second.pk
    assert Notification.objects.filter(recipient=user).count() == 1


@pytest.mark.django_db
def test_duplicate_batch_delivery_creates_nothing_the_second_time():
    first_user = account("one@example.com")
    second_user = account("two@example.com")
    requests = [
        request_for(first_user, dedupe_key="batch:1"),
        request_for(second_user, dedupe_key="batch:1"),
    ]

    assert service.deliver_many(requests) == 2
    assert service.deliver_many(requests) == 0
    assert Notification.objects.count() == 2


@pytest.mark.django_db
def test_producer_refuses_inactive_recipients_and_expired_deliveries():
    user = account("agent@example.com")
    user.is_active = False
    user.save(update_fields=["is_active"])
    assert service.deliver(request_for(user)) is None

    user.is_active = True
    user.save(update_fields=["is_active"])
    now = timezone.now()
    expired = request_for(
        user,
        dedupe_key="expired:1",
        available_at=now - timedelta(days=2),
        expires_at=now - timedelta(days=1),
    )
    assert service.deliver(expired, now=now) is None
    assert Notification.objects.count() == 0


@pytest.mark.django_db
def test_producer_refuses_a_source_the_recipient_may_not_read():
    """An unregistered or refusing source is a rejection, not a silent leak."""
    user = account("agent@example.com")
    assert (
        service.deliver(
            request_for(
                user,
                dedupe_key="mystery:1",
                source_module="not-registered",
                source_record_id="1",
            )
        )
        is None
    )
    assert Notification.objects.count() == 0


# --------------------------------------------------------------------------- #
# Self-only reader state and concurrency
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_a_reader_cannot_mutate_another_readers_notification():
    owner = account("owner@example.com")
    stranger = account("stranger@example.com")
    notification = service.deliver(request_for(owner))
    assert notification is not None

    assert service.mark_read(stranger, notification.public_id) is False
    assert service.mark_unread(stranger, notification.public_id) is False
    assert service.archive(stranger, notification.public_id) is False
    notification.refresh_from_db()
    assert notification.read_at is None
    assert notification.archived_at is None
    # An id that does not exist is indistinguishable from somebody else's.
    assert service.mark_read(stranger, uuid4()) is False


@pytest.mark.django_db
def test_marking_read_twice_is_idempotent_and_keeps_the_count_correct():
    user = account("agent@example.com")
    notification = service.deliver(request_for(user))
    assert notification is not None
    assert service.unread_summary(user)["unreadCount"] == 1

    assert service.mark_read(user, notification.public_id) is True
    notification.refresh_from_db()
    first_read_at = notification.read_at
    assert service.mark_read(user, notification.public_id) is True
    notification.refresh_from_db()

    assert notification.read_at == first_read_at
    assert service.unread_summary(user)["unreadCount"] == 0

    assert service.mark_unread(user, notification.public_id) is True
    assert service.unread_summary(user)["unreadCount"] == 1


@pytest.mark.django_db
def test_mark_all_read_leaves_mandatory_acknowledgements_alone():
    user = account("agent@example.com")
    service.deliver(request_for(user, dedupe_key="ordinary:1"))
    mandatory = service.deliver(
        request_for(
            user,
            dedupe_key="mandatory:1",
            is_mandatory=True,
            notification_type=NotificationType.TRAINING,
            action_key="open_action_items",
        )
    )
    assert mandatory is not None

    assert service.mark_all_read(user) == 1
    summary = service.unread_summary(user)
    assert summary == {"unreadCount": 1, "mandatoryCount": 1}

    with pytest.raises(ValidationError):
        service.archive(user, mandatory.public_id)

    service.mark_read(user, mandatory.public_id)
    assert service.archive(user, mandatory.public_id) is True


@pytest.mark.django_db
def test_expired_and_archived_rows_leave_the_badge():
    user = account("agent@example.com")
    now = timezone.now()
    service.deliver(request_for(user, dedupe_key="live:1"), now=now)
    expiring = service.deliver(
        request_for(
            user,
            dedupe_key="expiring:1",
            expires_at=now + timedelta(hours=1),
        ),
        now=now,
    )
    assert expiring is not None
    assert service.unread_summary(user, now=now)["unreadCount"] == 2

    later = now + timedelta(hours=2)
    assert service.unread_summary(user, now=later)["unreadCount"] == 1


@pytest.mark.django_db
def test_scheduled_notifications_stay_invisible_until_they_are_available():
    user = account("agent@example.com")
    now = timezone.now()
    service.deliver(
        request_for(user, dedupe_key="later:1", available_at=now + timedelta(days=1)),
        now=now,
    )
    assert service.unread_summary(user, now=now)["unreadCount"] == 0
    page = build_page(user, filters=NotificationFilters(), page=1, now=now)
    assert page.total == 0

    tomorrow = now + timedelta(days=2)
    assert service.unread_summary(user, now=tomorrow)["unreadCount"] == 1


# --------------------------------------------------------------------------- #
# Filters and bounded pagination
# --------------------------------------------------------------------------- #


def test_unknown_filter_values_fall_back_to_the_default_view():
    filters = parse_filters(
        {"status": "everything", "type": "wat", "priority": "urgent"}
    )
    assert filters.status == "unread"
    assert filters.notification_type == ""
    assert filters.priority == ""
    assert parse_page({"page": "-3"}) == 1
    assert parse_page({"page": "not-a-number"}) == 1


@pytest.mark.django_db
def test_pages_are_bounded_and_clamped_to_the_last_page():
    user = account("agent@example.com")
    now = timezone.now()
    service.deliver_many(
        [
            request_for(
                user,
                dedupe_key=f"bulk:{index}",
                available_at=now - timedelta(minutes=index),
            )
            for index in range(25)
        ],
        now=now,
    )

    first = build_page(user, filters=NotificationFilters(), page=1, now=now)
    assert (first.total, len(first.rows), first.page) == (25, 20, 1)
    second = build_page(user, filters=NotificationFilters(), page=2, now=now)
    assert len(second.rows) == 5
    clamped = build_page(user, filters=NotificationFilters(), page=99, now=now)
    assert clamped.page == 2


@pytest.mark.django_db
def test_status_filters_separate_unread_all_and_archived():
    user = account("agent@example.com")
    now = timezone.now()
    read = service.deliver(request_for(user, dedupe_key="read:1"), now=now)
    filed = service.deliver(request_for(user, dedupe_key="filed:1"), now=now)
    service.deliver(request_for(user, dedupe_key="unread:1"), now=now)
    assert read is not None and filed is not None
    service.mark_read(user, read.public_id)
    service.archive(user, filed.public_id)

    unread = build_page(user, filters=NotificationFilters(), page=1, now=now)
    assert [row.dedupe_key for row in unread.rows] == ["unread:1"]

    everything = build_page(
        user, filters=NotificationFilters(status=STATUS_ALL), page=1, now=now
    )
    assert {row.dedupe_key for row in everything.rows} == {"read:1", "unread:1"}

    archived = build_page(
        user, filters=NotificationFilters(status=STATUS_ARCHIVED), page=1, now=now
    )
    assert [row.dedupe_key for row in archived.rows] == ["filed:1"]


@pytest.mark.django_db
def test_a_page_costs_a_bounded_number_of_queries(django_assert_num_queries):
    user = account("agent@example.com")
    now = timezone.now()
    service.deliver_many(
        [request_for(user, dedupe_key=f"row:{index}") for index in range(15)], now=now
    )
    page = build_page(user, filters=NotificationFilters(), page=1, now=now)
    # One batched source resolution for the page, not one per row.
    with django_assert_num_queries(0):
        serialize_page(user, page.rows, now=now)


# --------------------------------------------------------------------------- #
# Source resolution and revocation
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_onboarding_detail_appears_only_while_the_grant_and_scope_hold():
    owner = manager("manager@example.com")
    agent = account("newagent@example.com")
    notification = service.deliver(
        NotificationRequest(
            recipient_id=owner.pk,
            notification_type=NotificationType.ADMINISTRATIVE,
            event_key="user.onboarding.owner_assigned",
            title="An onboarding case was assigned to you",
            dedupe_key="onboarding:owner:1",
            priority=NotificationPriority.HIGH,
            source_module=ONBOARDING_MODULE,
            source_record_type="user_onboarding_case",
            source_record_id=str(agent.pk),
            action_key="open_onboarding_case",
            action_args=(agent.pk,),
        )
    )
    assert notification is not None

    now = timezone.now()
    [payload] = serialize_page(owner, [notification], now=now)
    assert payload["detail"] == (
        f"Onboarding for {agent.preferred_display_name()} · {agent.office.name}"  # ty: ignore[unresolved-attribute]
    )
    assert payload["action"]["href"].endswith(f"/{agent.pk}")
    assert payload["staleAction"] is False

    # The agent transfers out of the owner's branch. Nothing rewrites the
    # notification; the detail and the destination simply stop resolving.
    agent.office = office("charlottesville-va")
    agent.save(update_fields=["office"])
    reloaded = User.objects.get(pk=owner.pk)
    [revoked] = serialize_page(reloaded, [notification], now=now)
    assert revoked["detail"] == ""
    assert revoked["action"] is None
    assert revoked["staleAction"] is True
    assert revoked["unavailableReason"]
    # The title is producer copy and names nobody, so it may survive.
    assert revoked["title"] == "An onboarding case was assigned to you"


@pytest.mark.django_db
def test_a_reader_without_the_grant_gets_no_detail():
    owner = manager("manager@example.com")
    agent = account("newagent@example.com")
    notification = service.deliver(
        NotificationRequest(
            recipient_id=owner.pk,
            notification_type=NotificationType.ADMINISTRATIVE,
            event_key="user.onboarding.owner_assigned",
            title="An onboarding case was assigned to you",
            dedupe_key="onboarding:owner:2",
            source_module=ONBOARDING_MODULE,
            source_record_type="user_onboarding_case",
            source_record_id=str(agent.pk),
            action_key="open_onboarding_case",
            action_args=(agent.pk,),
        )
    )
    assert notification is not None

    UserRoleAssignment.objects.filter(user=owner, role=BRANCH_MANAGER).delete()
    stripped = User.objects.get(pk=owner.pk)
    [payload] = serialize_page(stripped, [notification], now=timezone.now())
    assert payload["detail"] == ""
    assert payload["action"] is None


@pytest.mark.django_db
def test_a_failing_resolver_degrades_one_module_and_not_the_inbox(caplog):
    def explode(user, notifications):
        raise RuntimeError("source is down")

    register_resolver("explosive", explode)
    user = account("agent@example.com")
    notification = Notification.objects.create(
        recipient=user,
        notification_type=NotificationType.CONTRACT,
        event_key="contract.signed",
        title="A contract changed",
        dedupe_key="boom:1",
        source_module="explosive",
        source_record_id="1",
    )

    resolutions = resolve_sources(user, [notification])
    assert resolutions[notification.public_id].available is False


@pytest.mark.django_db
def test_a_notification_without_a_source_is_self_contained():
    user = account("agent@example.com")
    notification = service.deliver(request_for(user))
    assert notification is not None
    [payload] = serialize_page(user, [notification], now=timezone.now())
    assert payload["action"]["href"] == "/dashboard"
    assert payload["unavailableReason"] == ""


@pytest.mark.django_db
def test_an_archived_or_expired_row_offers_no_destination():
    user = account("agent@example.com")
    now = timezone.now()
    notification = service.deliver(
        request_for(user, dedupe_key="expiring:1", expires_at=now + timedelta(hours=1)),
        now=now,
    )
    assert notification is not None
    [payload] = serialize_page(user, [notification], now=now + timedelta(hours=2))
    assert payload["expired"] is True
    assert payload["action"] is None
    assert payload["detail"] == ""


# --------------------------------------------------------------------------- #
# Domain-event producers and background fan-out
# --------------------------------------------------------------------------- #


def envelope(name: str, payload: dict) -> EventEnvelope:
    return EventEnvelope(
        id=uuid4(),
        name=name,
        version=1,
        occurred_at=timezone.now(),
        actor_id="1",
        subject="user:1",
        organization_id="",
        correlation_id=None,
        causation_id=None,
        payload=payload,
    )


@pytest.mark.django_db
def test_owner_assignment_event_notifies_the_owner_exactly_once():
    owner = manager("manager@example.com")
    agent = account("newagent@example.com")
    event = envelope(
        "user.onboarding.owner_assigned",
        {"user_id": agent.pk, "owner_id": owner.pk},
    )

    deliver_for_event(event)
    deliver_for_event(event)

    notifications = list(Notification.objects.filter(recipient=owner))
    assert len(notifications) == 1
    assert notifications[0].source_record_id == str(agent.pk)
    assert Notification.objects.filter(recipient=agent).count() == 0


@pytest.mark.django_db
def test_account_deactivation_notifies_nobody_and_reactivation_notifies_the_user():
    user = account("agent@example.com")
    deliver_for_event(
        envelope("user.account.state_changed", {"user_id": user.pk, "is_active": False})
    )
    assert Notification.objects.count() == 0

    deliver_for_event(
        envelope("user.account.state_changed", {"user_id": user.pk, "is_active": True})
    )
    assert Notification.objects.filter(recipient=user).count() == 1


@pytest.mark.django_db
def test_audience_fan_out_is_queued_in_chunks_and_never_written_inline(
    monkeypatch, django_capture_on_commit_callbacks
):
    recipients = [account(f"agent{index}@example.com") for index in range(3)]
    queued: list[tuple] = []
    monkeypatch.setattr(
        "apps.notifications.tasks.fan_out_notifications.delay",
        lambda payload, ids: queued.append((payload, ids)),
    )
    monkeypatch.setattr(service, "FAN_OUT_CHUNK_SIZE", 2)

    template = request_for(
        recipients[0],
        dedupe_key="announcement:1",
        notification_type=NotificationType.ANNOUNCEMENT,
    )
    with django_capture_on_commit_callbacks(execute=True):
        handed_off = service.deliver_to_audience(
            template, [user.pk for user in recipients]
        )
        # Nothing is written by the caller, and nothing is queued until the
        # originating transaction actually commits.
        assert Notification.objects.count() == 0
        assert queued == []

    assert handed_off == 3
    assert Notification.objects.count() == 0
    assert len(queued) == 1

    payload, ids = queued[0]
    fan_out_notifications(payload, ids)
    # One chunk written, and the tail handed to a fresh task rather than
    # looped inline inside this worker.
    assert Notification.objects.count() == 2
    assert len(queued) == 2

    fan_out_notifications(*queued[1])
    assert Notification.objects.count() == 3
    assert len(queued) == 2


@pytest.mark.django_db
def test_replaying_a_fan_out_chunk_adds_nobody_twice():
    recipients = [account(f"agent{index}@example.com") for index in range(2)]
    payload = {
        "notification_type": NotificationType.ANNOUNCEMENT,
        "event_key": "announcement.published",
        "title": "A company announcement was published",
        "dedupe_key": "announcement:2",
        "priority": NotificationPriority.NORMAL,
        "is_mandatory": False,
        "source_module": "",
        "source_record_type": "",
        "source_record_id": "",
        "action_key": "",
        "action_args": [],
        "available_at": None,
        "expires_at": None,
    }
    ids = [user.pk for user in recipients]

    assert fan_out_notifications(payload, ids) == 2
    assert fan_out_notifications(payload, ids) == 0
    assert Notification.objects.count() == 2


@pytest.mark.django_db
def test_purging_expired_rows_leaves_live_ones_alone():
    user = account("agent@example.com")
    now = timezone.now()
    service.deliver(request_for(user, dedupe_key="live:1"), now=now)
    service.deliver(
        request_for(user, dedupe_key="gone:1", expires_at=now + timedelta(hours=1)),
        now=now,
    )

    assert service.purge_expired(before=now + timedelta(hours=2)) == 1
    assert Notification.objects.filter(recipient=user).count() == 1


@pytest.mark.django_db
def test_company_admins_keep_detail_for_agents_in_any_office():
    admin_user = account("admin@example.com")
    assign(admin_user, ADMIN, ScopeType.COMPANY)
    admin_user = User.objects.get(pk=admin_user.pk)
    agent = account("elsewhere@example.com", "charlottesville-va")
    notification = Notification.objects.create(
        recipient=admin_user,
        notification_type=NotificationType.ADMINISTRATIVE,
        event_key="user.onboarding.owner_assigned",
        title="An onboarding case was assigned to you",
        dedupe_key="onboarding:owner:3",
        source_module=ONBOARDING_MODULE,
        source_record_type="user_onboarding_case",
        source_record_id=str(agent.pk),
    )

    resolution = resolve_sources(admin_user, [notification])[notification.public_id]
    assert resolution == SourceResolution(
        available=True,
        detail=f"Onboarding for {agent.preferred_display_name()} · {agent.office.name}",  # ty: ignore[unresolved-attribute]
        action_available=True,
    )
