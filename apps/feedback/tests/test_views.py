"""The HTTP surface: routes, denial, and the screenshot authorization.

The service tests cover the rules; this file covers the wiring — that the
routes exist, that they refuse the right people, and that a screenshot is
genuinely unreachable by somebody who may not open its ticket.
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.urls import reverse

from apps.feedback.models import FeedbackTicket
from apps.feedback.taxonomy import FeedbackCategory, FeedbackUrgency
from apps.user.models import Office, UserRoleAssignment
from apps.user.tests.test_profile import completed_user


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()
    cache.clear()


def office(slug: str = "fairfax-va") -> Office:
    return Office.objects.get(slug=slug)


def person(email: str, slug: str = "fairfax-va"):
    return completed_user(email=email, office=office(slug))


def grant(user, *codenames: str) -> None:
    for codename in codenames:
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label="web", codename=codename)
        )
    user.refresh_from_db()


def assign_role(user, role: str, scope_type: str, scope_office=None) -> None:
    assignment = UserRoleAssignment(
        user=user, role=role, scope_type=scope_type, scope_office=scope_office
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()


def post_report(client, *, key="k-1", **overrides):
    payload = {
        "submissionKey": key,
        "category": FeedbackCategory.BUG,
        "summary": "Contracts page will not load",
        "description": "It spins forever.",
        "urgency": FeedbackUrgency.SLOWING,
        "pageUrl": "/contracts?token=supersecret&page=2",
        "browserMetadata": json.dumps({"viewport": "1280x720", "cookies": "no"}),
    }
    payload.update(overrides)
    return client.post(reverse("feedback_create"), payload)


# --------------------------------------------------------------------------- #
# Submission
# --------------------------------------------------------------------------- #


def test_the_form_is_open_to_any_signed_in_person(seeded, client):
    client.force_login(person("agent@example.com"))
    response = client.get(reverse("feedback_submit"), HTTP_X_INERTIA="true")
    assert response.status_code == 200


def test_the_form_carries_the_page_the_reader_came_from(seeded, client):
    """`document.referrer` is empty for an Inertia visit, so the trigger
    appends `?from=` and the server scrubs it here as well as on submit."""
    client.force_login(person("agent@example.com"))
    response = client.get(
        reverse("feedback_submit")
        + "?from=/operations/tasks%3Ftoken%3Dleak%26page%3D2",
        HTTP_X_INERTIA="true",
    )
    props = json.loads(response.content)["props"]
    assert props["pageUrl"] == "/operations/tasks?page=2"
    assert "leak" not in props["pageUrl"]


def test_a_filtered_page_survives_the_round_trip(seeded, client):
    """The whole fix, end to end.

    The sidebar sends the full url including its query; the redaction layer
    keeps the allowlisted filters — which are the useful part, "page 3 of the
    filtered list" being where the thing broke — and drops the secret.
    """
    from urllib.parse import quote

    client.force_login(person("agent@example.com"))
    origin = "/users?page=3&status=active&token=supersecretvalue"
    response = client.get(
        reverse("feedback_submit") + "?from=" + quote(origin, safe=""),
        HTTP_X_INERTIA="true",
    )
    stored = json.loads(response.content)["props"]["pageUrl"]

    assert stored == "/users?page=3&status=active"
    assert "supersecretvalue" not in stored


def test_a_hostile_from_parameter_renders_the_form_rather_than_failing(seeded, client):
    """This is the page somebody reaches when something is broken. Refusing to
    render it because a query parameter was hand-edited denies them the one
    thing they came for; the value is simply dropped."""
    client.force_login(person("agent@example.com"))
    response = client.get(
        reverse("feedback_submit") + "?from=https://evil.example/x",
        HTTP_X_INERTIA="true",
    )
    assert response.status_code == 200
    assert json.loads(response.content)["props"]["pageUrl"] == ""


def test_the_form_lists_the_offices_real_support_contacts(seeded, client):
    from apps.user.models import OfficeContactAssignment

    agent = person("agent@example.com")
    helper = person("it@example.com")
    OfficeContactAssignment.objects.create(
        office=office(),
        user=helper,
        assignment_type=OfficeContactAssignment.AssignmentType.IT_SUPPORT,
        is_primary=True,
    )
    client.force_login(agent)

    response = client.get(reverse("feedback_submit"), HTTP_X_INERTIA="true")
    contacts = json.loads(response.content)["props"]["contacts"]

    assert [c["key"] for c in contacts] == ["itSupport"]
    assert contacts[0]["email"] == helper.email


def test_an_office_with_no_contacts_lists_none(seeded, client):
    """A fabricated contact is worse than none."""
    client.force_login(person("agent@example.com"))
    response = client.get(reverse("feedback_submit"), HTTP_X_INERTIA="true")
    assert json.loads(response.content)["props"]["contacts"] == []


def test_an_anonymous_visitor_cannot_reach_the_form(seeded, client):
    response = client.get(reverse("feedback_submit"))
    assert response.status_code in {302, 401, 403}


def test_submitting_redirects_to_the_ticket_and_scrubs_diagnostics(seeded, client):
    agent = person("agent@example.com")
    client.force_login(agent)

    response = post_report(client)

    ticket = FeedbackTicket.objects.get()
    assert response.status_code == 302
    assert response.headers["Location"] == reverse(
        "feedback_detail", args=[str(ticket.public_id)]
    )
    # Redirect-after-post so a refresh cannot repeat the write.
    assert ticket.page_url == "/contracts?page=2"
    assert "supersecret" not in ticket.page_url
    assert ticket.browser_metadata == {"viewport": "1280x720"}


def test_unparseable_metadata_does_not_lose_the_report(seeded, client):
    """The report matters more than the diagnostics."""
    client.force_login(person("agent@example.com"))
    response = post_report(client, browserMetadata="not json at all")
    assert response.status_code == 302
    assert FeedbackTicket.objects.get().browser_metadata == {}


def test_a_refused_submission_answers_422_with_the_form_repopulated(seeded, client):
    client.force_login(person("agent@example.com"))
    response = post_report(client, category="", HTTP_X_INERTIA="true")
    assert response.status_code == 422
    assert FeedbackTicket.objects.count() == 0


def test_replaying_the_same_submission_key_creates_one_ticket(seeded, client):
    client.force_login(person("agent@example.com"))
    post_report(client, key="same")
    post_report(client, key="same")
    assert FeedbackTicket.objects.count() == 1


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #


def test_a_submitter_reads_their_own_ticket(seeded, client):
    agent = person("agent@example.com")
    client.force_login(agent)
    post_report(client)
    ticket = FeedbackTicket.objects.get()

    response = client.get(
        reverse("feedback_detail", args=[str(ticket.public_id)]),
        HTTP_X_INERTIA="true",
    )
    assert response.status_code == 200


def test_a_stranger_gets_404_not_403_for_somebody_elses_ticket(seeded, client):
    """Confirming that a ticket exists is itself a disclosure."""
    client.force_login(person("agent@example.com"))
    post_report(client)
    ticket = FeedbackTicket.objects.get()

    client.force_login(person("stranger@example.com"))
    response = client.get(reverse("feedback_detail", args=[str(ticket.public_id)]))
    assert response.status_code == 404


def test_the_inbox_refuses_somebody_without_the_triage_grant(seeded, client):
    client.force_login(person("agent@example.com"))
    response = client.get(reverse("admin_feedback"))
    assert response.status_code in {302, 403}


def test_the_inbox_opens_for_a_triager(seeded, client):
    staff = person("staff@example.com")
    assign_role(staff, "system_admin", "company")
    grant(staff, "view_feedback", "triage_feedback")
    client.force_login(staff)

    response = client.get(reverse("admin_feedback"), HTTP_X_INERTIA="true")

    assert response.status_code == 200
    # The *component*, not just the status. `apps.web.urls` builds a Coming
    # Soon route for every operations destination, and that placeholder also
    # answers 200 — asserting the status alone let this route serve the
    # placeholder for two commits without a single test noticing.
    assert json.loads(response.content)["component"] == "FeedbackInbox"


def test_every_live_destination_resolves_to_its_real_view(seeded):
    """The registry's Coming Soon route must not shadow a built module.

    A duplicate ``path()`` in the module's own urls.py only wins if the include
    order happens to favour it; the override in ``OPERATIONS_VIEWS`` is what
    actually decides. This checks the outcome rather than the mechanism.
    """
    from django.urls import resolve

    from apps.web.views import coming_soon

    for name in ("admin_feedback", "operational_tasks"):
        served = resolve(reverse(name)).func
        assert served is not coming_soon, f"{name} resolves to the placeholder"
        assert getattr(served, "__module__", "").startswith("apps."), name


# --------------------------------------------------------------------------- #
# Triage actions
# --------------------------------------------------------------------------- #


def triager(email="staff@example.com", slug="fairfax-va"):
    staff = person(email, slug)
    assign_role(staff, "system_admin", "company")
    grant(staff, "view_feedback", "triage_feedback", "assign_feedback")
    return staff


def test_a_triager_can_assign_and_prioritise_from_the_ticket(seeded, client):
    """Both endpoints had no control anywhere until now."""
    client.force_login(person("agent@example.com"))
    post_report(client)
    ticket = FeedbackTicket.objects.get()

    staff = triager()
    client.force_login(staff)

    assign = client.post(
        reverse("feedback_assign", args=[str(ticket.public_id)]),
        {"assignee": str(staff.pk)},
    )
    prioritise = client.post(
        reverse("feedback_prioritise", args=[str(ticket.public_id)]),
        {"priority": "critical"},
    )

    ticket.refresh_from_db()
    assert assign.status_code == 302
    assert prioritise.status_code == 302
    assert ticket.assignee_pk == staff.pk
    assert ticket.priority == 1


def test_the_assignee_picker_is_scoped_before_it_is_serialized(seeded, client):
    """It must never become a company-wide staff directory for a branch."""
    triager("company@example.com", "onest-head-office")
    local = person("localstaff@example.com", "fairfax-va")
    grant(local, "view_feedback", "triage_feedback")
    assign_role(local, "branch_manager", "office", office("fairfax-va"))

    client.force_login(person("agent@example.com"))
    post_report(client)
    ticket = FeedbackTicket.objects.get()

    client.force_login(local)
    response = client.get(
        reverse("feedback_detail", args=[str(ticket.public_id)]),
        HTTP_X_INERTIA="true",
    )
    names = {p["id"] for p in json.loads(response.content)["props"]["assignees"]}

    assert local.pk in names
    # The company-scoped triager sits outside this branch manager's reach.
    assert all(pk == local.pk for pk in names)


def test_a_reader_without_triage_gets_no_assignee_list(seeded, client):
    agent = person("agent@example.com")
    client.force_login(agent)
    post_report(client)
    ticket = FeedbackTicket.objects.get()

    response = client.get(
        reverse("feedback_detail", args=[str(ticket.public_id)]),
        HTTP_X_INERTIA="true",
    )
    assert json.loads(response.content)["props"]["assignees"] == []


def test_an_unknown_assignee_is_refused_without_touching_the_ticket(seeded, client):
    client.force_login(person("agent@example.com"))
    post_report(client)
    ticket = FeedbackTicket.objects.get()

    client.force_login(triager())
    response = client.post(
        reverse("feedback_assign", args=[str(ticket.public_id)]),
        {"assignee": "999999"},
        HTTP_X_INERTIA="true",
    )

    ticket.refresh_from_db()
    assert response.status_code == 422
    assert ticket.assignee_pk is None


# --------------------------------------------------------------------------- #
# Screenshot
# --------------------------------------------------------------------------- #


def _tiny_png() -> bytes:
    import base64

    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
        "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )


@pytest.fixture
def ticket_with_screenshot(seeded, client, tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    from django.core.files.uploadedfile import SimpleUploadedFile

    agent = person("agent@example.com")
    client.force_login(agent)
    post_report(
        client,
        screenshot=SimpleUploadedFile("broken.png", _tiny_png(), "image/png"),
    )
    return agent, FeedbackTicket.objects.get()


def test_the_submitter_can_open_their_own_screenshot(client, ticket_with_screenshot):
    agent, ticket = ticket_with_screenshot
    shot = ticket.screenshots.get()
    client.force_login(agent)

    response = client.get(
        reverse(
            "feedback_screenshot", args=[str(ticket.public_id), str(shot.public_id)]
        )
    )
    assert response.status_code == 200
    # Private, and never stored by a shared cache: the same URL means different
    # things to different readers.
    assert "no-store" in response.headers["Cache-Control"]


def test_a_stranger_cannot_open_the_screenshot(seeded, client, ticket_with_screenshot):
    """The parent ticket is loaded through the reader's scoped queryset first,
    so an id outside their reach 404s before any file is touched."""
    _agent, ticket = ticket_with_screenshot
    shot = ticket.screenshots.get()

    client.force_login(person("stranger@example.com"))
    response = client.get(
        reverse(
            "feedback_screenshot", args=[str(ticket.public_id), str(shot.public_id)]
        )
    )
    assert response.status_code == 404


def test_the_screenshot_payload_carries_a_route_not_a_storage_path(
    client, ticket_with_screenshot
):
    from apps.feedback.payloads import screenshot_payload

    _agent, ticket = ticket_with_screenshot
    payload = screenshot_payload(ticket.screenshots.get())

    shot = ticket.screenshots.get()
    # A route the view re-authorizes, not a location the file lives at.
    assert payload["href"] == reverse(
        "feedback_screenshot", args=[str(ticket.public_id), str(shot.public_id)]
    )
    # Nothing durable that could outlive the reader's access, and no trace of
    # where the bytes actually sit.
    assert "http" not in payload["href"]
    assert str(shot.image.name) not in payload["href"]


def test_a_non_image_upload_is_refused(seeded, client, tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    from django.core.files.uploadedfile import SimpleUploadedFile

    client.force_login(person("agent@example.com"))
    response = post_report(
        client,
        screenshot=SimpleUploadedFile(
            "payload.pdf", b"%PDF-1.4 fake", "application/pdf"
        ),
        HTTP_X_INERTIA="true",
    )
    assert response.status_code == 422
    assert FeedbackTicket.objects.count() == 0
