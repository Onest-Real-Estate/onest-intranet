"""Announcement classification, scope, ordering, filters, and governance.

The through-line of this file is the rule that priority is a *signal*, never a
*grant*: several tests deliberately give the invisible announcement the
highest priority, so a regression that let priority widen the set would fail
here rather than in production.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.announcements.models import (
    Announcement,
    AnnouncementCategory,
    ProtectedCategoryError,
)
from apps.announcements.services import (
    AnnouncementFilters,
    apply_filters,
    audience_office_ids,
    build_feed,
    category_filter_options,
    delete_category,
    order_for_feed,
    publish_announcement,
    validation_debt,
    validation_debt_payload,
    visible_queryset,
)
from apps.announcements.taxonomy import (
    CATEGORY_SEED,
    PRIORITY_IMPORTANT,
    PRIORITY_NORMAL,
    PRIORITY_URGENT,
)
from apps.audit.models import AuditEvent, DomainEvent
from apps.user.models import Office, User, UserRoleAssignment
from apps.user.tests.test_profile import completed_user


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def office(slug: str) -> Office:
    return Office.objects.get(slug=slug)


def category(code: str) -> AnnouncementCategory:
    return AnnouncementCategory.objects.get(code=code)


def assign(user, role: str, scope_type: str, scope_office=None) -> None:
    assignment = UserRoleAssignment(
        user=user, role=role, scope_type=scope_type, scope_office=scope_office
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()


def agent(slug="fairfax-va", email="agent@example.com"):
    return completed_user(email=email, office=office(slug))


def company_admin():
    user = completed_user(
        email="company.admin@example.com", office=office("onest-head-office")
    )
    assign(user, "system_admin", "company")
    return user


def scoped_publisher():
    """Announcement manager whose office grant stops at one region."""
    user = completed_user(email="regional.pub@example.com", office=office("harrisburg"))
    assign(user, "regional_admin", "region", office("region-mid-atlantic"))
    user.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="web", codename="manage_announcements"
        )
    )
    return User.objects.get(pk=user.pk)


def make(
    office_slug: str,
    slug: str,
    *,
    priority: str = PRIORITY_NORMAL,
    category_code: str = "company_announcement",
    status: str = Announcement.Status.PUBLISHED,
    published_at=None,
    publish_at=None,
    expires_at=None,
    title: str = "",
    body: str = "Something happened.",
) -> Announcement:
    announcement = Announcement(
        owner_office=office(office_slug),
        slug=slug,
        title=title or slug.replace("-", " ").title(),
        body=body,
        category=category(category_code) if category_code else None,
        priority=priority,
        status=status,
        publish_at=publish_at,
        expires_at=expires_at,
        published_at=(
            published_at
            if published_at is not None or status != Announcement.Status.PUBLISHED
            else timezone.now()
        ),
    )
    announcement.full_clean()
    announcement.save()
    return announcement


def slugs(rows) -> list[str]:
    return [row.slug if hasattr(row, "slug") else row["slug"] for row in rows]


# --------------------------------------------------------------------------- #
# Seeded vocabulary and its protections
# --------------------------------------------------------------------------- #


def test_migration_seeds_every_catalog_category_as_a_system_row(seeded):
    rows = AnnouncementCategory.objects.filter(is_system=True)
    assert set(rows.values_list("code", flat=True)) == {
        seed.code for seed in CATEGORY_SEED
    }
    assert all(row.is_active for row in rows)


def test_system_category_cannot_be_deleted_one_at_a_time(seeded):
    with pytest.raises(ProtectedCategoryError):
        category("event").delete()
    assert AnnouncementCategory.objects.filter(code="event").exists()


def test_system_category_cannot_be_deleted_in_bulk_either(seeded):
    """A queryset delete is the door a model-level guard usually misses."""
    with pytest.raises(ProtectedCategoryError):
        AnnouncementCategory.objects.filter(code="event").delete()
    assert AnnouncementCategory.objects.filter(code="event").exists()


def test_referenced_custom_category_is_refused_by_the_service(seeded):
    custom = AnnouncementCategory.objects.create(code="mergers", label="Mergers")
    make("fairfax-va", "merger-news", category_code="mergers")
    with pytest.raises(ProtectedCategoryError):
        delete_category(company_admin(), custom)
    assert AnnouncementCategory.objects.filter(code="mergers").exists()


def test_referenced_category_is_refused_by_the_database_as_a_backstop(seeded):
    custom = AnnouncementCategory.objects.create(code="mergers", label="Mergers")
    make("fairfax-va", "merger-news", category_code="mergers")
    with pytest.raises(IntegrityError), transaction.atomic():
        AnnouncementCategory.objects.filter(pk=custom.pk).delete()


def test_unreferenced_custom_category_can_be_deleted_by_a_manager(seeded):
    custom = AnnouncementCategory.objects.create(code="mergers", label="Mergers")
    delete_category(company_admin(), custom)
    assert not AnnouncementCategory.objects.filter(code="mergers").exists()


def test_deleting_a_category_needs_the_manage_permission(seeded):
    custom = AnnouncementCategory.objects.create(code="mergers", label="Mergers")
    with pytest.raises(PermissionDenied):
        delete_category(agent(), custom)
    assert AnnouncementCategory.objects.filter(code="mergers").exists()


def test_category_code_is_immutable_after_creation(seeded):
    row = category("event")
    row.code = "party"
    with pytest.raises(ValidationError) as excinfo:
        row.full_clean()
    assert "code" in excinfo.value.message_dict


def test_category_label_stays_editable(seeded):
    row = category("event")
    row.label = "Events & Gatherings"
    row.full_clean()
    row.save()
    assert category("event").label == "Events & Gatherings"


def test_retiring_a_category_keeps_published_history_readable(seeded):
    make("fairfax-va", "old-rules", category_code="compliance_update")
    retired = category("compliance_update")
    retired.is_active = False
    retired.save()

    rows = list(visible_queryset(agent()))
    assert slugs(rows) == ["old-rules"]
    assert rows[0].category is not None
    assert rows[0].category.label == "Compliance Update"


def test_a_retired_category_cannot_be_assigned_to_something_new(seeded):
    retired = category("event")
    retired.is_active = False
    retired.save()
    with pytest.raises(ValidationError) as excinfo:
        make("fairfax-va", "party", category_code="event")
    assert "category" in excinfo.value.message_dict


# --------------------------------------------------------------------------- #
# Publish requires the taxonomy; drafts report the debt instead
# --------------------------------------------------------------------------- #


def test_draft_saves_incomplete_and_reports_what_is_missing(seeded):
    draft = Announcement.objects.create(
        owner_office=office("fairfax-va"),
        slug="half-written",
        title="Half written",
        status=Announcement.Status.DRAFT,
    )
    fields = {field for field, _message in validation_debt(draft)}
    assert fields == {"category", "priority", "body"}

    payload = validation_debt_payload(draft)
    assert payload["isPublishable"] is False
    assert {item["field"] for item in payload["items"]} == fields
    assert all(item["message"] for item in payload["items"])


def test_a_complete_draft_reports_no_debt(seeded):
    draft = make(
        "fairfax-va",
        "ready",
        status=Announcement.Status.DRAFT,
        priority=PRIORITY_IMPORTANT,
    )
    assert validation_debt(draft) == []
    assert validation_debt_payload(draft)["isPublishable"] is True


def test_publishing_a_draft_with_debt_is_refused(seeded):
    draft = Announcement.objects.create(
        owner_office=office("fairfax-va"),
        slug="half-written",
        title="Half written",
        status=Announcement.Status.DRAFT,
    )
    with pytest.raises(ValidationError) as excinfo:
        publish_announcement(company_admin(), draft)
    assert set(excinfo.value.message_dict) == {"category", "priority", "body"}
    draft.refresh_from_db()
    assert draft.status == Announcement.Status.DRAFT


def test_the_database_refuses_a_published_row_without_taxonomy(seeded):
    """The acceptance criterion as a constraint, not a convention."""
    published = make("fairfax-va", "notice")
    with pytest.raises(IntegrityError), transaction.atomic():
        Announcement.objects.filter(pk=published.pk).update(priority="")
    with pytest.raises(IntegrityError), transaction.atomic():
        Announcement.objects.filter(pk=published.pk).update(category=None)


def test_publish_records_an_audit_entry_and_a_domain_event(seeded):
    draft = make(
        "fairfax-va",
        "outage",
        status=Announcement.Status.DRAFT,
        priority=PRIORITY_URGENT,
        category_code="urgent_operational_notice",
    )
    publish_announcement(company_admin(), draft)

    draft.refresh_from_db()
    assert draft.status == Announcement.Status.PUBLISHED
    assert draft.published_at is not None

    entry = AuditEvent.objects.filter(action="announcement.published").latest("id")
    assert entry.before["status"] == Announcement.Status.DRAFT
    assert entry.after["priority"] == PRIORITY_URGENT

    event = DomainEvent.objects.filter(name="announcement.published").latest("id")
    assert event.payload["category_code"] == "urgent_operational_notice"
    assert event.payload["priority_code"] == PRIORITY_URGENT
    assert event.payload["notify"] is True


def test_a_scoped_publisher_can_publish_inside_their_own_region(seeded):
    draft = make("harrisburg", "pa-news", status=Announcement.Status.DRAFT)
    publish_announcement(scoped_publisher(), draft)
    draft.refresh_from_db()
    assert draft.status == Announcement.Status.PUBLISHED


def test_a_scoped_publisher_is_refused_outside_their_region(seeded):
    """The office guard, exercised on its own.

    No shipped role currently pairs ``manage_announcements`` with a narrow
    scope — every role that carries it is company-wide — so the grant is built
    directly here. The guard is defence in depth for the day one does.
    """
    draft = make("connecticut", "ne-news", status=Announcement.Status.DRAFT)
    with pytest.raises(PermissionDenied):
        publish_announcement(scoped_publisher(), draft)
    draft.refresh_from_db()
    assert draft.status == Announcement.Status.DRAFT


def test_publishing_without_the_manage_permission_is_denied(seeded):
    draft = make("fairfax-va", "notice", status=Announcement.Status.DRAFT)
    with pytest.raises(PermissionDenied):
        publish_announcement(agent(), draft)


# --------------------------------------------------------------------------- #
# Audience scope — the set that reaches the sort
# --------------------------------------------------------------------------- #


def test_audience_is_the_readers_own_office_chain(seeded):
    chain = audience_office_ids(agent("fairfax-va"))
    assert set(chain) == {
        office(slug).pk
        for slug in (
            "fairfax-va",
            "ro-virginia",
            "region-mid-atlantic",
            "onest-head-office",
        )
    }


def test_a_user_without_an_office_sees_nothing(seeded):
    make("onest-head-office", "company-news")
    officeless = completed_user(email="nobody@example.com", office=None)
    assert audience_office_ids(officeless) == []
    assert list(visible_queryset(officeless)) == []


def test_a_sibling_branch_announcement_is_invisible_however_urgent(seeded):
    make("harrisburg", "pa-fire-drill", priority=PRIORITY_URGENT)
    make("fairfax-va", "va-notice", priority=PRIORITY_NORMAL)
    assert slugs(visible_queryset(agent("fairfax-va"))) == ["va-notice"]


def test_company_and_region_news_reach_the_branch(seeded):
    make("onest-head-office", "company-news")
    make("region-mid-atlantic", "region-news")
    make("fairfax-va", "branch-news")
    assert set(slugs(visible_queryset(agent("fairfax-va")))) == {
        "company-news",
        "region-news",
        "branch-news",
    }


def test_scope_level_is_derived_from_the_owning_node(seeded):
    assert make("onest-head-office", "a").scope_level == "company"
    assert make("region-mid-atlantic", "b").scope_level == "region"
    assert make("fairfax-va", "c").scope_level == "office"


# --------------------------------------------------------------------------- #
# Lifecycle window — priority does not open it
# --------------------------------------------------------------------------- #


def test_drafts_and_archives_never_reach_a_reader(seeded):
    make("fairfax-va", "draft-item", status=Announcement.Status.DRAFT)
    make("fairfax-va", "archived-item", status=Announcement.Status.ARCHIVED)
    make("fairfax-va", "live-item")
    assert slugs(visible_queryset(agent())) == ["live-item"]


def test_an_urgent_announcement_scheduled_for_later_is_still_not_visible(seeded):
    later = timezone.now() + timedelta(days=2)
    make("fairfax-va", "future-emergency", priority=PRIORITY_URGENT, publish_at=later)
    make("fairfax-va", "todays-news")
    assert slugs(visible_queryset(agent())) == ["todays-news"]


def test_an_urgent_announcement_that_expired_is_gone(seeded):
    past = timezone.now() - timedelta(days=3)
    make(
        "fairfax-va",
        "old-emergency",
        priority=PRIORITY_URGENT,
        publish_at=past,
        expires_at=timezone.now() - timedelta(days=1),
    )
    assert list(visible_queryset(agent())) == []


def test_expiry_must_follow_the_publish_time(seeded):
    now = timezone.now()
    with pytest.raises(ValidationError) as excinfo:
        make(
            "fairfax-va",
            "backwards",
            publish_at=now,
            expires_at=now - timedelta(hours=1),
        )
    assert "expires_at" in excinfo.value.message_dict


# --------------------------------------------------------------------------- #
# Ordering
# --------------------------------------------------------------------------- #


def test_priority_sorts_above_recency_and_recency_breaks_ties(seeded):
    now = timezone.now()
    make(
        "fairfax-va",
        "old-urgent",
        priority=PRIORITY_URGENT,
        published_at=now - timedelta(days=5),
    )
    make(
        "fairfax-va",
        "new-normal",
        priority=PRIORITY_NORMAL,
        published_at=now - timedelta(minutes=1),
    )
    make(
        "fairfax-va",
        "old-normal",
        priority=PRIORITY_NORMAL,
        published_at=now - timedelta(days=1),
    )
    make(
        "fairfax-va",
        "mid-important",
        priority=PRIORITY_IMPORTANT,
        published_at=now - timedelta(days=2),
    )

    assert slugs(order_for_feed(visible_queryset(agent()))) == [
        "old-urgent",
        "mid-important",
        "new-normal",
        "old-normal",
    ]


def test_ordering_sorts_but_never_adds_a_row(seeded):
    make("harrisburg", "other-branch", priority=PRIORITY_URGENT)
    make("fairfax-va", "mine")
    visible = visible_queryset(agent())
    assert set(slugs(order_for_feed(visible))) == set(slugs(visible))


def test_a_legacy_priority_code_sorts_as_normal_instead_of_disappearing(seeded):
    now = timezone.now()
    legacy = make("fairfax-va", "legacy", published_at=now - timedelta(minutes=1))
    Announcement.objects.filter(pk=legacy.pk).update(priority="blocker")
    make("fairfax-va", "real-urgent", priority=PRIORITY_URGENT)
    make("fairfax-va", "older-normal", published_at=now - timedelta(days=1))

    assert slugs(order_for_feed(visible_queryset(agent()))) == [
        "real-urgent",
        "legacy",
        "older-normal",
    ]


# --------------------------------------------------------------------------- #
# Filters
# --------------------------------------------------------------------------- #


def known_codes():
    return set(AnnouncementCategory.objects.values_list("code", flat=True))


def test_filters_accept_stable_codes_from_the_query_string(seeded):
    filters = AnnouncementFilters.from_params(
        {"category": "market_update", "priority": PRIORITY_URGENT},
        known_category_codes=known_codes(),
    )
    assert filters.category == "market_update"
    assert filters.priority == PRIORITY_URGENT
    assert filters.rejected == ()
    assert filters.active_count == 2


def test_an_unknown_filter_value_is_dropped_and_reported(seeded):
    filters = AnnouncementFilters.from_params(
        {"category": "not_a_category", "priority": "blocker"},
        known_category_codes=known_codes(),
    )
    assert (filters.category, filters.priority) == ("", "")
    assert set(filters.rejected) == {"category", "priority"}


def test_filters_narrow_to_only_accessible_records(seeded):
    make("harrisburg", "pa-market", category_code="market_update")
    make("fairfax-va", "va-market", category_code="market_update")
    filters = AnnouncementFilters(category="market_update")
    rows = apply_filters(visible_queryset(agent("fairfax-va")), filters)
    assert slugs(rows) == ["va-market"]


def test_priority_filter_narrows_without_reordering_scope(seeded):
    make("fairfax-va", "urgent-one", priority=PRIORITY_URGENT)
    make("fairfax-va", "normal-one", priority=PRIORITY_NORMAL)
    rows = apply_filters(
        visible_queryset(agent()), AnnouncementFilters(priority=PRIORITY_URGENT)
    )
    assert slugs(rows) == ["urgent-one"]


def test_filtering_by_a_retired_category_still_returns_its_history(seeded):
    make("fairfax-va", "old-rules", category_code="compliance_update")
    retired = category("compliance_update")
    retired.is_active = False
    retired.save()

    feed = build_feed(agent(), params={"category": "compliance_update"}, page=1)
    assert slugs(feed["items"]) == ["old-rules"]
    assert feed["filters"]["category"] == "compliance_update"


def test_a_retired_but_selected_category_stays_in_the_filter_options(seeded):
    retired = category("compliance_update")
    retired.is_active = False
    retired.save()

    values = {row["value"] for row in category_filter_options()}
    assert "compliance_update" not in values

    with_selection = {
        row["value"]
        for row in category_filter_options(include_codes=("compliance_update",))
    }
    assert "compliance_update" in with_selection


# --------------------------------------------------------------------------- #
# Feed payload + pagination
# --------------------------------------------------------------------------- #


def test_feed_row_carries_codes_and_meanings_not_styling(seeded):
    make(
        "fairfax-va",
        "outage",
        priority=PRIORITY_URGENT,
        category_code="urgent_operational_notice",
    )
    row = build_feed(agent(), params={}, page=1)["items"][0]

    assert row["priority"]["code"] == PRIORITY_URGENT
    assert row["priority"]["tone"] == "destructive"
    assert row["priority"]["label"] == "Urgent"
    assert row["category"]["code"] == "urgent_operational_notice"
    assert row["scope"]["level"] == "office"
    assert "#" not in json.dumps(row)


def test_filters_survive_pagination(seeded):
    for index in range(5):
        make(
            "fairfax-va",
            f"market-{index}",
            category_code="market_update",
            published_at=timezone.now() - timedelta(minutes=index),
        )
    make("fairfax-va", "unrelated", category_code="event")

    reader = agent()
    params = {"category": "market_update"}
    first = build_feed(reader, params=params, page=1, page_size=2)
    second = build_feed(reader, params=params, page=2, page_size=2)

    assert (
        first["filters"]
        == second["filters"]
        == {
            "category": "market_update",
            "priority": "",
            "rejected": [],
        }
    )
    assert first["pagination"]["totalItems"] == 5
    assert second["pagination"]["page"] == 2
    assert set(slugs(first["items"])) & set(slugs(second["items"])) == set()
    assert "unrelated" not in slugs(first["items"]) + slugs(second["items"])


def test_a_page_beyond_the_end_clamps_instead_of_erroring(seeded):
    make("fairfax-va", "only-one")
    feed = build_feed(agent(), params={}, page=99, page_size=2)
    assert feed["pagination"]["page"] == 1
    assert slugs(feed["items"]) == ["only-one"]


# --------------------------------------------------------------------------- #
# The Inertia page
# --------------------------------------------------------------------------- #


def props(response) -> dict:
    return json.loads(response.content)["props"]


def test_feed_page_renders_for_a_signed_in_reader(seeded, client):
    make("fairfax-va", "va-notice", priority=PRIORITY_IMPORTANT)
    make("harrisburg", "pa-notice", priority=PRIORITY_URGENT)
    client.force_login(agent("fairfax-va"))

    response = client.get(reverse("announcements"), HTTP_X_INERTIA="true")
    assert response.status_code == 200
    body = json.loads(response.content)
    assert body["component"] == "Announcements"
    assert slugs(body["props"]["feed"]["items"]) == ["va-notice"]
    assert body["props"]["filterOptions"]["priorities"][0]["value"] == PRIORITY_URGENT


def test_feed_page_requires_a_session(seeded, client):
    response = client.get(reverse("announcements"))
    assert response.status_code in {302, 401}


def test_feed_page_ignores_a_junk_filter_and_says_so(seeded, client):
    make("fairfax-va", "va-notice")
    client.force_login(agent("fairfax-va"))

    response = client.get(
        reverse("announcements"),
        {"category": "not_a_category"},
        HTTP_X_INERTIA="true",
    )
    filters = props(response)["feed"]["filters"]
    assert filters["category"] == ""
    assert filters["rejected"] == ["category"]
    assert slugs(props(response)["feed"]["items"]) == ["va-notice"]


def test_feed_page_never_widens_scope_from_a_query_parameter(seeded, client):
    """No office identifier is accepted; a forged one changes nothing."""
    make("harrisburg", "pa-notice", priority=PRIORITY_URGENT)
    make("fairfax-va", "va-notice")
    client.force_login(agent("fairfax-va"))

    response = client.get(
        reverse("announcements"),
        {"office": office("harrisburg").pk, "owner_office": "harrisburg"},
        HTTP_X_INERTIA="true",
    )
    assert slugs(props(response)["feed"]["items"]) == ["va-notice"]
