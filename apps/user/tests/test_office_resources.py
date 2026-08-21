"""Office resources: visibility inheritance, windows, search, downloads."""

from __future__ import annotations

import json

import pytest
from django.core.files.base import ContentFile
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.audit.models import AuditEvent
from apps.user.models import OfficeResource
from apps.user.services.office_resources import (
    ResourceFilters,
    effective_resources,
    office_resources_page_payload,
)
from apps.user.tests.test_profile import completed_user


def slug_set(user) -> set[str]:
    return {item.slug for item in effective_resources(user)}


def make_resource(office, slug, *, category="general", **kwargs) -> OfficeResource:
    return OfficeResource(
        owner_office=office,
        slug=slug,
        title=kwargs.pop("title", slug.replace("-", " ").title()),
        category=category,
        resource_type=kwargs.pop("resource_type", "content"),
        body=kwargs.pop("body", "Do the thing."),
        **kwargs,
    )


def office(slug):
    from apps.user.models import Office

    return Office.objects.get(slug=slug)


@pytest.fixture
def seeded_offices():
    from apps.user.office_seed import seed_offices

    seed_offices()


@pytest.mark.django_db
def test_visibility_across_scope_chain(seeded_offices):
    agent = completed_user(email="agent@example.com", office=office("fairfax-va"))
    make_resource(office("onest-head-office"), "company-handbook").save()
    make_resource(office("region-mid-atlantic"), "midatlantic-procedures").save()
    make_resource(office("fairfax-va"), "wifi-password").save()
    make_resource(
        office("charlottesville-va"), "charlottesville-only"
    ).save()  # another branch — must not leak
    slugs = slug_set(agent)
    assert {"company-handbook", "midatlantic-procedures", "wifi-password"} <= slugs
    assert "charlottesville-only" not in slugs


@pytest.mark.django_db
def test_closest_scope_overrides_same_slug(seeded_offices):
    agent = completed_user(email="agent@example.com", office=office("fairfax-va"))
    company_copy = make_resource(
        office("onest-head-office"), "wifi-password", body="Company default."
    )
    company_copy.save()
    branch_copy = make_resource(
        office("fairfax-va"), "wifi-password", body="Branch override."
    )
    branch_copy.save()
    resolved = {item.slug: item for item in effective_resources(agent)}
    assert (
        len(
            [
                item
                for item in effective_resources(agent)
                if item.slug == "wifi-password"
            ]
        )
        == 1
    )
    assert resolved["wifi-password"].body == "Branch override."


@pytest.mark.django_db
def test_inactive_and_out_of_window_resources_hidden(seeded_offices):
    from datetime import timedelta

    from django.utils import timezone

    agent = completed_user(email="agent@example.com", office=office("fairfax-va"))
    today = timezone.localdate()

    inactive = make_resource(office("fairfax-va"), "inactive-one")
    inactive.is_active = False
    inactive.save()

    future = make_resource(
        office("fairfax-va"), "future-one", starts_at=today + timedelta(days=1)
    )
    future.save()

    expired = make_resource(
        office("fairfax-va"), "expired-one", ends_at=today - timedelta(days=1)
    )
    expired.save()

    current = make_resource(office("fairfax-va"), "current-one")
    current.save()

    assert slug_set(agent) == {"current-one"}


@pytest.mark.django_db
def test_user_without_office_sees_nothing(seeded_offices):
    user = completed_user(email="nooffice@example.com", office=None)
    make_resource(office("onest-head-office"), "company-handbook").save()
    assert slug_set(user) == set()
    payload = office_resources_page_payload(user, filters=ResourceFilters())
    assert payload["groups"] == []
    assert payload["empty"] == {
        "title": "No office assigned",
        "description": (
            "Your profile does not have a primary office yet. "
            "Update your profile or contact your branch administrator."
        ),
        "kind": "no-office",
    }


