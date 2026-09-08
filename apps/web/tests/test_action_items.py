"""Action-item contract: sources, ordering, dedupe, completion, isolation."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.web.action_items import (
    ACTION_SOURCE_DEFINITIONS,
    ActionItem,
    ActionPriority,
    ActionSourceContext,
    ActionType,
    build_queue,
    collect_items,
    order_items,
    queue_for_user,
)
from apps.web.action_items.ordering import dedupe, is_overdue
from apps.web.dashboard import WidgetStatus, build_context, widget_payload
from apps.web.dashboard.registry import WIDGET_BY_KEY
from apps.web.tests.test_dashboard_metrics import make_user


def _now() -> datetime:
    return timezone.make_aware(
        datetime(2026, 8, 21, 12, 0), ZoneInfo("America/New_York")
    )


def _item(**overrides: object) -> ActionItem:
    base: dict[str, object] = {
        "id": "a",
        "dedupe_key": "a",
        "title": "Do the thing",
        "type": ActionType.PROFILE,
        "priority": ActionPriority.NORMAL,
        "due_at": None,
        "source_module": "test",
        "source_record_type": "fixture",
        "source_record_id": "1",
        "context": "detail",
        "cta_label": "Open",
        "cta_href": "/profile",
        "assignee_id": 1,
    }
    base.update(overrides)
    return ActionItem(
        id=str(base["id"]),
        dedupe_key=str(base["dedupe_key"]),
        title=str(base["title"]),
        type=str(base["type"]),
        priority=int(base["priority"]),  # type: ignore[arg-type]
        due_at=base["due_at"],  # type: ignore[arg-type]
        source_module=str(base["source_module"]),
        source_record_type=str(base["source_record_type"]),
        source_record_id=str(base["source_record_id"]),
        context=str(base["context"]),
        cta_label=str(base["cta_label"]),
        cta_href=str(base["cta_href"]),
        assignee_id=int(base["assignee_id"]),  # type: ignore[arg-type]
        state=str(base.get("state", "open")),
    )


# --------------------------------------------------------------------------- #
# Ordering and deduplication
# --------------------------------------------------------------------------- #


def test_overdue_sorts_before_dated_and_undated_peers():
    now = _now()
    overdue = _item(
        id="overdue",
        dedupe_key="overdue",
        priority=ActionPriority.LOW,
        due_at=now - timedelta(days=1),
    )
    high = _item(
        id="high",
        dedupe_key="high",
        priority=ActionPriority.HIGH,
        due_at=now + timedelta(days=1),
    )
    undated = _item(
        id="undated",
        dedupe_key="undated",
        priority=ActionPriority.CRITICAL,
    )
    ordered = order_items([high, undated, overdue], now=now)
    assert [item.id for item in ordered] == ["overdue", "undated", "high"]


def test_same_priority_orders_by_due_then_stable_id():
    now = _now()
    later = _item(
        id="b",
        dedupe_key="b",
        due_at=now + timedelta(days=2),
        priority=ActionPriority.NORMAL,
    )
    sooner = _item(
        id="a",
        dedupe_key="a",
        due_at=now + timedelta(days=1),
        priority=ActionPriority.NORMAL,
    )
    ordered = order_items([later, sooner], now=now)
    assert [item.id for item in ordered] == ["a", "b"]


def test_duplicate_dedupe_keys_collapse_to_the_first_after_sort():
    now = _now()
    first = _item(
        id="contract:1:a",
        dedupe_key="contract:1",
        priority=ActionPriority.HIGH,
        due_at=now - timedelta(hours=1),
    )
    second = _item(
        id="contract:1:b",
        dedupe_key="contract:1",
        priority=ActionPriority.NORMAL,
        due_at=now + timedelta(days=1),
    )
    ordered = order_items([second, first], now=now)
    assert len(ordered) == 1
    assert ordered[0].id == "contract:1:a"


def test_dedupe_preserves_order_of_first_seen_keys():
    rows = [
        _item(id="1", dedupe_key="x"),
        _item(id="2", dedupe_key="y"),
        _item(id="3", dedupe_key="x"),
    ]
    assert [item.id for item in dedupe(rows)] == ["1", "2"]


def test_completed_state_cannot_be_constructed():
    with pytest.raises(ValueError, match="Only open action items"):
        _item(state="completed")


# --------------------------------------------------------------------------- #
# Profile source — completion derived from the user record
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_incomplete_profile_emits_a_typed_action_item():
    user = make_user("gaps@example.com")
    # make_user leaves optional professional fields empty.
    context = ActionSourceContext(
        user=user, access=build_context(user).access, now=_now()
    )
    items, partial = collect_items(context)
    assert partial is False
    profile_items = [item for item in items if item.type == ActionType.PROFILE]
    assert len(profile_items) == 1
    item = profile_items[0]
    assert item.cta_href == reverse("profile")
    assert item.assignee_id == user.pk
    assert item.source_record_id == str(user.pk)


@pytest.mark.django_db
def test_complete_profile_with_distant_licence_emits_nothing(monkeypatch):
    user = make_user("complete@example.com")
    user.license_expires_on = date(2030, 1, 1)
    user.save(update_fields=["license_expires_on"])
    monkeypatch.setattr(
        "apps.web.action_items.sources.profile_completeness",
        lambda _user: {
            "completed": 19,
            "total": 19,
            "percent": 100,
            "missing": [],
        },
    )
    context = ActionSourceContext(
        user=user, access=build_context(user).access, now=_now()
    )
    items, _partial = collect_items(context)
    assert items == []


@pytest.mark.django_db
def test_expired_licence_is_critical_and_overdue():
    user = make_user("expired@example.com")
    user.license_expires_on = date(2026, 8, 1)
    user.save(update_fields=["license_expires_on"])
    now = _now()
    context = ActionSourceContext(user=user, access=build_context(user).access, now=now)
    items, _ = collect_items(context)
    licence = next(item for item in items if item.type == ActionType.COMPLIANCE)
    assert licence.priority == ActionPriority.CRITICAL
    assert is_overdue(licence, now=now)
    assert licence.dedupe_key == f"profile:license:{user.pk}"


@pytest.mark.django_db
def test_expired_and_expiring_licence_share_a_dedupe_key():
    """One licence signal per user — expired wins by sort before dedupe."""
    user = make_user("one-licence@example.com")
    user.license_expires_on = date(2026, 8, 1)
    user.save(update_fields=["license_expires_on"])
    result = queue_for_user(user, build_context(user).access, now=_now(), feed_limit=0)
    assert result.status == WidgetStatus.READY
    assert result.data is not None
    licence_rows = [
        row for row in result.data["items"] if row["type"] == ActionType.COMPLIANCE
    ]
    assert len(licence_rows) == 1
    assert licence_rows[0]["priority"] == "critical"


# --------------------------------------------------------------------------- #
# Composer: cap, empty, partial failure, self-only scope
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_dashboard_widget_caps_items_and_keeps_total(monkeypatch):
    user = make_user("capped@example.com")
    now = _now()

    def many(_context):
        return [
            _item(
                id=f"row-{index}",
                dedupe_key=f"row-{index}",
                priority=ActionPriority.NORMAL,
                due_at=now + timedelta(days=index),
                assignee_id=user.pk,
            )
            for index in range(8)
        ]

    monkeypatch.setattr(
        "apps.web.action_items.registry.ACTION_SOURCE_DEFINITIONS",
        [
            type(ACTION_SOURCE_DEFINITIONS[0])(
                key="fixture", collector=many, available=True
            )
        ],
    )
    context = build_context(user, at=now)
    payload = widget_payload(WIDGET_BY_KEY["action_items"], context)
    assert payload["status"] == WidgetStatus.READY
    assert payload["data"]["total"] == 8
    assert len(payload["data"]["items"]) == 5
    assert payload["meta"]["truncated"] is True
    assert payload["data"]["viewAllHref"] == reverse("action_items_queue")
    assert payload["version"] == 2


@pytest.mark.django_db
def test_caught_up_user_gets_an_empty_state_not_unavailable(monkeypatch):
    user = make_user("caught-up@example.com")

    monkeypatch.setattr(
        "apps.web.action_items.registry.ACTION_SOURCE_DEFINITIONS",
        [
            type(ACTION_SOURCE_DEFINITIONS[0])(
                key="fixture", collector=lambda _ctx: [], available=True
            )
        ],
    )
    result = queue_for_user(user, build_context(user).access, now=_now(), feed_limit=5)
    assert result.status == WidgetStatus.EMPTY
    assert result.empty_state is not None


@pytest.mark.django_db
def test_source_failure_is_isolated_and_opaque(monkeypatch, caplog):
    user = make_user("partial@example.com")
    now = _now()

    def boom(_context):
        raise RuntimeError("secret record ON-9999")

    def ok(_context):
        return [
            _item(
                id="ok",
                dedupe_key="ok",
                assignee_id=user.pk,
                cta_href=reverse("profile"),
            )
        ]

    monkeypatch.setattr(
        "apps.web.action_items.registry.ACTION_SOURCE_DEFINITIONS",
        [
            type(ACTION_SOURCE_DEFINITIONS[0])(
                key="broken", collector=boom, available=True
            ),
            type(ACTION_SOURCE_DEFINITIONS[0])(key="ok", collector=ok, available=True),
        ],
    )
    result = build_queue(
        ActionSourceContext(user=user, access=build_context(user).access, now=now),
        feed_limit=5,
    )
    assert result.status == WidgetStatus.READY
    assert result.meta.get("partialFailure") is True
    assert "ON-9999" not in str(result.data)
    assert "broken" not in str(result.meta)
    assert "secret record" in caplog.text


@pytest.mark.django_db
def test_all_sources_failing_yields_retryable_unavailable(monkeypatch):
    user = make_user("all-fail@example.com")

    def boom(_context):
        raise RuntimeError("nope")

    monkeypatch.setattr(
        "apps.web.action_items.registry.ACTION_SOURCE_DEFINITIONS",
        [
            type(ACTION_SOURCE_DEFINITIONS[0])(
                key="broken", collector=boom, available=True
            )
        ],
    )
    result = queue_for_user(user, build_context(user).access, now=_now(), feed_limit=5)
    assert result.status == WidgetStatus.UNAVAILABLE
    assert result.unavailable is not None
    assert result.unavailable.retryable is True


@pytest.mark.django_db
def test_queue_only_assigns_items_to_the_signed_in_user():
    reader = make_user("reader@example.com")
    other = make_user("other@example.com")
    other.license_expires_on = date(2026, 8, 1)
    other.save(update_fields=["license_expires_on"])

    result = queue_for_user(
        reader, build_context(reader).access, now=_now(), feed_limit=0
    )
    assert result.status in {WidgetStatus.READY, WidgetStatus.EMPTY}
    if result.status == WidgetStatus.READY:
        assert result.data is not None
        for row in result.data["items"]:
            assert row["assigneeId"] == reader.pk
            assert row["source"]["recordId"] == str(reader.pk)


@pytest.mark.django_db
def test_full_queue_page_rechecks_auth_and_rederives_items(client):
    user = make_user("queue-page@example.com")
    client.force_login(user)
    response = client.get(reverse("action_items_queue"), HTTP_X_INERTIA="true")
    assert response.status_code == 200
    props = json.loads(response.content)["props"]
    assert props["queue"] is not None
    assert props["queue"]["total"] >= 1
    assert all(row["ctaHref"] == reverse("profile") for row in props["queue"]["items"])


@pytest.mark.django_db
def test_stale_cta_still_requires_destination_policy(client):
    """Following the profile CTA without a session is rejected at the endpoint."""
    response = client.get(reverse("profile"), HTTP_X_INERTIA="true")
    assert response.status_code in {302, 401, 403}


@pytest.mark.django_db
def test_action_items_widget_is_no_longer_a_permanent_unavailable():
    user = make_user("live-widget@example.com")
    payload = widget_payload(WIDGET_BY_KEY["action_items"], build_context(user))
    assert payload["status"] in {WidgetStatus.READY, WidgetStatus.EMPTY}
