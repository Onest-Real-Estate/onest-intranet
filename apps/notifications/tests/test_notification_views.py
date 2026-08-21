"""The notification centre over HTTP: self-only access, filters, mutations."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.notifications import service
from apps.notifications.contract import NotificationRequest, NotificationType
from apps.notifications.models import Notification
from apps.notifications.tests.test_notifications import account, request_for


def props(response) -> dict:
    return json.loads(response.content)["props"]


def inertia(client, url: str):
    return client.get(url, HTTP_X_INERTIA="true")


@pytest.mark.django_db
def test_anonymous_readers_are_sent_to_sign_in(client):
    response = client.get(reverse("notifications"))
    assert response.status_code == 302
    assert reverse("login") in response.headers["Location"]


@pytest.mark.django_db
def test_the_summary_endpoint_refuses_anonymous_callers_with_json(client):
    response = client.get(reverse("notification_summary"))
    assert response.status_code == 401
    assert response.json()["error"] == "authentication_required"


@pytest.mark.django_db
def test_the_centre_lists_only_the_signed_in_readers_notifications(client):
    reader = account("reader@example.com")
    stranger = account("stranger@example.com")
    service.deliver(request_for(reader, dedupe_key="mine:1", title="Mine"))
    service.deliver(request_for(stranger, dedupe_key="theirs:1", title="Theirs"))
    client.force_login(reader)

    payload = props(inertia(client, reverse("notifications")))
    titles = [row["title"] for row in payload["notificationList"]["items"]]
    assert titles == ["Mine"]
    assert payload["notificationList"]["pagination"]["totalItems"] == 1
    assert payload["summary"] == {"unreadCount": 1, "mandatoryCount": 0}


@pytest.mark.django_db
def test_filters_narrow_the_list_and_survive_a_mutation(client):
    reader = account("reader@example.com")
    now = timezone.now()
    service.deliver(
        request_for(
            reader,
            dedupe_key="training:1",
            title="Training due",
            notification_type=NotificationType.TRAINING,
        ),
        now=now,
    )
    lead = service.deliver(
        request_for(
            reader,
            dedupe_key="lead:1",
            title="New lead",
            notification_type=NotificationType.LEAD,
        ),
        now=now,
    )
    assert lead is not None
    client.force_login(reader)

    filtered = props(
        inertia(client, f"{reverse('notifications')}?type={NotificationType.LEAD}")
    )
    assert [row["title"] for row in filtered["notificationList"]["items"]] == [
        "New lead"
    ]
    assert filtered["notificationList"]["filters"]["type"] == NotificationType.LEAD

    response = client.post(
        reverse("notification_state", args=[lead.public_id]),
        {"action": "read", "type": NotificationType.LEAD, "status": "all"},
    )
    assert response.status_code == 302
    assert response.headers["Location"].startswith(reverse("notifications"))
    assert f"type={NotificationType.LEAD}" in response.headers["Location"]


@pytest.mark.django_db
def test_read_unread_and_archive_are_idempotent_over_http(client):
    reader = account("reader@example.com")
    notification = service.deliver(request_for(reader))
    assert notification is not None
    client.force_login(reader)
    url = reverse("notification_state", args=[notification.public_id])

    for _ in range(2):
        assert client.post(url, {"action": "read"}).status_code == 302
    notification.refresh_from_db()
    assert notification.read_at is not None

    for _ in range(2):
        assert client.post(url, {"action": "unread"}).status_code == 302
    notification.refresh_from_db()
    assert notification.read_at is None

    for _ in range(2):
        assert client.post(url, {"action": "archive"}).status_code == 302
    notification.refresh_from_db()
    assert notification.archived_at is not None


@pytest.mark.django_db
def test_one_reader_cannot_touch_another_readers_notification_over_http(client):
    owner = account("owner@example.com")
    stranger = account("stranger@example.com")
    notification = service.deliver(request_for(owner))
    assert notification is not None
    client.force_login(stranger)

    response = client.post(
        reverse("notification_state", args=[notification.public_id]),
        {"action": "read"},
    )
    # A redirect to their own (empty) centre: the response cannot be used to
    # learn that somebody else's notification exists.
    assert response.status_code == 302
    notification.refresh_from_db()
    assert notification.read_at is None


@pytest.mark.django_db
def test_an_unsupported_action_is_refused_without_changing_anything(client):
    reader = account("reader@example.com")
    notification = service.deliver(request_for(reader))
    assert notification is not None
    client.force_login(reader)

    response = client.post(
        reverse("notification_state", args=[notification.public_id]),
        {"action": "delete"},
        HTTP_X_INERTIA="true",
    )
    assert response.status_code == 422
    assert props(response)["errors"]["form"]
    notification.refresh_from_db()
    assert notification.read_at is None
    assert notification.archived_at is None


@pytest.mark.django_db
def test_mandatory_notifications_resist_archiving_until_they_are_read(client):
    reader = account("reader@example.com")
    mandatory = service.deliver(
        NotificationRequest(
            recipient_id=reader.pk,
            notification_type=NotificationType.TRAINING,
            event_key="training.assigned",
            title="Required training was assigned",
            dedupe_key="training:mandatory:1",
            is_mandatory=True,
            action_key="open_action_items",
        )
    )
    assert mandatory is not None
    client.force_login(reader)
    url = reverse("notification_state", args=[mandatory.public_id])

    refused = client.post(url, {"action": "archive"}, HTTP_X_INERTIA="true")
    assert refused.status_code == 422
    assert props(refused)["errors"]["form"]
    mandatory.refresh_from_db()
    assert mandatory.archived_at is None

    assert client.post(url, {"action": "read"}).status_code == 302
    assert client.post(url, {"action": "archive"}).status_code == 302
    mandatory.refresh_from_db()
    assert mandatory.archived_at is not None


@pytest.mark.django_db
def test_mark_all_read_clears_the_badge_but_not_the_acknowledgements(client):
    reader = account("reader@example.com")
    service.deliver(request_for(reader, dedupe_key="ordinary:1"))
    service.deliver(
        NotificationRequest(
            recipient_id=reader.pk,
            notification_type=NotificationType.TRAINING,
            event_key="training.assigned",
            title="Required training was assigned",
            dedupe_key="training:mandatory:2",
            is_mandatory=True,
            action_key="open_action_items",
        )
    )
    client.force_login(reader)

    assert client.post(reverse("notification_read_all")).status_code == 302
    assert client.get(reverse("notification_summary")).json() == {
        "unreadCount": 1,
        "mandatoryCount": 1,
    }


@pytest.mark.django_db
def test_the_summary_endpoint_answers_only_about_its_caller(client):
    reader = account("reader@example.com")
    stranger = account("stranger@example.com")
    service.deliver(request_for(stranger, dedupe_key="theirs:1"))
    service.deliver(request_for(reader, dedupe_key="mine:1"))
    client.force_login(reader)

    assert client.get(reverse("notification_summary")).json() == {
        "unreadCount": 1,
        "mandatoryCount": 0,
    }


@pytest.mark.django_db
def test_the_header_badge_rides_along_with_every_inertia_page(client):
    reader = account("reader@example.com")
    service.deliver(request_for(reader))
    client.force_login(reader)

    shared = props(inertia(client, reverse("dashboard")))["notifications"]
    assert shared["unreadCount"] == 1
    assert shared["href"] == reverse("notifications")

    # And on the centre itself: its list prop is deliberately named something
    # else so it cannot shadow the shared badge on this page alone.
    centre = props(inertia(client, reverse("notifications")))
    assert centre["notifications"]["unreadCount"] == 1
    assert "items" in centre["notificationList"]


@pytest.mark.django_db
def test_expired_notifications_never_reach_the_page_body(client):
    reader = account("reader@example.com")
    now = timezone.now()
    service.deliver(
        request_for(
            reader,
            dedupe_key="expiring:1",
            title="Time-limited notice",
            available_at=now - timedelta(hours=2),
            expires_at=now + timedelta(hours=1),
        ),
        now=now,
    )
    # Time passes: the row is untouched, its expiry simply falls behind now.
    Notification.objects.filter(dedupe_key="expiring:1").update(
        expires_at=now - timedelta(hours=1)
    )
    client.force_login(reader)

    payload = props(inertia(client, f"{reverse('notifications')}?status=all"))
    [row] = payload["notificationList"]["items"]
    assert row["expired"] is True
    assert row["detail"] == ""
    assert row["action"] is None
    assert payload["summary"]["unreadCount"] == 0


@pytest.mark.django_db
def test_rendering_a_full_page_stays_within_a_bounded_query_budget(
    client, django_assert_max_num_queries
):
    reader = account("reader@example.com")
    now = timezone.now()
    service.deliver_many(
        [request_for(reader, dedupe_key=f"row:{index}") for index in range(20)],
        now=now,
    )
    client.force_login(reader)

    # Session, user, effective access, shell props, the page itself: a fixed
    # budget that must not grow with the number of rows on the page.
    with django_assert_max_num_queries(25):
        response = inertia(client, reverse("notifications"))
    assert len(props(response)["notificationList"]["items"]) == 20
    assert Notification.objects.filter(recipient=reader).count() == 20
