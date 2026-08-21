"""Preference resolution, the mandatory override, and the settings page."""

from __future__ import annotations

import json

import pytest
from django.urls import reverse

from apps.audit.models import AuditEvent
from apps.notifications import preferences
from apps.notifications.categories import (
    CATEGORY_BY_KEY,
    CATEGORY_DEFINITIONS,
    CHANNEL_EMAIL,
    CHANNEL_IN_APP,
    PREFERENCE_POLICY_VERSION,
)
from apps.notifications.contract import NotificationType
from apps.notifications.forms import NotificationPreferencesForm
from apps.notifications.models import NotificationPreference
from apps.notifications.tests.test_notifications import account, request_for


def props(response) -> dict:
    return json.loads(response.content)["props"]


def field(channel: str, category: str) -> str:
    return f"{channel}__{category}"


# --------------------------------------------------------------------------- #
# The registry
# --------------------------------------------------------------------------- #


def test_every_notification_type_has_a_category_and_a_reason_to_exist():
    for category in CATEGORY_DEFINITIONS:
        assert category.label.strip()
        assert category.description.strip()
        if category.mandatory:
            # A category nobody can switch off has to say why, or the settings
            # page shows a disabled control with no explanation.
            assert category.mandatory_reason.strip()


def test_the_in_app_channel_is_never_configurable():
    from apps.notifications.categories import CHANNEL_BY_KEY

    assert CHANNEL_BY_KEY[CHANNEL_IN_APP].configurable is False
    assert CHANNEL_BY_KEY[CHANNEL_IN_APP].locked_reason.strip()
    assert CHANNEL_BY_KEY[CHANNEL_EMAIL].configurable is True


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_a_reader_who_has_never_chosen_gets_the_documented_defaults():
    user = account("agent@example.com")
    matrix = preferences.resolved_matrix(user)

    for category in CATEGORY_DEFINITIONS:
        assert matrix[CHANNEL_IN_APP][category.key] is True
        expected = True if category.mandatory else category.default_email
        assert matrix[CHANNEL_EMAIL][category.key] is expected


@pytest.mark.django_db
def test_reading_preferences_does_not_write_a_row():
    """Delivery reads this on every send; it must not be a write path."""
    user = account("agent@example.com")
    assert preferences.stored_choices(user) == {}
    assert not NotificationPreference.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_an_explicit_choice_wins_over_the_default():
    user = account("agent@example.com")
    preferences.save_choices(user, {CHANNEL_EMAIL: {NotificationType.TRAINING: False}})

    matrix = preferences.resolved_matrix(user)
    assert matrix[CHANNEL_EMAIL][NotificationType.TRAINING] is False
    # Untouched categories are still at their defaults, not at False.
    assert (
        matrix[CHANNEL_EMAIL][NotificationType.CONTRACT]
        is CATEGORY_BY_KEY[NotificationType.CONTRACT].default_email
    )


@pytest.mark.django_db
def test_a_category_added_later_arrives_at_its_default_for_an_existing_reader():
    """The stored map holds decisions, not a frozen copy of today's catalog."""
    user = account("agent@example.com")
    preferences.save_choices(user, {CHANNEL_EMAIL: {NotificationType.TRAINING: False}})

    stored = preferences.stored_choices(user)
    assert stored == {CHANNEL_EMAIL: {NotificationType.TRAINING: False}}

    matrix = preferences.resolved_matrix(user)
    for category in CATEGORY_DEFINITIONS:
        if category.key == NotificationType.TRAINING:
            continue
        expected = True if category.mandatory else category.default_email
        assert matrix[CHANNEL_EMAIL][category.key] is expected


