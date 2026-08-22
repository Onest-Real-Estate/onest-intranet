"""The dev seed, and the negatives it is supposed to demonstrate.

The point of testing a seed is not that it runs. It is that the rows it
labels "should NOT be visible" really are invisible — otherwise the seed
quietly teaches a developer that a broken predicate is working.
"""

from __future__ import annotations

import pytest

from apps.announcements.audience import visible_announcements
from apps.announcements.models import Announcement, AnnouncementAudience
from apps.announcements.seed import SPECS, seed_announcements
from apps.announcements.services import order_for_feed
from apps.announcements.taxonomy import PRIORITY_CODES
from apps.user.models import Office, UserRoleAssignment
from apps.user.tests.test_profile import completed_user


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups
    from apps.user.user_seed import seed_users

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()
    # Users first: role and individual selectors only mean something once
    # somebody holds the role or has the account.
    seed_users(password="seed-test", ensure_prerequisites=False)
    seed_announcements()


def fairfax_realtor():
    user = completed_user(
        email="seed.reader@example.com", office=Office.objects.get(slug="fairfax-va")
    )
    assignment = UserRoleAssignment(
        user=user,
        role="realtor",
        scope_type="office",
        scope_office=Office.objects.get(slug="fairfax-va"),
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()
    return user


def test_the_seed_creates_every_spec(seeded):
    assert Announcement.objects.count() == len(SPECS)


def test_the_seed_is_idempotent(seeded):
    before = Announcement.objects.count()
    before_selectors = AnnouncementAudience.objects.count()
    seed_announcements()
    seed_announcements()
    assert Announcement.objects.count() == before
    assert AnnouncementAudience.objects.count() == before_selectors


def test_the_seed_covers_every_selector_kind(seeded):
    kinds = set(AnnouncementAudience.objects.values_list("kind", flat=True))
    assert kinds == set(AnnouncementAudience.Kind.values)


def test_the_seed_covers_every_priority(seeded):
    stored = set(
        Announcement.objects.exclude(priority="").values_list("priority", flat=True)
    )
    assert stored == PRIORITY_CODES


def test_a_fairfax_realtor_sees_the_intended_rows(seeded):
    visible = {row.slug for row in visible_announcements(fairfax_realtor())}
    assert visible == {
        "mls-outage",  # company
        "q3-results",  # company
        "mid-atlantic-inventory",  # region above them
        "fairfax-parking",  # their own office
        "agency-disclosure-form",  # their role
        "new-crm-rollout",  # office half of a two-selector union
    }


def test_the_seeds_negatives_really_are_negative(seeded):
    """Every row whose summary claims it is hidden must actually be hidden."""
    visible = {row.slug for row in visible_announcements(fairfax_realtor())}
    claimed_hidden = {spec.slug for spec in SPECS if "NOT be visible" in spec.summary}
    assert claimed_hidden
    assert claimed_hidden & visible == set()


def test_the_two_selector_row_appears_once(seeded):
    feed = [
        row.slug for row in order_for_feed(visible_announcements(fairfax_realtor()))
    ]
    assert feed.count("new-crm-rollout") == 1


def test_the_seeded_feed_arrives_in_the_documented_order(seeded):
    feed = [
        row.priority for row in order_for_feed(visible_announcements(fairfax_realtor()))
    ]
    ranks = {"urgent": 1, "important": 2, "normal": 3}
    assert [ranks[code] for code in feed] == sorted(ranks[code] for code in feed)


def test_the_seeded_draft_carries_validation_debt(seeded):
    from apps.announcements.services import validation_debt

    draft = Announcement.objects.get(slug="half-written-policy")
    assert draft.status == Announcement.Status.DRAFT
    assert {field for field, _msg in validation_debt(draft)} == {
        "category",
        "priority",
        "body",
        "audience",
    }
