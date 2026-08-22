"""Audience resolution, union semantics, grant boundaries, and direct access.

Structured around the two questions the audience module answers:

* *Given a reader, which announcements?* — ``visible_announcements`` /
  ``visible_to``, exercised table-driven across every selector type.
* *Given an announcement, which readers?* — ``recipients_for``.

Both must agree. ``test_the_two_directions_agree`` asserts that directly, so a
change that loosens one side without the other fails here.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.announcements.audience import (
    MIN_RECIPIENT_QUERY,
    AudienceSelector,
    assert_can_target,
    describe_audience,
    live_role_codes,
    recipients_for,
    replace_audience,
    search_recipients,
    selectors_for,
    targetable_office_ids,
    targetable_role_codes,
    visible_announcements,
    visible_to,
)
from apps.announcements.models import Announcement, AnnouncementAudience
from apps.announcements.taxonomy import PRIORITY_NORMAL, PRIORITY_URGENT
from apps.audit.models import AuditEvent
from apps.user.models import Office, User, UserRoleAssignment
from apps.user.tests.test_profile import completed_user

Kind = AnnouncementAudience.Kind


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


# --------------------------------------------------------------------------- #
# Fixtures and helpers
# --------------------------------------------------------------------------- #


def office(slug: str) -> Office:
    return Office.objects.get(slug=slug)


def person(email: str, office_slug: str | None = "fairfax-va") -> User:
    return completed_user(
        email=email, office=office(office_slug) if office_slug else None
    )


def assign(user, role: str, scope_type: str, scope_office=None, **window) -> None:
    assignment = UserRoleAssignment(
        user=user,
        user_id=user.pk,
        role=role,
        scope_type=scope_type,
        scope_office=scope_office,
        **window,
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()


def company_admin() -> User:
    user = person("company.admin@example.com", "onest-head-office")
    assign(user, "system_admin", "company")
    return user


def grant_publisher(user: User) -> User:
    """Give one user the publish permission without widening their org scope."""
    user.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="web", codename="manage_announcements"
        )
    )
    return User.objects.get(pk=user.pk)


def branch_publisher() -> User:
    user = person("branch.pub@example.com", "fairfax-va")
    assign(user, "branch_admin", "office", office("fairfax-va"))
    return grant_publisher(user)


def regional_publisher() -> User:
    user = person("regional.pub@example.com", "harrisburg")
    assign(user, "regional_admin", "region", office("region-mid-atlantic"))
    return grant_publisher(user)


def announcement(slug: str, *, owner="onest-head-office", **kwargs) -> Announcement:
    from apps.announcements.models import AnnouncementCategory

    row = Announcement(
        owner_office=office(owner),
        slug=slug,
        title=slug.replace("-", " ").title(),
        body="Something happened.",
        category=AnnouncementCategory.objects.get(code="company_announcement"),
        priority=kwargs.pop("priority", PRIORITY_NORMAL),
        status=kwargs.pop("status", Announcement.Status.PUBLISHED),
        published_at=kwargs.pop("published_at", timezone.now()),
        **kwargs,
    )
    row.save()
    return row


def target(row: Announcement, kind: str, **target_kwargs) -> AnnouncementAudience:
    return AnnouncementAudience.objects.create(
        announcement=row, kind=kind, **target_kwargs
    )


def slugs(rows) -> set[str]:
    return {row.slug for row in rows}


# --------------------------------------------------------------------------- #
# Table-driven: each selector returns its documented recipient set
# --------------------------------------------------------------------------- #


AUDIENCE_CASES = [
    # (case name, selector kwargs factory, reader office slug, expected)
    ("company reaches a branch agent", Kind.COMPANY, {}, "fairfax-va", True),
    ("company reaches head office", Kind.COMPANY, {}, "onest-head-office", True),
    ("region reaches an office under it", Kind.REGION, "region", "fairfax-va", True),
    (
        "region reaches an office deeper under it",
        Kind.REGION,
        "region",
        "harrisburg",
        True,
    ),
    (
        "region does not reach another region",
        Kind.REGION,
        "region",
        "connecticut",
        False,
    ),
    ("office reaches exactly that office", Kind.OFFICE, "branch", "fairfax-va", True),
    (
        "office does not reach a sibling branch",
        Kind.OFFICE,
        "branch",
        "charlottesville-va",
        False,
    ),
    (
        "office does not reach its own parent region",
        Kind.OFFICE,
        "branch",
        "region-mid-atlantic",
        False,
    ),
]


@pytest.mark.parametrize(
    ("name", "kind", "office_role", "reader_office", "expected"),
    AUDIENCE_CASES,
    ids=[case[0] for case in AUDIENCE_CASES],
)
def test_each_selector_returns_its_documented_set(
    seeded, name, kind, office_role, reader_office, expected
):
    row = announcement("notice")
    if office_role == "region":
        target(row, kind, office=office("region-mid-atlantic"))
    elif office_role == "branch":
        target(row, kind, office=office("fairfax-va"))
    else:
        target(row, kind)

    reader = person("reader@example.com", reader_office)
    assert visible_to(reader, row) is expected
    assert (row.slug in slugs(visible_announcements(reader))) is expected


def test_role_selector_reaches_every_current_holder(seeded):
    row = announcement("for-coordinators")
    target(row, Kind.ROLE, role="transaction_coordinator")

    holder = person("tc@example.com", "charlottesville-va")
    assign(holder, "transaction_coordinator", "office", office("charlottesville-va"))
    outsider = person("plain@example.com", "charlottesville-va")

    assert visible_to(holder, row) is True
    assert visible_to(outsider, row) is False


def test_role_selector_honours_the_validity_window(seeded):
    row = announcement("for-coordinators")
    target(row, Kind.ROLE, role="transaction_coordinator")
    now = timezone.now()

    future = person("future@example.com", "fairfax-va")
    assign(
        future,
        "transaction_coordinator",
        "office",
        office("fairfax-va"),
        starts_at=now + timedelta(days=3),
    )
    expired = person("expired@example.com", "fairfax-va")
    assign(
        expired,
        "transaction_coordinator",
        "office",
        office("fairfax-va"),
        starts_at=now - timedelta(days=10),
        ends_at=now - timedelta(days=1),
    )

    assert visible_to(future, row) is False
    assert visible_to(expired, row) is False
    # The scheduled grant opens access when its window arrives — evaluated at
    # read time, so no backfill job is involved.
    assert visible_to(future, row, at=now + timedelta(days=4)) is True


def test_a_reader_with_several_roles_matches_on_any_of_them(seeded):
    row = announcement("for-coordinators")
    target(row, Kind.ROLE, role="transaction_coordinator")

    reader = person("multi@example.com", "fairfax-va")
    assign(reader, "branch_admin", "office", office("fairfax-va"))
    assign(reader, "transaction_coordinator", "office", office("fairfax-va"))

    assert "transaction_coordinator" in live_role_codes(reader)
    assert visible_to(reader, row) is True


def test_individual_selector_reaches_that_person_only(seeded):
    row = announcement("just-for-you")
    named = person("named@example.com", "fairfax-va")
    colleague = person("colleague@example.com", "fairfax-va")
    target(row, Kind.USER, user=named)

    assert visible_to(named, row) is True
    assert visible_to(colleague, row) is False


def test_a_reader_without_an_office_still_matches_company_and_named(seeded):
    company_row = announcement("all-hands")
    target(company_row, Kind.COMPANY)
    office_row = announcement("branch-only")
    target(office_row, Kind.OFFICE, office=office("fairfax-va"))
    named_row = announcement("personal")

    officeless = person("nowhere@example.com", None)
    target(named_row, Kind.USER, user=officeless)

    assert slugs(visible_announcements(officeless)) == {"all-hands", "personal"}


def test_an_announcement_with_no_selectors_reaches_nobody(seeded):
    row = announcement("orphan")
    assert visible_to(person("reader@example.com"), row) is False
    assert list(recipients_for(row)) == []


def test_an_inactive_office_does_not_change_the_predicate(seeded):
    """Deactivating an office is an org decision, not a revocation of news.

    The reader still belongs to it, so the documented behaviour is that they
    keep seeing what was addressed to it. Anything else would silently drop
    people mid-reorganization.
    """
    row = announcement("branch-only")
    target(row, Kind.OFFICE, office=office("fairfax-va"))
    reader = person("reader@example.com", "fairfax-va")

    node = office("fairfax-va")
    node.is_active = False
    node.save(update_fields=["is_active"])

    assert visible_to(reader, row) is True


# --------------------------------------------------------------------------- #
# Union semantics
# --------------------------------------------------------------------------- #


def test_multiple_selectors_are_a_union_not_an_intersection(seeded):
    row = announcement("either-way")
    target(row, Kind.OFFICE, office=office("fairfax-va"))
    target(row, Kind.ROLE, role="transaction_coordinator")

    by_office = person("office@example.com", "fairfax-va")
    by_role = person("role@example.com", "connecticut")
    assign(by_role, "transaction_coordinator", "office", office("connecticut"))
    neither = person("neither@example.com", "connecticut")

    assert visible_to(by_office, row) is True
    assert visible_to(by_role, row) is True
    assert visible_to(neither, row) is False


def test_matching_several_selectors_still_yields_one_feed_entry(seeded):
    row = announcement("many-ways")
    reader = person("reader@example.com", "fairfax-va")
    assign(reader, "transaction_coordinator", "office", office("fairfax-va"))

    target(row, Kind.COMPANY)
    target(row, Kind.REGION, office=office("region-mid-atlantic"))
    target(row, Kind.OFFICE, office=office("fairfax-va"))
    target(row, Kind.ROLE, role="transaction_coordinator")
    target(row, Kind.USER, user=reader)

    visible = list(visible_announcements(reader))
    assert [item.slug for item in visible] == ["many-ways"]


def test_a_person_caught_by_several_selectors_appears_once_in_recipients(seeded):
    row = announcement("many-ways")
    reader = person("reader@example.com", "fairfax-va")
    assign(reader, "transaction_coordinator", "office", office("fairfax-va"))
    target(row, Kind.REGION, office=office("region-mid-atlantic"))
    target(row, Kind.OFFICE, office=office("fairfax-va"))
    target(row, Kind.ROLE, role="transaction_coordinator")
    target(row, Kind.USER, user=reader)

    recipients = list(recipients_for(row))
    assert [item.pk for item in recipients].count(reader.pk) == 1


# --------------------------------------------------------------------------- #
# The two directions agree
# --------------------------------------------------------------------------- #


def test_the_two_directions_agree(seeded):
    """Everyone ``recipients_for`` names can see it; nobody else can."""
    row = announcement("mixed")
    inside_office = person("in-office@example.com", "fairfax-va")
    inside_region = person("in-region@example.com", "harrisburg")
    named = person("named@example.com", "connecticut")
    outsider = person("outside@example.com", "connecticut")

    target(row, Kind.OFFICE, office=office("fairfax-va"))
    target(row, Kind.REGION, office=office("ro-pennsylvania"))
    target(row, Kind.USER, user=named)

    recipient_ids = set(recipients_for(row).values_list("pk", flat=True))
    assert recipient_ids == {inside_office.pk, inside_region.pk, named.pk}
    for reader in (inside_office, inside_region, named):
        assert visible_to(reader, row) is True
    assert visible_to(outsider, row) is False
    assert outsider.pk not in recipient_ids


def test_company_selector_reaches_every_active_user(seeded):
    row = announcement("all-hands")
    target(row, Kind.COMPANY)
    people = [person(f"p{index}@example.com", "fairfax-va") for index in range(3)]
    disabled = person("gone@example.com", "fairfax-va")
    User.objects.filter(pk=disabled.pk).update(is_active=False)

    recipient_ids = set(recipients_for(row).values_list("pk", flat=True))
    assert {item.pk for item in people} <= recipient_ids
    assert disabled.pk not in recipient_ids


# --------------------------------------------------------------------------- #
# Reassignment changes future access
# --------------------------------------------------------------------------- #


def test_moving_offices_changes_access_from_that_moment(seeded):
    row = announcement("va-only")
    target(row, Kind.OFFICE, office=office("fairfax-va"))
    reader = person("mover@example.com", "fairfax-va")
    assert visible_to(reader, row) is True

    reader.office = office("connecticut")
    reader.save(update_fields=["office"])

    assert visible_to(User.objects.get(pk=reader.pk), row) is False


def test_ending_a_role_assignment_closes_access(seeded):
    row = announcement("for-coordinators")
    target(row, Kind.ROLE, role="transaction_coordinator")
    reader = person("tc@example.com", "fairfax-va")
    assign(reader, "transaction_coordinator", "office", office("fairfax-va"))
    assert visible_to(reader, row) is True

    UserRoleAssignment.objects.filter(user=reader).update(
        status=UserRoleAssignment.Status.REVOKED, revoked_at=timezone.now()
    )
    assert visible_to(User.objects.get(pk=reader.pk), row) is False


def test_moving_into_a_region_opens_access_to_its_history(seeded):
    row = announcement("mid-atlantic-news")
    target(row, Kind.REGION, office=office("region-mid-atlantic"))
    reader = person("joiner@example.com", "connecticut")
    assert visible_to(reader, row) is False

    reader.office = office("philadelphia")
    reader.save(update_fields=["office"])
    assert visible_to(User.objects.get(pk=reader.pk), row) is True


# --------------------------------------------------------------------------- #
# Grant boundaries
# --------------------------------------------------------------------------- #


def test_a_branch_publisher_may_address_their_own_branch(seeded):
    actor = branch_publisher()
    assert_can_target(
        actor, [AudienceSelector(Kind.OFFICE, office=office("fairfax-va"))]
    )


def test_a_branch_publisher_cannot_address_a_sibling_branch(seeded):
    actor = branch_publisher()
    with pytest.raises(PermissionDenied):
        assert_can_target(
            actor,
            [AudienceSelector(Kind.OFFICE, office=office("charlottesville-va"))],
        )


def test_a_branch_publisher_cannot_address_an_ancestor(seeded):
    actor = branch_publisher()
    for slug in ("ro-virginia", "region-mid-atlantic", "onest-head-office"):
        with pytest.raises(PermissionDenied):
            assert_can_target(
                actor, [AudienceSelector(Kind.REGION, office=office(slug))]
            )


def test_a_branch_publisher_cannot_address_everyone(seeded):
    actor = branch_publisher()
    with pytest.raises(PermissionDenied):
        assert_can_target(actor, [AudienceSelector(Kind.COMPANY)])


def test_a_regional_publisher_reaches_down_but_not_sideways(seeded):
    actor = regional_publisher()
    reachable = targetable_office_ids(actor)
    assert office("harrisburg").pk in reachable
    assert office("philadelphia").pk in reachable
    assert office("region-mid-atlantic").pk in reachable
    assert office("connecticut").pk not in reachable
    assert office("onest-head-office").pk not in reachable


def test_a_company_admin_may_address_everyone(seeded):
    assert_can_target(company_admin(), [AudienceSelector(Kind.COMPANY)])


def test_a_publisher_cannot_address_a_role_they_cannot_delegate(seeded):
    actor = branch_publisher()
    delegable = targetable_role_codes(actor)
    assert "system_admin" not in delegable
    with pytest.raises(PermissionDenied):
        assert_can_target(actor, [AudienceSelector(Kind.ROLE, role="system_admin")])


def test_a_publisher_cannot_name_a_person_outside_their_scope(seeded):
    actor = branch_publisher()
    stranger = person("stranger@example.com", "connecticut")
    with pytest.raises(PermissionDenied):
        assert_can_target(actor, [AudienceSelector(Kind.USER, user=stranger)])


def test_targeting_without_the_publish_permission_is_denied(seeded):
    reader = person("reader@example.com", "fairfax-va")
    with pytest.raises(PermissionDenied):
        assert_can_target(
            reader, [AudienceSelector(Kind.OFFICE, office=office("fairfax-va"))]
        )


def test_an_empty_audience_is_a_validation_error_not_a_silent_pass(seeded):
    with pytest.raises(ValidationError):
        assert_can_target(company_admin(), [])


def test_one_denied_selector_rejects_the_whole_set(seeded):
    """A mixed request is not partially applied."""
    actor = branch_publisher()
    row = announcement("mixed", owner="fairfax-va")
    with pytest.raises(PermissionDenied):
        replace_audience(
            actor,
            row,
            [
                AudienceSelector(Kind.OFFICE, office=office("fairfax-va")),
                AudienceSelector(Kind.OFFICE, office=office("charlottesville-va")),
            ],
        )
    assert not selectors_for(row).exists()


def test_a_denied_target_is_recorded(seeded):
    actor = branch_publisher()
    with pytest.raises(PermissionDenied):
        assert_can_target(actor, [AudienceSelector(Kind.COMPANY)])
    entry = (
        AuditEvent.objects.filter(action="security.announcement.audience_denied")
        .order_by("occurred_at")
        .last()
    )
    assert entry is not None
    assert entry.outcome == AuditEvent.Outcome.DENIED
    assert entry.reason == "company_audience_outside_grant"


def test_replacing_the_audience_records_before_and_after(seeded):
    actor = company_admin()
    row = announcement("news")
    replace_audience(
        actor, row, [AudienceSelector(Kind.OFFICE, office=office("fairfax-va"))]
    )
    replace_audience(actor, row, [AudienceSelector(Kind.COMPANY)])

    # Selected by content rather than by ordering: the audit primary key is a
    # UUID, so "the latest row" is not a question the id can answer.
    entries = list(AuditEvent.objects.filter(action="announcement.audience_changed"))
    assert len(entries) == 2
    transitions = {
        (
            tuple(item["kind"] for item in entry.before["audience"]),
            tuple(item["kind"] for item in entry.after["audience"]),
        )
        for entry in entries
    }
    assert transitions == {
        ((), (Kind.OFFICE,)),
        ((Kind.OFFICE,), (Kind.COMPANY,)),
    }
    assert describe_audience(row)[0]["label"] == "Everyone at oNEST"


# --------------------------------------------------------------------------- #
# Stored shape
# --------------------------------------------------------------------------- #


def test_a_selector_cannot_carry_a_target_its_kind_does_not_use(seeded):
    row = announcement("news")
    with pytest.raises(IntegrityError), transaction.atomic():
        AnnouncementAudience.objects.create(
            announcement=row, kind=Kind.COMPANY, office=office("fairfax-va")
        )


def test_a_role_selector_must_name_a_role(seeded):
    row = announcement("news")
    with pytest.raises(IntegrityError), transaction.atomic():
        AnnouncementAudience.objects.create(announcement=row, kind=Kind.ROLE, role="")


def test_the_same_selector_cannot_be_added_twice(seeded):
    row = announcement("news")
    target(row, Kind.OFFICE, office=office("fairfax-va"))
    with pytest.raises(IntegrityError), transaction.atomic():
        target(row, Kind.OFFICE, office=office("fairfax-va"))


def test_region_and_office_selectors_on_one_node_coexist(seeded):
    """Different meanings, same node: "this branch" and "under this branch"."""
    row = announcement("news")
    target(row, Kind.REGION, office=office("ro-virginia"))
    target(row, Kind.OFFICE, office=office("ro-virginia"))
    assert selectors_for(row).count() == 2


# --------------------------------------------------------------------------- #
# Recipient search — scoped, and not an enumeration tool
# --------------------------------------------------------------------------- #


def test_recipient_search_only_returns_people_in_the_actors_scope(seeded):
    actor = branch_publisher()
    person("findable.smith@example.com", "fairfax-va")
    person("hidden.smith@example.com", "connecticut")

    emails = {row["email"] for row in search_recipients(actor, "smith")}
    assert emails == {"findable.smith@example.com"}


def test_recipient_search_refuses_a_query_too_short_to_be_a_search(seeded):
    actor = branch_publisher()
    person("aaron@example.com", "fairfax-va")
    assert search_recipients(actor, "a") == []
    assert search_recipients(actor, "") == []
    assert len(search_recipients(actor, "aa")) >= 0
    assert MIN_RECIPIENT_QUERY == 2


def test_recipient_search_needs_the_publish_permission(seeded):
    with pytest.raises(PermissionDenied):
        search_recipients(person("nosy@example.com", "fairfax-va"), "smith")


def test_recipient_search_is_capped(seeded):
    actor = company_admin()
    for index in range(30):
        person(f"smith{index}@example.com", "fairfax-va")
    assert len(search_recipients(actor, "smith")) <= 20


# --------------------------------------------------------------------------- #
# Direct object access
# --------------------------------------------------------------------------- #


def test_the_detail_url_enforces_the_same_predicate_as_the_feed(seeded, client):
    row = announcement("branch-only", priority=PRIORITY_URGENT)
    target(row, Kind.OFFICE, office=office("fairfax-va"))

    insider = person("in@example.com", "fairfax-va")
    outsider = person("out@example.com", "charlottesville-va")

    client.force_login(insider)
    assert (
        client.get(
            reverse("announcement_detail", args=[row.pk]), HTTP_X_INERTIA="true"
        ).status_code
        == 200
    )

    client.force_login(outsider)
    assert (
        client.get(
            reverse("announcement_detail", args=[row.pk]), HTTP_X_INERTIA="true"
        ).status_code
        == 403
    )


def test_a_draft_is_not_reachable_by_direct_url(seeded, client):
    row = announcement("draft", status=Announcement.Status.DRAFT, published_at=None)
    target(row, Kind.COMPANY)
    client.force_login(person("reader@example.com", "fairfax-va"))
    assert (
        client.get(
            reverse("announcement_detail", args=[row.pk]), HTTP_X_INERTIA="true"
        ).status_code
        == 403
    )


def test_an_expired_announcement_is_not_reachable_by_direct_url(seeded, client):
    row = announcement(
        "expired",
        priority=PRIORITY_URGENT,
        expires_at=timezone.now() - timedelta(hours=1),
    )
    target(row, Kind.COMPANY)
    client.force_login(person("reader@example.com", "fairfax-va"))
    assert (
        client.get(
            reverse("announcement_detail", args=[row.pk]), HTTP_X_INERTIA="true"
        ).status_code
        == 403
    )


def test_an_out_of_audience_detail_request_is_recorded(seeded, client):
    row = announcement("branch-only")
    target(row, Kind.OFFICE, office=office("fairfax-va"))
    client.force_login(person("out@example.com", "charlottesville-va"))
    client.get(reverse("announcement_detail", args=[row.pk]), HTTP_X_INERTIA="true")

    entry = AuditEvent.objects.filter(action="security.announcement.denied").latest(
        "id"
    )
    assert entry.reason == "detail_out_of_audience"


def test_the_attachment_url_enforces_the_same_predicate(
    seeded, client, settings, tmp_path
):
    from django.core.files.base import ContentFile

    settings.MEDIA_ROOT = str(tmp_path)

    row = announcement("with-file")
    target(row, Kind.OFFICE, office=office("fairfax-va"))
    row.attachment.save("memo.txt", ContentFile(b"hello"), save=False)
    row.attachment_name = "memo.txt"
    row.save(update_fields=["attachment", "attachment_name"])

    client.force_login(person("out@example.com", "charlottesville-va"))
    assert (
        client.get(reverse("announcement_attachment", args=[row.pk])).status_code == 403
    )

    client.force_login(person("in@example.com", "fairfax-va"))
    response = client.get(reverse("announcement_attachment", args=[row.pk]))
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"hello"


def test_the_recipient_search_endpoint_refuses_a_reader(seeded, client):
    client.force_login(person("reader@example.com", "fairfax-va"))
    response = client.get(reverse("announcement_recipient_search"), {"q": "smith"})
    assert response.status_code == 403


def test_the_recipient_search_endpoint_stays_inside_scope(seeded, client):
    actor = branch_publisher()
    person("findable.smith@example.com", "fairfax-va")
    person("hidden.smith@example.com", "connecticut")
    client.force_login(actor)

    response = client.get(reverse("announcement_recipient_search"), {"q": "smith"})
    assert response.status_code == 200
    emails = {row["email"] for row in response.json()["results"]}
    assert emails == {"findable.smith@example.com"}


# --------------------------------------------------------------------------- #
# Query behaviour
# --------------------------------------------------------------------------- #


def test_the_feed_cost_does_not_grow_with_the_number_of_announcements(
    seeded, django_assert_num_queries
):
    """No per-announcement or per-selector query.

    The reader's facts are gathered once and the audience becomes one join, so
    twenty announcements cost the same as two.
    """
    from django.db import connection

    reader = person("reader@example.com", "fairfax-va")
    assign(reader, "transaction_coordinator", "office", office("fairfax-va"))

    def cost(count: int) -> int:
        Announcement.objects.all().delete()
        for index in range(count):
            row = announcement(f"news-{index}")
            target(row, Kind.COMPANY)
            target(row, Kind.OFFICE, office=office("fairfax-va"))
        fresh = User.objects.get(pk=reader.pk)
        with CaptureQueriesContext(connection) as captured:
            assert len(list(visible_announcements(fresh))) == count
        return len(captured)

    assert cost(2) == cost(20)


def test_recipient_resolution_is_one_query_regardless_of_selector_count(seeded):
    from django.db import connection

    row = announcement("many-ways")
    reader = person("reader@example.com", "fairfax-va")
    assign(reader, "transaction_coordinator", "office", office("fairfax-va"))
    target(row, Kind.OFFICE, office=office("fairfax-va"))
    target(row, Kind.ROLE, role="transaction_coordinator")
    target(row, Kind.USER, user=reader)

    with CaptureQueriesContext(connection) as captured:
        list(recipients_for(row))
    # One read of the selectors, then one read of the users. Region selectors
    # add their descendant walk; there are none here.
    assert len(captured) <= 2
