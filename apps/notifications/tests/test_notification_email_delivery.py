"""The email pipeline: after-commit queueing, idempotency, revalidation, retry."""

from __future__ import annotations

from datetime import timedelta
from typing import cast

import pytest
from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.notifications import delivery, preferences, service
from apps.notifications.categories import CHANNEL_EMAIL
from apps.notifications.contract import NotificationRequest, NotificationType
from apps.notifications.models import Notification, NotificationEmail
from apps.notifications.resolvers import ONBOARDING_MODULE
from apps.notifications.tasks import (
    dispatch_notification_emails,
    send_notification_email,
    sweep_notification_emails,
)
from apps.notifications.tests.test_notifications import (
    account,
    manager,
    office,
    request_for,
)
from apps.user.models import User


def html_part(message) -> str:
    """The HTML alternative of a sent message, as text."""
    return str(cast(EmailMultiAlternatives, message).alternatives[0][0])


def ledger(notification: Notification) -> NotificationEmail:
    return NotificationEmail.objects.get(
        notification=notification, channel=CHANNEL_EMAIL
    )


def optional(user: User, **overrides) -> Notification:
    """An optional-category notification with no source module."""
    payload = {
        "notification_type": NotificationType.TRAINING,
        "dedupe_key": "training:1",
        "title": "A course was assigned to you",
    }
    payload.update(overrides)
    row = service.deliver(request_for(user, **payload))
    assert row is not None
    return row


def onboarding_case(owner: User, agent: User) -> Notification:
    row = service.deliver(
        NotificationRequest(
            recipient_id=owner.pk,
            notification_type=NotificationType.ADMINISTRATIVE,
            event_key="user.onboarding.owner_assigned",
            title="An onboarding case was assigned to you",
            dedupe_key=f"onboarding:owner:{agent.pk}",
            source_module=ONBOARDING_MODULE,
            source_record_type="user_onboarding_case",
            source_record_id=str(agent.pk),
            action_key="open_onboarding_case",
            action_args=(agent.pk,),
        )
    )
    assert row is not None
    return row


# --------------------------------------------------------------------------- #
# Queueing
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_delivering_a_notification_opens_one_ledger_row():
    user = account("agent@example.com")
    row = optional(user)

    entry = ledger(row)
    assert entry.status == NotificationEmail.Status.PENDING
    assert entry.delivery_key == row.dedupe_key
    assert entry.recipient_id == user.pk
    assert entry.attempts == 0
    assert mail.outbox == []


@pytest.mark.django_db
def test_nothing_is_queued_until_the_producing_transaction_commits(
    monkeypatch, django_capture_on_commit_callbacks
):
    user = account("agent@example.com")
    queued: list[list[str]] = []
    monkeypatch.setattr(
        "apps.notifications.tasks.dispatch_notification_emails.delay",
        lambda ids: queued.append(list(ids)),
    )

    with django_capture_on_commit_callbacks(execute=True):
        row = optional(user)
        # Committed row, nothing on the queue yet: a rollback here mails nobody.
        assert queued == []

    assert len(queued) == 1
    assert queued[0] == [str(ledger(row).public_id)]


@pytest.mark.django_db
def test_an_opted_out_category_is_recorded_as_suppressed_rather_than_skipped():
    """A silent skip is not answerable later; a ledger row is."""
    user = account("agent@example.com")
    preferences.save_choices(user, {CHANNEL_EMAIL: {NotificationType.TRAINING: False}})

    entry = ledger(optional(user))
    assert entry.status == NotificationEmail.Status.SUPPRESSED
    assert entry.suppression_reason == "preference_opted_out"
    assert entry.resolved_at is not None


@pytest.mark.django_db
def test_a_replayed_producer_never_opens_a_second_delivery():
    user = account("agent@example.com")
    request = request_for(
        user, notification_type=NotificationType.TRAINING, dedupe_key="training:1"
    )
    service.deliver(request)
    service.deliver(request)
    service.deliver(request)

    assert Notification.objects.filter(recipient=user).count() == 1
    assert NotificationEmail.objects.filter(recipient=user).count() == 1


@pytest.mark.django_db
def test_requeueing_the_same_batch_adds_nothing():
    user = account("agent@example.com")
    row = optional(user)

    assert delivery.queue_emails([row]) == [str(ledger(row).public_id)]
    assert NotificationEmail.objects.filter(notification=row).count() == 1


@pytest.mark.django_db
def test_a_fan_out_chunk_opens_one_delivery_per_recipient():
    recipients = [account(f"agent{index}@example.com") for index in range(3)]
    created = service.deliver_many(
        [
            request_for(
                user,
                notification_type=NotificationType.ANNOUNCEMENT,
                dedupe_key="announcement:1",
            )
            for user in recipients
        ]
    )

    assert created == 3
    assert NotificationEmail.objects.count() == 3
    assert set(NotificationEmail.objects.values_list("status", flat=True)) == {
        NotificationEmail.Status.PENDING
    }