@pytest.mark.django_db
def test_unknown_channels_categories_and_types_are_dropped_rather_than_raising():
    """A restored backup or an older release must not break the settings page."""
    user = account("agent@example.com")
    NotificationPreference.objects.create(
        user=user,
        channels={
            "carrier_pigeon": {NotificationType.TRAINING: False},
            CHANNEL_EMAIL: {
                "retired_category": False,
                NotificationType.TRAINING: "nope",
                NotificationType.LEAD: True,
            },
        },
    )

    assert preferences.stored_choices(user) == {CHANNEL_EMAIL: {"lead": True}}
    assert preferences.resolved_matrix(user)[CHANNEL_EMAIL]["lead"] is True


@pytest.mark.django_db
def test_a_hand_edited_row_cannot_switch_off_a_mandatory_category():
    user = account("agent@example.com")
    NotificationPreference.objects.create(
        user=user,
        channels={
            CHANNEL_EMAIL: {NotificationType.ACCOUNT: False},
            CHANNEL_IN_APP: {NotificationType.TRAINING: False},
        },
    )

    assert preferences.stored_choices(user) == {}
    matrix = preferences.resolved_matrix(user)
    assert matrix[CHANNEL_EMAIL][NotificationType.ACCOUNT] is True
    assert matrix[CHANNEL_IN_APP][NotificationType.TRAINING] is True


# --------------------------------------------------------------------------- #
# The delivery question
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_an_optional_category_respects_the_stored_choice():
    user = account("agent@example.com")
    notification = request_for(
        user, notification_type=NotificationType.TRAINING, dedupe_key="t:1"
    )
    from apps.notifications import service

    row = service.deliver(notification)
    assert row is not None

    assert preferences.email_refusal(user, row) == ""
    preferences.save_choices(user, {CHANNEL_EMAIL: {NotificationType.TRAINING: False}})
    assert preferences.email_refusal(user, row) == "preference_opted_out"


@pytest.mark.django_db
def test_a_mandatory_notification_ignores_every_preference():
    from apps.notifications import service

    user = account("agent@example.com")
    row = service.deliver(
        request_for(
            user,
            notification_type=NotificationType.TRAINING,
            dedupe_key="t:mandatory",
            is_mandatory=True,
        )
    )
    assert row is not None
    preferences.save_choices(user, {CHANNEL_EMAIL: {NotificationType.TRAINING: False}})

    assert preferences.email_refusal(user, row) == ""


@pytest.mark.django_db
def test_a_mandatory_category_ignores_every_preference():
    from apps.notifications import service

    user = account("agent@example.com")
    row = service.deliver(
        request_for(user, notification_type=NotificationType.ACCOUNT, dedupe_key="a:1")
    )
    assert row is not None
    # The form refuses to store it, so write it the only way it could exist.
    NotificationPreference.objects.update_or_create(
        user=user, defaults={"channels": {CHANNEL_EMAIL: {"account": False}}}
    )

    assert preferences.email_refusal(user, row) == ""


@pytest.mark.django_db
def test_an_unrecognised_category_fails_closed():
    from apps.notifications import service

    user = account("agent@example.com")
    row = service.deliver(
        request_for(user, notification_type=NotificationType.LEAD, dedupe_key="l:1")
    )
    assert row is not None
    # A type that no longer has a reviewed category has no reviewed default.
    row.notification_type = "retired_type"

    assert preferences.email_refusal(user, row) == "unknown_category"


# --------------------------------------------------------------------------- #
# The form
# --------------------------------------------------------------------------- #


def test_the_form_has_no_field_for_a_locked_cell():
    form = NotificationPreferencesForm({})
    assert field(CHANNEL_EMAIL, NotificationType.ACCOUNT) not in form.fields
    for category in CATEGORY_DEFINITIONS:
        assert field(CHANNEL_IN_APP, category.key) not in form.fields
    assert field(CHANNEL_EMAIL, NotificationType.TRAINING) in form.fields


def test_the_form_reads_an_absent_checkbox_as_off():
    form = NotificationPreferencesForm(
        {field(CHANNEL_EMAIL, NotificationType.TRAINING): "true"}
    )
    assert form.is_valid()
    chosen = form.choices()
    assert chosen[CHANNEL_EMAIL][NotificationType.TRAINING] is True
    assert chosen[CHANNEL_EMAIL][NotificationType.CONTRACT] is False


