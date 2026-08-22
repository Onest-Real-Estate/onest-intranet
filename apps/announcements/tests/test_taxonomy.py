"""Taxonomy, presentation, and notification-policy adapters.

Nothing here touches the database: the vocabulary, the badge mapping, and the
delivery policy are pure functions by design, so they are cheap to pin down
exactly.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from apps.announcements.policy import (
    FALLBACK_BEHAVIOR,
    notification_behavior,
    should_notify,
)
from apps.announcements.presentation import (
    CATEGORY_TONES,
    DEFAULT_CATEGORY_TONE,
    PRIORITY_TONES,
    category_tone,
    present_category,
    present_priority,
)
from apps.announcements.taxonomy import (
    CATEGORY_SEED,
    CATEGORY_SEED_BY_CODE,
    FALLBACK_CATEGORY_CODE,
    PRIORITY_CODES,
    PRIORITY_CODES_BY_RANK,
    PRIORITY_IMPORTANT,
    PRIORITY_NORMAL,
    PRIORITY_URGENT,
    is_known_priority,
    priority_rank,
    require_priority,
    resolve_priority,
)
from apps.notifications.contract import NotificationPriority, NotificationType

REQUIRED_CATEGORY_LABELS = {
    "Company Announcement",
    "Market Update",
    "Event",
    "Training Notice",
    "Compliance Update",
    "Office Notice",
    "Technology Notice",
    "Urgent Operational Notice",
}


class FakeCategory:
    """Stands in for the model row; resolution only reads three attributes."""

    def __init__(self, code: str, label: str, is_active: bool = True):
        self.code = code
        self.label = label
        self.is_active = is_active


# --------------------------------------------------------------------------- #
# Priority: a closed, ordered, code-owned set
# --------------------------------------------------------------------------- #


def test_priority_set_is_exactly_the_three_documented_codes():
    assert {PRIORITY_NORMAL, PRIORITY_IMPORTANT, PRIORITY_URGENT} == PRIORITY_CODES


def test_priority_ranks_are_unique_and_order_urgent_first():
    assert PRIORITY_CODES_BY_RANK == (
        PRIORITY_URGENT,
        PRIORITY_IMPORTANT,
        PRIORITY_NORMAL,
    )
    ranks = [priority_rank(code) for code in PRIORITY_CODES_BY_RANK]
    assert ranks == sorted(ranks)
    assert len(set(ranks)) == len(ranks)


def test_resolve_known_priority_round_trips_its_code():
    resolved = resolve_priority(PRIORITY_URGENT)
    assert resolved.known
    assert resolved.code == PRIORITY_URGENT
    assert resolved.requested_code == PRIORITY_URGENT
    assert resolved.rank == 1


@pytest.mark.parametrize("code", ["", None, "  ", "blocker", "P1", "critical"])
def test_unknown_priority_falls_back_to_normal_without_raising(code):
    resolved = resolve_priority(code)
    assert resolved.code == PRIORITY_NORMAL
    assert resolved.rank == priority_rank(PRIORITY_NORMAL)
    assert resolved.known is False
    assert resolved.requested_code == (code or "").strip()


def test_unknown_priority_is_logged_once_with_the_offending_code(caplog):
    with caplog.at_level("WARNING", logger="apps.announcements"):
        resolve_priority("legacy_blocker")
    assert "legacy_blocker" in caplog.text


def test_blank_priority_is_not_logged_as_a_legacy_code(caplog):
    """A draft with nothing chosen yet is normal, not a data problem."""
    with caplog.at_level("WARNING", logger="apps.announcements"):
        resolve_priority("")
    assert caplog.text == ""


def test_write_path_rejects_what_the_read_path_tolerates():
    assert require_priority(PRIORITY_IMPORTANT) == PRIORITY_IMPORTANT
    for bad in ("", None, "blocker"):
        with pytest.raises(ValidationError):
            require_priority(bad)
    assert is_known_priority("blocker") is False


# --------------------------------------------------------------------------- #
# Category catalog
# --------------------------------------------------------------------------- #


def test_catalog_carries_the_eight_required_categories():
    assert {seed.label for seed in CATEGORY_SEED} == REQUIRED_CATEGORY_LABELS


def test_category_codes_are_unique_and_ordered():
    codes = [seed.code for seed in CATEGORY_SEED]
    assert len(set(codes)) == len(codes)
    orders = [seed.display_order for seed in CATEGORY_SEED]
    assert orders == sorted(orders)


# --------------------------------------------------------------------------- #
# Presentation: semantic tones, never colors, never silent
# --------------------------------------------------------------------------- #


def test_priority_tone_map_is_total_over_the_closed_set():
    assert set(PRIORITY_TONES) == PRIORITY_CODES


def test_priority_tones_escalate_with_rank():
    assert PRIORITY_TONES[PRIORITY_URGENT] == "destructive"
    assert PRIORITY_TONES[PRIORITY_IMPORTANT] == "warning"
    assert PRIORITY_TONES[PRIORITY_NORMAL] == "neutral"


def test_every_seeded_category_has_a_deliberate_tone():
    assert set(CATEGORY_TONES) == set(CATEGORY_SEED_BY_CODE)


def test_admin_created_category_lands_on_the_documented_default_tone():
    assert category_tone("brand_new_category_from_the_admin") == DEFAULT_CATEGORY_TONE


def test_priority_payload_carries_readable_text_beside_the_tone():
    payload = present_priority(PRIORITY_URGENT)
    assert payload["label"] == "Urgent"
    assert payload["srLabel"] == "Priority: Urgent"
    assert payload["tone"] == "destructive"
    assert payload["rank"] == 1
    assert payload["known"] is True


def test_unknown_priority_payload_names_the_substitution_in_words():
    payload = present_priority("legacy_blocker")
    assert payload["code"] == PRIORITY_NORMAL
    assert payload["known"] is False
    assert "legacy_blocker" in payload["srLabel"]


def test_payloads_never_leak_colors_or_css_classes():
    for payload in (present_priority(PRIORITY_URGENT), present_category(None)):
        rendered = repr(payload)
        assert "#" not in rendered
        assert "bg-" not in rendered
        assert "text-" not in rendered


def test_missing_category_reads_as_the_placeholder_not_a_crash():
    payload = present_category(None)
    assert payload["code"] == FALLBACK_CATEGORY_CODE
    assert payload["label"] == "Uncategorized"
    assert payload["known"] is False
    assert payload["srLabel"] == "Category: not set"


def test_retired_category_keeps_its_label_and_says_it_is_retired():
    payload = present_category(
        FakeCategory("compliance_update", "Compliance Update", is_active=False)
    )
    assert payload["label"] == "Compliance Update"
    assert payload["tone"] == "warning"
    assert "retired" in payload["srLabel"]


# --------------------------------------------------------------------------- #
# Notification policy
# --------------------------------------------------------------------------- #


def test_urgent_interrupts_important_badges_normal_does_neither():
    urgent = notification_behavior(PRIORITY_URGENT)
    important = notification_behavior(PRIORITY_IMPORTANT)
    normal = notification_behavior(PRIORITY_NORMAL)

    assert (urgent.notify, important.notify, normal.notify) == (True, True, False)
    assert urgent.priority == NotificationPriority.CRITICAL
    assert important.priority == NotificationPriority.HIGH
    assert normal.priority == NotificationPriority.NORMAL


def test_policy_routes_to_the_announcement_notification_type():
    assert (
        notification_behavior(PRIORITY_URGENT).notification_type
        == NotificationType.ANNOUNCEMENT
    )


def test_policy_priority_order_matches_the_feed_order():
    """The two scales must not disagree about what is more urgent."""
    by_feed_rank = [priority_rank(code) for code in PRIORITY_CODES_BY_RANK]
    by_notification = [
        notification_behavior(code).priority for code in PRIORITY_CODES_BY_RANK
    ]
    assert by_feed_rank == sorted(by_feed_rank)
    assert by_notification == sorted(by_notification)


@pytest.mark.parametrize("code", ["", None, "legacy_blocker"])
def test_unknown_priority_uses_the_same_fallback_as_the_feed(code):
    assert notification_behavior(code) is FALLBACK_BEHAVIOR
    assert should_notify(code) is False