# --------------------------------------------------------------------------- #
# Sending
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_a_queued_delivery_sends_once_and_settles():
    user = account("agent@example.com")
    row = optional(user)
    entry = ledger(row)

    assert delivery.attempt_delivery(entry.public_id) == NotificationEmail.Status.SENT
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [user.email]

    entry.refresh_from_db()
    assert entry.status == NotificationEmail.Status.SENT
    assert entry.attempts == 1
    assert entry.sent_at is not None
    assert entry.to_email == user.email

    # Re-running the task is a no-op, not a second message.
    assert delivery.attempt_delivery(entry.public_id) == NotificationEmail.Status.SENT
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_a_row_another_worker_is_holding_is_left_alone():
    user = account("agent@example.com")
    entry = ledger(optional(user))
    NotificationEmail.objects.filter(pk=entry.pk).update(
        status=NotificationEmail.Status.SENDING,
        attempts=1,
        last_attempt_at=timezone.now(),
    )

    assert (
        delivery.attempt_delivery(entry.public_id) == NotificationEmail.Status.SENDING
    )
    assert mail.outbox == []


@pytest.mark.django_db
def test_a_scheduled_notification_waits_for_its_availability():
    user = account("agent@example.com")
    later = timezone.now() + timedelta(days=3)
    row = optional(user, available_at=later)
    entry = ledger(row)

    assert entry.next_attempt_at == later
    assert (
        delivery.attempt_delivery(entry.public_id) == NotificationEmail.Status.PENDING
    )
    assert mail.outbox == []
    assert delivery.due_delivery_ids() == []


# --------------------------------------------------------------------------- #
# Revalidation immediately before send
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (
            lambda row, user: Notification.objects.filter(pk=row.pk).update(
                read_at=timezone.now()
            ),
            delivery.SUPPRESSED_ALREADY_READ,
        ),
        (
            lambda row, user: Notification.objects.filter(pk=row.pk).update(
                archived_at=timezone.now()
            ),
            delivery.SUPPRESSED_ARCHIVED,
        ),
        (
            # Expiry has to stay after availability, so move both back.
            lambda row, user: Notification.objects.filter(pk=row.pk).update(
                available_at=timezone.now() - timedelta(hours=2),
                expires_at=timezone.now() - timedelta(minutes=1),
            ),
            delivery.SUPPRESSED_EXPIRED,
        ),
        (
            lambda row, user: User.objects.filter(pk=user.pk).update(is_active=False),
            delivery.SUPPRESSED_RECIPIENT_INACTIVE,
        ),
        (
            lambda row, user: User.objects.filter(pk=user.pk).update(email=""),
            delivery.SUPPRESSED_NO_ADDRESS,
        ),
    ],
)
def test_state_that_changed_after_queueing_stops_the_send(mutate, expected):
    user = account("agent@example.com")
    row = optional(user)
    entry = ledger(row)

    mutate(row, user)

    assert (
        delivery.attempt_delivery(entry.public_id)
        == NotificationEmail.Status.SUPPRESSED
    )
    entry.refresh_from_db()
    assert entry.suppression_reason == expected
    assert mail.outbox == []


@pytest.mark.django_db
def test_opting_out_between_queueing_and_sending_stops_the_send():
    user = account("agent@example.com")
    entry = ledger(optional(user))
    preferences.save_choices(user, {CHANNEL_EMAIL: {NotificationType.TRAINING: False}})

    assert (
        delivery.attempt_delivery(entry.public_id)
        == NotificationEmail.Status.SUPPRESSED
    )
    ledger_row = NotificationEmail.objects.get(pk=entry.pk)
    assert ledger_row.suppression_reason == "preference_opted_out"
    assert mail.outbox == []


@pytest.mark.django_db
def test_a_withdrawn_source_grant_stops_the_send():
    owner = manager("manager@example.com")
    agent = account("newagent@example.com")
    entry = ledger(onboarding_case(owner, agent))

    # The agent transfers out of the owner's branch after the row was queued.
    agent.office = office("charlottesville-va")
    agent.save(update_fields=["office"])

    assert (
        delivery.attempt_delivery(entry.public_id)
        == NotificationEmail.Status.SUPPRESSED
    )
    entry.refresh_from_db()
    assert entry.suppression_reason == delivery.SUPPRESSED_SOURCE
    assert mail.outbox == []


@pytest.mark.django_db
def test_an_address_changed_after_queueing_is_the_one_used():
    user = account("agent@example.com")
    entry = ledger(optional(user))
    User.objects.filter(pk=user.pk).update(email="moved@example.com")

    assert delivery.attempt_delivery(entry.public_id) == NotificationEmail.Status.SENT
    assert mail.outbox[0].to == ["moved@example.com"]
    entry.refresh_from_db()
    assert entry.to_email == "moved@example.com"