# --------------------------------------------------------------------------- #
# The page
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_anonymous_readers_are_sent_to_sign_in(client):
    response = client.get(reverse("notification_preferences"))
    assert response.status_code == 302
    assert reverse("login") in response.headers["Location"]


@pytest.mark.django_db
def test_the_page_sends_every_cell_including_the_locked_ones(client):
    user = account("agent@example.com")
    client.force_login(user)

    payload = props(
        client.get(reverse("notification_preferences"), HTTP_X_INERTIA="true")
    )["preferences"]

    assert [item["key"] for item in payload["channels"]] == [
        CHANNEL_IN_APP,
        CHANNEL_EMAIL,
    ]
    by_key = {item["key"]: item for item in payload["categories"]}
    assert set(by_key) == {category.key for category in CATEGORY_DEFINITIONS}

    account_email = next(
        cell
        for cell in by_key[NotificationType.ACCOUNT]["channels"]
        if cell["key"] == CHANNEL_EMAIL
    )
    assert account_email["locked"] is True
    assert account_email["enabled"] is True
    assert account_email["lockedReason"].strip()

    training_email = next(
        cell
        for cell in by_key[NotificationType.TRAINING]["channels"]
        if cell["key"] == CHANNEL_EMAIL
    )
    assert training_email["locked"] is False
    assert payload["policy"]["version"] == PREFERENCE_POLICY_VERSION
    assert payload["policy"]["outdated"] is False


@pytest.mark.django_db
def test_saving_stores_the_choice_and_records_the_change(
    client, django_capture_on_commit_callbacks
):
    user = account("agent@example.com")
    client.force_login(user)

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            reverse("notification_preferences_submit"),
            {field(CHANNEL_EMAIL, NotificationType.CONTRACT): "true"},
        )
    assert response.status_code == 302

    stored = preferences.stored_choices(user)
    assert stored[CHANNEL_EMAIL][NotificationType.CONTRACT] is True
    assert stored[CHANNEL_EMAIL][NotificationType.TRAINING] is False
    assert (
        NotificationPreference.objects.get(user=user).policy_version
        == PREFERENCE_POLICY_VERSION
    )
    assert AuditEvent.objects.filter(
        action="user.notification_preferences.updated"
    ).exists()


@pytest.mark.django_db
def test_posting_a_mandatory_cell_changes_nothing(client):
    user = account("agent@example.com")
    client.force_login(user)

    client.post(
        reverse("notification_preferences_submit"),
        {
            field(CHANNEL_EMAIL, NotificationType.ACCOUNT): "false",
            field(CHANNEL_IN_APP, NotificationType.TRAINING): "false",
            field(CHANNEL_EMAIL, NotificationType.TRAINING): "true",
        },
    )

    matrix = preferences.resolved_matrix(user)
    assert matrix[CHANNEL_EMAIL][NotificationType.ACCOUNT] is True
    assert matrix[CHANNEL_IN_APP][NotificationType.TRAINING] is True
    assert matrix[CHANNEL_EMAIL][NotificationType.TRAINING] is True


@pytest.mark.django_db
def test_one_reader_never_sees_or_writes_another_readers_settings(client):
    reader = account("reader@example.com")
    stranger = account("stranger@example.com")
    preferences.save_choices(
        stranger, {CHANNEL_EMAIL: {NotificationType.CONTRACT: False}}
    )
    client.force_login(reader)

    client.post(
        reverse("notification_preferences_submit"),
        {field(CHANNEL_EMAIL, NotificationType.CONTRACT): "true"},
    )

    assert preferences.stored_choices(reader)[CHANNEL_EMAIL]["contract"] is True
    assert preferences.stored_choices(stranger)[CHANNEL_EMAIL]["contract"] is False
