"""The announcement workspace: lifecycle, scope, concurrency, audit, and events.

The through-line here is that *authoring is not publishing*. Several tests give
the actor full authoring authority and then assert they still cannot change what
anybody sees — a regression that collapsed the two grants back into one would
fail here rather than in production.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.announcements.administration import (
    StaleAnnouncementVersion,
    TransitionRefused,
    WorkspaceFilters,
    announcement_version,
    apply_workspace_filters,
    create_announcement,
    lifecycle_state,
    manageable_queryset,
    preview_payload,
    publication_history,
    set_pinned,
    transition,
    update_announcement,
)
from apps.announcements.audience import AudienceSelector
from apps.announcements.models import Announcement, AnnouncementAudience
from apps.announcements.services import order_for_feed, visible_queryset
from apps.audit.models import AuditEvent, DomainEvent
from apps.user.models import Office, User, UserRoleAssignment
from apps.user.tests.test_profile import completed_user

PRIORITY = "normal"
CATEGORY = "company_announcement"
#: A node in the other region. Everything under Mid-Atlantic is *inside* the
#: regional publisher's grant, so an out-of-scope case has to leave the region.
OUTSIDE_REGION = "connecticut"


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def office(slug: str) -> Office:
    return Office.objects.get(slug=slug)


def category():
    from apps.announcements.models import AnnouncementCategory

    return AnnouncementCategory.objects.get(code=CATEGORY)


def grant(user: User, *codenames: str) -> User:
    for codename in codenames:
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label="web", codename=codename)
        )
    return User.objects.get(pk=user.pk)


def assign(user, role: str, scope_type: str, scope_office=None) -> None:
    assignment = UserRoleAssignment(
        user=user, role=role, scope_type=scope_type, scope_office=scope_office
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()


def company_publisher(email="company.pub@example.com") -> User:
    user = completed_user(email=email, office=office("onest-head-office"))
    assign(user, "system_admin", "company")
    return grant(
        user, "manage_announcements", "publish_announcements", "pin_announcements"
    )


def regional_publisher(email="regional.pub@example.com") -> User:
    """Publisher whose grant stops at one region."""
    user = completed_user(email=email, office=office("harrisburg"))
    assign(user, "regional_admin", "region", office("region-mid-atlantic"))
    return grant(user, "manage_announcements", "publish_announcements")


def author_only(email="author@example.com") -> User:
    """Authoring authority and nothing else — the interesting negative case.

    Regional Admin is the reviewed bundle that carries ``manage_announcements``
    without ``publish_announcements``, so this persona is the real split rather
    than a permission set nobody actually holds.
    """
    user = completed_user(email=email, office=office("harrisburg"))
    assign(user, "regional_admin", "region", office("region-mid-atlantic"))
    return User.objects.get(pk=user.pk)


def reader(slug="fairfax-va", email="agent@example.com") -> User:
    """A plain recipient. Idempotent so a test can ask for the same one twice."""
    existing = User.objects.filter(email=email).first()
    return existing or completed_user(email=email, office=office(slug))


def draft_for(actor: User, *, owner_slug: str, selectors=None, **fields):
    payload = {
        "title": "Quarterly update",
        "summary": "What changed this quarter.",
        "body": "The full text of the notice.",
        "category": category(),
        "priority": PRIORITY,
        "publish_at": None,
        "expires_at": None,
        "cta_label": "",
        "cta_url": "",
    }
    payload.update(fields)
    return create_announcement(
        actor=actor,
        office=office(owner_slug),
        cleaned=payload,
        selectors=selectors
        or [AudienceSelector(kind="office", office=office("fairfax-va"))],
    )


def publish(actor: User, announcement: Announcement) -> Announcement:
    return transition(
        actor=actor,
        announcement=announcement,
        action="publish",
        expected_version=announcement_version(announcement),
    )


def inertia_props(response) -> dict:
    return json.loads(response.content.decode())["props"]


# --------------------------------------------------------------------------- #
# The full lifecycle
# --------------------------------------------------------------------------- #


def test_author_can_walk_draft_preview_publish_archive(seeded):
    actor = company_publisher()
    announcement = draft_for(actor, owner_slug="onest-head-office")

    assert announcement.status == Announcement.Status.DRAFT
    assert lifecycle_state(announcement)["code"] == "draft"
    # A draft is invisible to its own audience: nothing published it.
    assert not visible_queryset(reader()).filter(pk=announcement.pk).exists()

    # Previewing renders it without making it reachable.
    preview = preview_payload(announcement, office=office("fairfax-va"), role_code="")
    assert preview["article"]["title"] == "Quarterly update"
    assert preview["reach"]["matched"] is True
    assert not visible_queryset(reader()).filter(pk=announcement.pk).exists()

    published = transition(
        actor=actor,
        announcement=announcement,
        action="publish",
        expected_version=announcement_version(announcement),
    )
    assert published.status == Announcement.Status.PUBLISHED
    assert lifecycle_state(published)["code"] == "live"
    assert visible_queryset(reader()).filter(pk=published.pk).exists()

    archived = transition(
        actor=actor,
        announcement=published,
        action="archive",
        expected_version=announcement_version(published),
    )
    assert archived.status == Announcement.Status.ARCHIVED
    assert archived.archived_at is not None
    assert not visible_queryset(reader()).filter(pk=archived.pk).exists()


def test_scheduling_publishes_the_row_but_not_yet_the_words(seeded):
    actor = company_publisher()
    later = timezone.now() + timedelta(days=3)
    announcement = draft_for(actor, owner_slug="onest-head-office", publish_at=later)

    scheduled = transition(
        actor=actor,
        announcement=announcement,
        action="schedule",
        expected_version=announcement_version(announcement),
    )

    assert scheduled.status == Announcement.Status.PUBLISHED
    assert lifecycle_state(scheduled)["code"] == "scheduled"
    # The window predicate, not the status column, is what hides it.
    assert not visible_queryset(reader()).filter(pk=scheduled.pk).exists()
    assert (
        visible_queryset(reader(), now=later + timedelta(minutes=1))
        .filter(pk=scheduled.pk)
        .exists()
    )


def test_publish_refuses_a_future_dated_draft_without_saying_schedule(seeded):
    actor = company_publisher()
    announcement = draft_for(
        actor,
        owner_slug="onest-head-office",
        publish_at=timezone.now() + timedelta(days=1),
    )
    with pytest.raises(TransitionRefused):
        transition(
            actor=actor,
            announcement=announcement,
            action="publish",
            expected_version=announcement_version(announcement),
        )
    announcement.refresh_from_db()
    assert announcement.status == Announcement.Status.DRAFT


def test_schedule_refuses_when_the_publish_time_is_not_in_the_future(seeded):
    actor = company_publisher()
    announcement = draft_for(actor, owner_slug="onest-head-office")
    with pytest.raises(TransitionRefused):
        transition(
            actor=actor,
            announcement=announcement,
            action="schedule",
            expected_version=announcement_version(announcement),
        )


def test_an_expired_announcement_reads_as_expired_and_leaves_the_feed(seeded):
    actor = company_publisher()
    announcement = draft_for(
        actor,
        owner_slug="onest-head-office",
        expires_at=timezone.now() + timedelta(minutes=5),
    )
    published = transition(
        actor=actor,
        announcement=announcement,
        action="publish",
        expected_version=announcement_version(announcement),
    )
    after = timezone.now() + timedelta(hours=1)

    assert lifecycle_state(published, now=after)["code"] == "expired"
    assert not visible_queryset(reader(), now=after).filter(pk=published.pk).exists()


def test_unpublish_returns_to_draft_and_clears_the_publication_stamp(seeded):
    actor = company_publisher()
    published = publish(actor, draft_for(actor, owner_slug="onest-head-office"))
    reverted = transition(
        actor=actor,
        announcement=published,
        action="unpublish",
        expected_version=announcement_version(published),
    )
    assert reverted.status == Announcement.Status.DRAFT
    assert reverted.published_at is None
    assert not visible_queryset(reader()).filter(pk=reverted.pk).exists()


def test_restore_returns_an_archived_notice_to_draft_never_straight_to_live(seeded):
    actor = company_publisher()
    published = publish(actor, draft_for(actor, owner_slug="onest-head-office"))
    archived = transition(
        actor=actor,
        announcement=published,
        action="archive",
        expected_version=announcement_version(published),
    )
    restored = transition(
        actor=actor,
        announcement=archived,
        action="restore",
        expected_version=announcement_version(archived),
    )
    assert restored.status == Announcement.Status.DRAFT
    assert not visible_queryset(reader()).filter(pk=restored.pk).exists()


# --------------------------------------------------------------------------- #
# Publish-time validation
# --------------------------------------------------------------------------- #


def test_publishing_refuses_while_the_checklist_is_outstanding(seeded):
    actor = company_publisher()
    announcement = draft_for(
        actor, owner_slug="onest-head-office", body="", priority=""
    )
    with pytest.raises(ValidationError) as caught:
        transition(
            actor=actor,
            announcement=announcement,
            action="publish",
            expected_version=announcement_version(announcement),
        )
    assert set(caught.value.message_dict) >= {"body", "priority"}
    announcement.refresh_from_db()
    assert announcement.status == Announcement.Status.DRAFT


def test_a_draft_with_no_audience_is_refused_at_save_not_only_at_publish(seeded):
    from apps.announcements.forms import AnnouncementForm

    actor = company_publisher()
    form = AnnouncementForm(
        data={
            "owner_office": str(office("onest-head-office").pk),
            "title": "No audience",
            "body": "Words.",
            "category": CATEGORY,
            "priority": PRIORITY,
        },
        actor=actor,
    )
    assert not form.is_valid()
    assert "audience_company" in form.errors


# --------------------------------------------------------------------------- #
# Scope and over-targeting
# --------------------------------------------------------------------------- #


def test_a_scoped_publisher_never_sees_records_outside_their_region(seeded):
    company = company_publisher()
    inside = draft_for(company, owner_slug="harrisburg")
    outside = draft_for(company, owner_slug=OUTSIDE_REGION)

    visible = manageable_queryset(regional_publisher())

    assert inside.pk in set(visible.values_list("pk", flat=True))
    assert outside.pk not in set(visible.values_list("pk", flat=True))


def test_a_scoped_publisher_cannot_own_an_announcement_outside_their_grant(seeded):
    with pytest.raises(PermissionDenied):
        draft_for(regional_publisher(), owner_slug=OUTSIDE_REGION)


def test_a_scoped_publisher_cannot_address_the_whole_company(seeded):
    actor = regional_publisher()
    with pytest.raises(PermissionDenied):
        draft_for(
            actor,
            owner_slug="harrisburg",
            selectors=[AudienceSelector(kind="company")],
        )


def test_a_crafted_office_id_is_refused_even_though_no_control_offered_it(seeded):
    actor = regional_publisher()
    with pytest.raises(PermissionDenied):
        draft_for(
            actor,
            owner_slug="harrisburg",
            selectors=[AudienceSelector(kind="office", office=office(OUTSIDE_REGION))],
        )


def test_a_crafted_named_recipient_outside_the_grant_is_refused(seeded):
    actor = regional_publisher()
    stranger = reader(slug=OUTSIDE_REGION, email="stranger@example.com")
    with pytest.raises(PermissionDenied):
        draft_for(
            actor,
            owner_slug="harrisburg",
            selectors=[AudienceSelector(kind="user", user=stranger)],
        )


def test_narrowing_a_publisher_grant_stops_a_republish_of_their_own_draft(seeded):
    """Authority is re-derived at publish, not trusted from compose time."""
    actor = company_publisher()
    announcement = draft_for(
        actor,
        owner_slug="onest-head-office",
        selectors=[AudienceSelector(kind="company")],
    )
    UserRoleAssignment.objects.filter(user=actor).delete()
    actor.user_permissions.clear()
    narrowed = User.objects.get(pk=actor.pk)

    with pytest.raises(PermissionDenied):
        transition(
            actor=narrowed,
            announcement=announcement,
            action="publish",
            expected_version=announcement_version(announcement),
        )


# --------------------------------------------------------------------------- #
# Separated grants
# --------------------------------------------------------------------------- #


def test_an_author_without_the_publish_grant_can_save_but_not_publish(seeded):
    actor = author_only()
    announcement = draft_for(actor, owner_slug="harrisburg")

    updated = update_announcement(
        actor=actor,
        announcement=announcement,
        cleaned={"title": "Reworded"},
        selectors=[AudienceSelector(kind="office", office=office("fairfax-va"))],
        expected_version=announcement_version(announcement),
    )
    assert updated.title == "Reworded"

    with pytest.raises(PermissionDenied):
        transition(
            actor=actor,
            announcement=updated,
            action="publish",
            expected_version=announcement_version(updated),
        )
    updated.refresh_from_db()
    assert updated.status == Announcement.Status.DRAFT


def test_pinning_needs_its_own_grant_and_only_applies_to_published_rows(seeded):
    publisher = company_publisher()
    without_pin = regional_publisher()
    announcement = draft_for(publisher, owner_slug="harrisburg")

    with pytest.raises(PermissionDenied):
        set_pinned(
            actor=without_pin,
            announcement=announcement,
            pinned=True,
            expected_version=announcement_version(announcement),
        )
    with pytest.raises(TransitionRefused):
        set_pinned(
            actor=publisher,
            announcement=announcement,
            pinned=True,
            expected_version=announcement_version(announcement),
        )


def test_a_pin_lifts_order_without_widening_the_audience(seeded):
    actor = company_publisher()
    quiet = publish(
        actor,
        draft_for(
            actor,
            owner_slug="onest-head-office",
            title="Quiet notice",
            selectors=[AudienceSelector(kind="office", office=office("fairfax-va"))],
        ),
    )
    elsewhere = publish(
        actor,
        draft_for(
            actor,
            owner_slug="onest-head-office",
            title="Somewhere else",
            selectors=[AudienceSelector(kind="office", office=office("harrisburg"))],
        ),
    )
    set_pinned(
        actor=actor,
        announcement=elsewhere,
        pinned=True,
        expected_version=announcement_version(elsewhere),
    )

    rows = list(order_for_feed(visible_queryset(reader())))

    assert [row.pk for row in rows] == [quiet.pk]


def test_archiving_takes_the_pin_with_it(seeded):
    actor = company_publisher()
    published = publish(actor, draft_for(actor, owner_slug="onest-head-office"))
    pinned = set_pinned(
        actor=actor,
        announcement=published,
        pinned=True,
        expected_version=announcement_version(published),
    )
    archived = transition(
        actor=actor,
        announcement=pinned,
        action="archive",
        expected_version=announcement_version(pinned),
    )
    assert archived.is_pinned is False
    assert archived.pinned_at is None


# --------------------------------------------------------------------------- #
# Concurrency
# --------------------------------------------------------------------------- #


def test_a_stale_version_token_refuses_rather_than_overwriting(seeded):
    actor = company_publisher()
    announcement = draft_for(actor, owner_slug="onest-head-office")
    stale = announcement_version(announcement)

    update_announcement(
        actor=actor,
        announcement=announcement,
        cleaned={"title": "Their wording"},
        selectors=[AudienceSelector(kind="office", office=office("fairfax-va"))],
        expected_version=stale,
    )

    with pytest.raises(StaleAnnouncementVersion):
        update_announcement(
            actor=actor,
            announcement=announcement,
            cleaned={"title": "My wording"},
            selectors=[AudienceSelector(kind="office", office=office("fairfax-va"))],
            expected_version=stale,
        )
    announcement.refresh_from_db()
    assert announcement.title == "Their wording"


def test_a_stale_token_also_blocks_a_lifecycle_move(seeded):
    actor = company_publisher()
    announcement = draft_for(actor, owner_slug="onest-head-office")
    stale = announcement_version(announcement)
    update_announcement(
        actor=actor,
        announcement=announcement,
        cleaned={"summary": "Edited elsewhere"},
        selectors=[AudienceSelector(kind="office", office=office("fairfax-va"))],
        expected_version=stale,
    )

    with pytest.raises(StaleAnnouncementVersion):
        transition(
            actor=actor,
            announcement=announcement,
            action="publish",
            expected_version=stale,
        )
    announcement.refresh_from_db()
    assert announcement.status == Announcement.Status.DRAFT


# --------------------------------------------------------------------------- #
# Audit and domain events
# --------------------------------------------------------------------------- #


def test_every_lifecycle_step_leaves_an_audit_row_with_before_and_after(seeded):
    actor = company_publisher()
    announcement = draft_for(actor, owner_slug="onest-head-office")
    published = transition(
        actor=actor,
        announcement=announcement,
        action="publish",
        expected_version=announcement_version(announcement),
    )
    transition(
        actor=actor,
        announcement=published,
        action="archive",
        expected_version=announcement_version(published),
    )

    actions = list(
        AuditEvent.objects.filter(
            target_type=Announcement._meta.label_lower,
            target_id=str(announcement.pk),
            outcome=AuditEvent.Outcome.SUCCESS,
        ).values_list("action", flat=True)
    )
    assert "announcement.created" in actions
    assert "announcement.published" in actions
    assert "announcement.archived" in actions

    archived_row = AuditEvent.objects.get(
        action="announcement.archived", target_id=str(announcement.pk)
    )
    assert archived_row.before["status"] == Announcement.Status.PUBLISHED
    assert archived_row.after["status"] == Announcement.Status.ARCHIVED


def test_a_denied_publish_attempt_is_recorded(seeded):
    actor = author_only()
    announcement = draft_for(actor, owner_slug="harrisburg")
    with pytest.raises(PermissionDenied):
        transition(
            actor=actor,
            announcement=announcement,
            action="publish",
            expected_version=announcement_version(announcement),
        )
    assert AuditEvent.objects.filter(
        action="security.announcement.denied",
        outcome=AuditEvent.Outcome.DENIED,
        reason="missing_publish_permission",
    ).exists()


def test_publishing_emits_the_published_event_only_after_the_commit(seeded):
    actor = company_publisher()
    announcement = draft_for(actor, owner_slug="onest-head-office")
    transition(
        actor=actor,
        announcement=announcement,
        action="publish",
        expected_version=announcement_version(announcement),
    )
    event = DomainEvent.objects.get(
        name="announcement.published", subject=str(announcement.pk)
    )
    assert event.payload["announcement_id"] == announcement.pk
    assert event.payload["visible_from"] is not None


def test_scheduling_emits_scheduled_rather_than_published(seeded):
    """A consumer must not notify people about news they cannot open yet."""
    actor = company_publisher()
    announcement = draft_for(
        actor,
        owner_slug="onest-head-office",
        publish_at=timezone.now() + timedelta(days=2),
    )
    transition(
        actor=actor,
        announcement=announcement,
        action="schedule",
        expected_version=announcement_version(announcement),
    )
    assert DomainEvent.objects.filter(
        name="announcement.scheduled", subject=str(announcement.pk)
    ).exists()
    assert not DomainEvent.objects.filter(
        name="announcement.published", subject=str(announcement.pk)
    ).exists()


def test_publication_history_reads_the_audit_trail_newest_first(seeded):
    actor = company_publisher()
    announcement = draft_for(actor, owner_slug="onest-head-office")
    transition(
        actor=actor,
        announcement=announcement,
        action="publish",
        expected_version=announcement_version(announcement),
    )

    history = publication_history(announcement)

    actions = [row["action"] for row in history]
    assert actions[0] == "announcement.published"
    assert "announcement.created" in actions
    assert all(row["actor"] for row in history)


# --------------------------------------------------------------------------- #
# Filters
# --------------------------------------------------------------------------- #


def _filters(**values) -> WorkspaceFilters:
    return WorkspaceFilters.from_params(
        values, known_categories=[CATEGORY], known_priorities=[PRIORITY]
    )


def test_lifecycle_filters_split_scheduled_live_and_expired(seeded):
    actor = company_publisher()
    live = publish(
        actor, draft_for(actor, owner_slug="onest-head-office", title="Live")
    )
    later = draft_for(
        actor,
        owner_slug="onest-head-office",
        title="Later",
        publish_at=timezone.now() + timedelta(days=2),
    )
    scheduled = transition(
        actor=actor,
        announcement=later,
        action="schedule",
        expected_version=announcement_version(later),
    )
    base = manageable_queryset(actor)

    assert list(
        apply_workspace_filters(base, _filters(lifecycle="live")).values_list(
            "pk", flat=True
        )
    ) == [live.pk]
    assert list(
        apply_workspace_filters(base, _filters(lifecycle="scheduled")).values_list(
            "pk", flat=True
        )
    ) == [scheduled.pk]


def test_an_unknown_filter_value_is_dropped_rather_than_applied(seeded):
    filters = _filters(lifecycle="whenever", priority="loudest")
    assert filters.lifecycle == ""
    assert filters.priority == ""


def test_the_audience_filter_finds_records_by_selector_kind(seeded):
    actor = company_publisher()
    by_office = draft_for(actor, owner_slug="onest-head-office", title="Office one")
    draft_for(
        actor,
        owner_slug="onest-head-office",
        title="Everyone",
        selectors=[AudienceSelector(kind="company")],
    )

    rows = apply_workspace_filters(
        manageable_queryset(actor), _filters(audience="office")
    )

    assert list(rows.values_list("pk", flat=True)) == [by_office.pk]


# --------------------------------------------------------------------------- #
# Preview
# --------------------------------------------------------------------------- #


def test_preview_reports_a_reader_the_audience_does_not_reach(seeded):
    actor = company_publisher()
    announcement = draft_for(
        actor,
        owner_slug="onest-head-office",
        selectors=[AudienceSelector(kind="office", office=office("fairfax-va"))],
    )

    hit = preview_payload(announcement, office=office("fairfax-va"), role_code="")
    miss = preview_payload(announcement, office=office("harrisburg"), role_code="")

    assert hit["reach"]["matched"] is True
    assert miss["reach"]["matched"] is False


def test_preview_carries_the_same_payload_shape_the_reader_page_renders(seeded):
    from apps.announcements.services import feed_row

    actor = company_publisher()
    announcement = draft_for(actor, owner_slug="onest-head-office")

    article = preview_payload(announcement, office=None, role_code="")["article"]

    assert set(feed_row(announcement)).issubset(article)
    assert set(article) >= {"audience", "hero", "attachments"}


# --------------------------------------------------------------------------- #
# HTTP surface
# --------------------------------------------------------------------------- #


def test_an_agent_cannot_reach_any_management_endpoint(seeded, client):
    actor = company_publisher()
    announcement = draft_for(actor, owner_slug="onest-head-office")
    client.force_login(reader())

    assert client.get(reverse("admin_announcements")).status_code == 403
    assert client.get(reverse("announcement_new")).status_code == 403
    assert (
        client.get(reverse("announcement_edit", args=[announcement.pk])).status_code
        == 403
    )
    assert (
        client.post(
            reverse("announcement_lifecycle", args=[announcement.pk]),
            {"action": "publish"},
        ).status_code
        == 403
    )
    announcement.refresh_from_db()
    assert announcement.status == Announcement.Status.DRAFT


def test_an_out_of_scope_record_is_a_404_not_a_403(seeded, client):
    company = company_publisher()
    outside = draft_for(company, owner_slug=OUTSIDE_REGION)
    client.force_login(regional_publisher())

    response = client.get(reverse("announcement_edit", args=[outside.pk]))

    assert response.status_code == 404


def test_an_author_without_the_publish_grant_is_refused_by_the_route(seeded, client):
    actor = author_only()
    announcement = draft_for(actor, owner_slug="harrisburg")
    client.force_login(actor)

    response = client.post(
        reverse("announcement_lifecycle", args=[announcement.pk]),
        {"action": "publish", "expected_version": announcement_version(announcement)},
    )

    assert response.status_code == 403
    announcement.refresh_from_db()
    assert announcement.status == Announcement.Status.DRAFT


def test_a_concurrent_save_answers_409_with_the_current_values(seeded, client):
    actor = company_publisher()
    announcement = draft_for(actor, owner_slug="onest-head-office")
    stale = announcement_version(announcement)
    update_announcement(
        actor=actor,
        announcement=announcement,
        cleaned={"title": "Their wording"},
        selectors=[AudienceSelector(kind="office", office=office("fairfax-va"))],
        expected_version=stale,
    )
    client.force_login(actor)

    response = client.post(
        reverse("announcement_update", args=[announcement.pk]),
        {
            "owner_office": str(office("onest-head-office").pk),
            "title": "My wording",
            "body": "Words.",
            "category": CATEGORY,
            "priority": PRIORITY,
            "audience_offices": [str(office("fairfax-va").pk)],
            "expected_version": stale,
        },
        HTTP_X_INERTIA="true",
    )

    assert response.status_code == 409
    props = inertia_props(response)
    assert props["announcement"]["title"] == "Their wording"
    announcement.refresh_from_db()
    assert announcement.title == "Their wording"


def test_the_workspace_index_lists_only_records_in_scope(seeded, client):
    company = company_publisher()
    inside = draft_for(company, owner_slug="harrisburg", title="In region")
    outside = draft_for(company, owner_slug=OUTSIDE_REGION, title="Elsewhere")
    client.force_login(regional_publisher())

    props = inertia_props(
        client.get(reverse("admin_announcements"), HTTP_X_INERTIA="true")
    )

    ids = {row["id"] for row in props["announcements"]["items"]}
    assert inside.pk in ids
    assert outside.pk not in ids
    assert props["capabilities"] == {
        "canAuthor": True,
        "canPublish": True,
        "canPin": False,
    }


def test_creating_through_the_route_saves_a_draft_and_notifies_nobody(seeded, client):
    actor = company_publisher()
    client.force_login(actor)

    response = client.post(
        reverse("announcement_create"),
        {
            "owner_office": str(office("onest-head-office").pk),
            "title": "Fresh notice",
            "summary": "Short version.",
            "body": "Long version.",
            "category": CATEGORY,
            "priority": PRIORITY,
            "audience_offices": [str(office("fairfax-va").pk)],
        },
    )

    assert response.status_code == 302
    saved = Announcement.objects.get(title="Fresh notice")
    assert saved.status == Announcement.Status.DRAFT
    assert saved.created_by == actor
    assert saved.updated_by == actor
    assert not DomainEvent.objects.filter(subject=str(saved.pk)).exists()
    assert AnnouncementAudience.objects.filter(announcement=saved).count() == 1


def test_the_create_drawer_reopens_on_the_queue_with_the_draft_intact(seeded, client):
    """A rejected create answers with the list page, not the standalone form."""
    client.force_login(company_publisher())

    response = client.post(
        reverse("announcement_create"),
        {
            "context": "sheet",
            "owner_office": str(office("onest-head-office").pk),
            "title": "Half-written notice",
            # No body and no audience: two different reasons to refuse.
            "category": CATEGORY,
            "priority": PRIORITY,
        },
        HTTP_X_INERTIA="true",
    )

    assert response.status_code == 422
    payload = json.loads(response.content.decode())
    assert payload["component"] == "AnnouncementAdministration"
    props = payload["props"]
    assert props["createSheet"]["open"] is True
    assert props["createSheet"]["draft"]["title"] == "Half-written notice"
    assert props["errors"]["fields"]
    assert not Announcement.objects.filter(title="Half-written notice").exists()


def test_every_value_the_drawer_offers_is_a_value_the_create_accepts(seeded, client):
    """The regression guard for option/field key mismatches.

    Hand-written literals in a test can agree with the form while disagreeing
    with the controls a person actually uses — which is exactly how the category
    picker shipped posting a stable code at a field keyed by primary key. This
    posts what the server itself advertises in ``createOptions``, so the two
    halves of the contract cannot drift apart again without failing here.
    """
    client.force_login(company_publisher())
    options = inertia_props(
        client.get(reverse("admin_announcements"), HTTP_X_INERTIA="true")
    )["createOptions"]

    response = client.post(
        reverse("announcement_create"),
        {
            "context": "sheet",
            "owner_office": str(options["offices"][0]["value"]),
            "title": "Built from the advertised options",
            "body": "Words.",
            "category": options["categories"][0]["value"],
            "priority": options["priorities"][0]["value"],
            "audience_offices": [str(options["audience"]["offices"][0]["value"])],
            "audience_roles": [options["audience"]["roles"][0]["value"]],
        },
    )

    assert response.status_code == 302, response.content
    saved = Announcement.objects.get(title="Built from the advertised options")
    assert saved.category is not None
    assert saved.category.code == options["categories"][0]["value"]
    assert saved.priority == options["priorities"][0]["value"]


def test_the_category_field_is_keyed_by_its_stable_code(seeded, client):
    """A primary key is not the wire format, even though one exists."""
    client.force_login(company_publisher())
    payload = {
        "context": "sheet",
        "owner_office": str(office("onest-head-office").pk),
        "title": "Keyed by code",
        "body": "Words.",
        "priority": PRIORITY,
        "audience_offices": [str(office("fairfax-va").pk)],
    }

    accepted = client.post(
        reverse("announcement_create"), {**payload, "category": CATEGORY}
    )
    assert accepted.status_code == 302
    saved = Announcement.objects.get(title="Keyed by code")
    assert saved.category is not None
    assert saved.category.code == CATEGORY

    by_pk = client.post(
        reverse("announcement_create"),
        {**payload, "title": "Keyed by pk", "category": str(category().pk)},
        HTTP_X_INERTIA="true",
    )
    assert by_pk.status_code == 422
    assert not Announcement.objects.filter(title="Keyed by pk").exists()


def test_the_drawer_lands_in_the_workspace_once_the_draft_saves(seeded, client):
    client.force_login(company_publisher())

    response = client.post(
        reverse("announcement_create"),
        {
            "context": "sheet",
            "owner_office": str(office("onest-head-office").pk),
            "title": "From the drawer",
            "body": "Words.",
            "category": CATEGORY,
            "priority": PRIORITY,
            "audience_offices": [str(office("fairfax-va").pk)],
        },
    )

    saved = Announcement.objects.get(title="From the drawer")
    assert response.status_code == 302
    assert response.url == reverse("announcement_edit", args=[saved.pk])
    assert saved.status == Announcement.Status.DRAFT


def test_the_drawer_cannot_be_used_to_reach_an_office_outside_the_grant(seeded, client):
    client.force_login(regional_publisher())

    response = client.post(
        reverse("announcement_create"),
        {
            "context": "sheet",
            "owner_office": str(office(OUTSIDE_REGION).pk),
            "title": "Crafted through the drawer",
            "body": "Words.",
            "category": CATEGORY,
            "priority": PRIORITY,
            "audience_offices": [str(office(OUTSIDE_REGION).pk)],
        },
        HTTP_X_INERTIA="true",
    )

    assert response.status_code == 422
    assert not Announcement.objects.filter(title="Crafted through the drawer").exists()


def test_the_queue_offers_only_grant_bounded_choices_to_the_drawer(seeded, client):
    client.force_login(regional_publisher())

    props = inertia_props(
        client.get(reverse("admin_announcements"), HTTP_X_INERTIA="true")
    )

    options = props["createOptions"]
    assert props["createSheet"] is None
    assert options["audience"]["canTargetCompany"] is False
    labels = {row["label"] for row in options["offices"]}
    assert office(OUTSIDE_REGION).name not in labels


def test_a_submitted_office_outside_the_grant_fails_form_validation(seeded, client):
    client.force_login(regional_publisher())

    response = client.post(
        reverse("announcement_create"),
        {
            "owner_office": str(office(OUTSIDE_REGION).pk),
            "title": "Crafted",
            "body": "Words.",
            "category": CATEGORY,
            "priority": PRIORITY,
            "audience_offices": [str(office("fairfax-va").pk)],
        },
        HTTP_X_INERTIA="true",
    )

    assert response.status_code == 422
    assert not Announcement.objects.filter(title="Crafted").exists()