@pytest.mark.django_db
def test_a_mandatory_notice_is_sent_even_to_a_reader_who_opted_out():
    user = account("agent@example.com")
    preferences.save_choices(user, {CHANNEL_EMAIL: {NotificationType.TRAINING: False}})
    row = optional(user, dedupe_key="training:required", is_mandatory=True)

    entry = ledger(row)
    assert entry.status == NotificationEmail.Status.PENDING
    assert delivery.attempt_delivery(entry.public_id) == NotificationEmail.Status.SENT
    assert len(mail.outbox) == 1


# --------------------------------------------------------------------------- #
# Failure, retry, and recovery
# --------------------------------------------------------------------------- #


def _break_smtp(monkeypatch) -> None:
    def explode(self, *args, **kwargs):
        raise OSError("smtp unavailable")

    monkeypatch.setattr(EmailMultiAlternatives, "send", explode)


@pytest.mark.django_db
def test_a_failed_send_backs_off_and_leaves_the_notification_untouched(monkeypatch):
    user = account("agent@example.com")
    row = optional(user)
    entry = ledger(row)
    _break_smtp(monkeypatch)

    now = timezone.now()
    assert (
        delivery.attempt_delivery(entry.public_id, now=now)
        == NotificationEmail.Status.FAILED
    )

    entry.refresh_from_db()
    assert entry.attempts == 1
    assert entry.last_error
    assert entry.next_attempt_at == now + timedelta(seconds=delivery._BACKOFF[0])
    # The domain fact is untouched: the reader's inbox does not know or care.
    row.refresh_from_db()
    assert row.read_at is None
    assert Notification.objects.filter(pk=row.pk).exists()


@pytest.mark.django_db
def test_a_delivery_gives_up_after_the_attempt_budget_and_is_audited(
    monkeypatch, django_capture_on_commit_callbacks
):
    user = account("agent@example.com")
    entry = ledger(optional(user))
    _break_smtp(monkeypatch)

    with django_capture_on_commit_callbacks(execute=True):
        for _ in range(delivery.MAX_ATTEMPTS):
            NotificationEmail.objects.filter(pk=entry.pk).update(next_attempt_at=None)
            status = delivery.attempt_delivery(entry.public_id)

    assert status == NotificationEmail.Status.DEAD
    entry.refresh_from_db()
    assert entry.attempts == delivery.MAX_ATTEMPTS
    assert entry.next_attempt_at is None
    assert entry.resolved_at is not None
    event = AuditEvent.objects.get(action="notification.email.failed")
    assert event.outcome == AuditEvent.Outcome.FAILURE
    assert event.target_snapshot["attempts"] == delivery.MAX_ATTEMPTS


@pytest.mark.django_db
def test_a_worker_that_died_mid_send_is_reclaimed_not_stranded():
    user = account("agent@example.com")
    entry = ledger(optional(user))
    stale = timezone.now() - delivery.STALE_CLAIM - timedelta(minutes=1)
    NotificationEmail.objects.filter(pk=entry.pk).update(
        status=NotificationEmail.Status.SENDING, attempts=1, last_attempt_at=stale
    )

    assert delivery.reclaim_stalled() == 1
    entry.refresh_from_db()
    assert entry.status == NotificationEmail.Status.FAILED
    # The attempt it consumed still counts, so a crash loop exhausts the
    # budget and dies rather than retrying for ever.
    assert entry.attempts == 1
    assert str(entry.public_id) in delivery.due_delivery_ids()


@pytest.mark.django_db
def test_the_sweep_rebuilds_the_queue_from_the_database(monkeypatch):
    user = account("agent@example.com")
    entry = ledger(optional(user))
    queued: list[str] = []
    monkeypatch.setattr(
        "apps.notifications.tasks.send_notification_email.delay", queued.append
    )

    # The dispatch task was never delivered — a broker outage, a lost message.
    assert sweep_notification_emails() == 1
    assert queued == [str(entry.public_id)]


@pytest.mark.django_db
def test_a_backing_off_delivery_is_not_swept_before_it_is_due():
    user = account("agent@example.com")
    entry = ledger(optional(user))
    NotificationEmail.objects.filter(pk=entry.pk).update(
        status=NotificationEmail.Status.FAILED,
        next_attempt_at=timezone.now() + timedelta(minutes=30),
    )

    assert delivery.due_delivery_ids() == []