@pytest.mark.django_db
def test_search_filters_within_scope_only(seeded_offices):
    agent = completed_user(email="agent@example.com", office=office("fairfax-va"))
    make_resource(
        office("fairfax-va"),
        "printer-guide",
        category="printer_wifi",
        title="Printer guide",
    ).save()
    make_resource(
        office("fairfax-va"),
        "shipping-guide",
        category="shipping",
        title="Shipping guide",
    ).save()

    from apps.user.services.office_resources import apply_resource_filters

    scoped = effective_resources(agent)
    hits = apply_resource_filters(scoped, ResourceFilters(q="printer"))
    assert [item.slug for item in hits] == ["printer-guide"]
    by_category = apply_resource_filters(scoped, ResourceFilters(category="shipping"))
    assert [item.slug for item in by_category] == ["shipping-guide"]
    misses = apply_resource_filters(scoped, ResourceFilters(q="zebra"))
    assert misses == []


@pytest.mark.django_db
def test_link_resources_require_https(seeded_offices):
    resource = make_resource(
        office("fairfax-va"), "vendor-site", resource_type="link", body=""
    )
    resource.url = "http://insecure.example.com"
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        resource.full_clean()
    resource.url = "https://secure.example.com"
    resource.full_clean()


@pytest.mark.django_db
def test_resource_type_specific_validation(seeded_offices):
    from django.core.exceptions import ValidationError

    link_without_url = make_resource(
        office("fairfax-va"), "broken-link", resource_type="link", body=""
    )
    with pytest.raises(ValidationError):
        link_without_url.full_clean()

    content_without_body = make_resource(office("fairfax-va"), "empty-content", body="")
    with pytest.raises(ValidationError):
        content_without_body.full_clean()


@pytest.mark.django_db
def test_page_and_download_flow(client, settings, tmp_path, seeded_offices):
    settings.MEDIA_ROOT = str(tmp_path)
    agent = completed_user(email="agent@example.com", office=office("fairfax-va"))
    resource = make_resource(
        office("fairfax-va"),
        "local-forms-packet",
        category="local_forms",
        resource_type="file",
        body="",
    )
    resource.file.save("packet.pdf", ContentFile(b"%PDF-1.4 test"), save=True)

    client.force_login(agent)
    response = client.get(reverse("office_resources"), HTTP_X_INERTIA="true")
    assert response.status_code == 200
    page = json.loads(response.content)["props"]
    items = [item for group in page["groups"] for item in group["items"]]
    packet = next(item for item in items if item["slug"] == "local-forms-packet")
    assert packet["resourceType"] == "file"
    assert packet["fileName"] == "packet.pdf"
    download_url = packet["downloadUrl"]
    assert download_url.endswith("/office-resources/local-forms-packet/download")

    file_response = client.get(download_url)
    assert file_response.status_code == 200
    assert b"".join(file_response.streaming_content) == b"%PDF-1.4 test"
    assert AuditEvent.objects.filter(action="office_resource.downloaded").exists()


@pytest.mark.django_db
def test_download_denied_for_other_office(client, settings, tmp_path, seeded_offices):
    settings.MEDIA_ROOT = str(tmp_path)
    outsider = completed_user(
        email="outsider@example.com", office=office("charlottesville-va")
    )
    resource = make_resource(
        office("fairfax-va"), "secret-file", resource_type="file", body=""
    )
    resource.file.save("secret.txt", ContentFile(b"secret"), save=True)

    client.force_login(outsider)
    response = client.get(reverse("office_resources_download", args=[resource.slug]))
    assert response.status_code == 404
    assert not AuditEvent.objects.filter(action="office_resource.downloaded").exists()


@pytest.mark.django_db
def test_download_requires_file_type(seeded_offices):
    """A content resource's slug cannot be used against the download route."""
    actor = completed_user(email="agent@example.com", office=office("fairfax-va"))
    make_resource(office("fairfax-va"), "just-content").save()
    client = _client_for(actor)
    response = client.get(reverse("office_resources_download", args=["just-content"]))
    assert response.status_code == 404


def _client_for(user):
    from django.test import Client

    client = Client()
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_office_resources_page_query_count_bounded(client, seeded_offices):
    agent = completed_user(email="agent@example.com", office=office("fairfax-va"))
    head = office("onest-head-office")
    region = office("region-mid-atlantic")
    branch = office("fairfax-va")
    for node in (head, region, branch):
        for index in range(5):
            make_resource(node, f"{node.slug}-res-{index}", title=f"Res {index}").save()
    client.force_login(agent)
    from django.db import connection

    with CaptureQueriesContext(connection) as context:
        client.get(reverse("office_resources"), HTTP_X_INERTIA="true")
    assert len(context) < 60