@pytest.mark.django_db
def test_settled_deliveries_are_never_swept_again():
    user = account("agent@example.com")
    entry = ledger(optional(user))
    for status in (
        NotificationEmail.Status.SENT,
        NotificationEmail.Status.SUPPRESSED,
        NotificationEmail.Status.DEAD,
    ):
        NotificationEmail.objects.filter(pk=entry.pk).update(
            status=status, next_attempt_at=None
        )
        assert delivery.due_delivery_ids() == []


@pytest.mark.django_db
def test_dispatch_chunks_the_queue_and_hands_on_the_tail(monkeypatch):
    monkeypatch.setattr(delivery, "DISPATCH_CHUNK_SIZE", 2)
    sent: list[str] = []
    chunks: list[list[str]] = []
    monkeypatch.setattr(
        "apps.notifications.tasks.send_notification_email.delay", sent.append
    )
    monkeypatch.setattr(
        "apps.notifications.tasks.dispatch_notification_emails.delay",
        lambda ids: chunks.append(list(ids)),
    )

    assert dispatch_notification_emails(["a", "b", "c"]) == 2
    assert sent == ["a", "b"]
    assert chunks == [["c"]]


@pytest.mark.django_db
def test_the_send_task_reports_the_rows_status(monkeypatch):
    user = account("agent@example.com")
    entry = ledger(optional(user))

    assert (
        send_notification_email(str(entry.public_id)) == NotificationEmail.Status.SENT
    )


@pytest.mark.django_db
def test_deleting_a_notification_takes_its_delivery_ledger_with_it():
    """Housekeeping must not leave orphaned rows the sweep would retry for ever."""
    user = account("agent@example.com")
    row = optional(user)
    entry = ledger(row)

    row.delete()

    assert not NotificationEmail.objects.filter(pk=entry.pk).exists()
    assert delivery.due_delivery_ids() == []


# --------------------------------------------------------------------------- #
# What the message is allowed to contain
# --------------------------------------------------------------------------- #


def test_only_a_rooted_in_app_path_becomes_a_link():
    assert delivery_absolute("/notifications").endswith("/notifications")
    # Protocol-relative and absolute URLs are somebody else's server.
    assert delivery_absolute("//evil.example.com/steal") == ""
    assert delivery_absolute("https://evil.example.com/steal") == ""
    assert delivery_absolute("javascript:alert(1)") == ""
    assert delivery_absolute("") == ""


def delivery_absolute(path: str) -> str:
    from apps.notifications.emails import absolute_url

    return absolute_url(path)


@pytest.mark.django_db
def test_the_message_carries_the_title_a_link_and_nothing_from_the_record():
    owner = manager("manager@example.com")
    agent = account("newagent@example.com", last_name="Confidentialsurname")
    row = onboarding_case(owner, agent)

    assert delivery.attempt_delivery(ledger(row).public_id) == (
        NotificationEmail.Status.SENT
    )
    message = mail.outbox[0]
    html = html_part(message)

    # The fixed producer title is fine — it names nobody.
    assert row.title in message.subject
    assert row.title in message.body
    # The source-resolved detail is not. It is only ever shown to a signed-in
    # reader whose access is re-checked at that moment.
    assert agent.preferred_display_name() not in message.body
    assert agent.preferred_display_name() not in html
    assert agent.email not in message.body

    # The destination is an in-app path on this deployment, not a file URL.
    assert f"/operations/new-agents/{agent.pk}" in message.body
    assert "http" in message.body
    assert message.subject.count("\n") == 0


@pytest.mark.django_db
def test_producer_copy_is_escaped_in_the_html_part():
    user = account("agent@example.com")
    row = optional(
        user,
        dedupe_key="training:escaped",
        title="<script>alert(1)</script> course assigned",
    )

    delivery.attempt_delivery(ledger(row).public_id)
    html = html_part(mail.outbox[0])

    assert "<script>" not in html
    assert "&lt;script&gt;" in html


@pytest.mark.django_db
def test_an_optional_message_says_how_to_turn_it_off_and_a_required_one_says_why_not():
    user = account("agent@example.com")
    optional_row = optional(user, dedupe_key="training:optional")
    delivery.attempt_delivery(ledger(optional_row).public_id)
    assert "Choose which notifications reach your inbox" in mail.outbox[0].body
    assert "/notifications/preferences" in mail.outbox[0].body

    required_row = optional(user, dedupe_key="training:required", is_mandatory=True)
    delivery.attempt_delivery(ledger(required_row).public_id)
    assert "cannot be turned off" in mail.outbox[1].body


@pytest.mark.django_db
def test_a_notification_whose_action_no_longer_reverses_still_links_to_the_centre():
    user = account("agent@example.com")
    row = optional(user)
    Notification.objects.filter(pk=row.pk).update(action_key="retired_action")

    assert delivery.attempt_delivery(ledger(row).public_id) == (
        NotificationEmail.Status.SENT
    )
    assert "/notifications" in mail.outbox[0].body
