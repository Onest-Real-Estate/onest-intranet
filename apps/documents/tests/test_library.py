"""Documents library visibility, versioning, and consumer detail."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.http import Http404
from django.urls import reverse
from django.utils import timezone

from apps.documents.audience import AudienceSelector
from apps.documents.models import DocumentAudience, DocumentVersion
from apps.documents.services import (
    LibraryFilters,
    library_queryset,
    resolve_consumer_document,
)
from apps.documents.tests.factories import (
    agent,
    office,
    publish_document,
)
from apps.user.tests.test_profile import completed_user


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def test_library_lists_only_current_live_version(seeded):
    v1 = publish_document(
        key="exclusive-buyer",
        name="Buyer v1",
        owner_office=office("onest-head-office"),
        version_number=1,
    )
    v2 = publish_document(
        key="exclusive-buyer",
        name="Buyer v2",
        owner_office=office("onest-head-office"),
        version_number=2,
    )
    v1.status = DocumentVersion.Status.SUPERSEDED
    v1.save(update_fields=["status"])

    reader = agent()
    ids = set(library_queryset(reader, LibraryFilters()).values_list("pk", flat=True))
    assert v2.pk in ids
    assert v1.pk not in ids


def test_jurisdiction_filters_by_license_or_office_state(seeded):
    publish_document(
        key="va-only",
        name="VA only",
        owner_office=office("onest-head-office"),
        jurisdiction_state_codes=["VA"],
    )
    publish_document(
        key="nationwide",
        name="Nationwide",
        owner_office=office("onest-head-office"),
        jurisdiction_state_codes=[],
    )
    reader = agent()
    reader.license_state = "VA"
    reader.save(update_fields=["license_state"])
    names = set(
        library_queryset(reader, LibraryFilters()).values_list("name", flat=True)
    )
    assert "VA only" in names
    assert "Nationwide" in names

    md_reader = agent(email="md-reader@example.com")
    md_reader.license_state = "MD"
    if md_reader.office:
        md_reader.office.state = "MD"
        md_reader.office.save(update_fields=["state"])
    md_reader.save(update_fields=["license_state"])
    md_names = set(
        library_queryset(md_reader, LibraryFilters()).values_list("name", flat=True)
    )
    assert "VA only" not in md_names
    assert "Nationwide" in md_names


def test_office_audience_does_not_leak_to_sibling_branch(seeded):
    publish_document(
        key="fairfax-form",
        name="Fairfax only",
        owner_office=office("fairfax-va"),
        audience=(
            AudienceSelector(
                kind=DocumentAudience.Kind.OFFICE, office=office("fairfax-va")
            ),
        ),
    )
    other = completed_user(
        email="other-branch@example.com",
        office=office("harrisburg"),
    )
    ids = list(library_queryset(other, LibraryFilters()).values_list("name", flat=True))
    assert "Fairfax only" not in ids


def test_role_filter_narrows_and_cannot_widen(seeded):
    publish_document(
        key="company-form",
        name="Everyone form",
        owner_office=office("onest-head-office"),
    )
    publish_document(
        key="realtor-form",
        name="Realtor form",
        owner_office=office("onest-head-office"),
        audience=(AudienceSelector(kind=DocumentAudience.Kind.ROLE, role="realtor"),),
    )
    reader = agent()
    from apps.documents.tests.factories import assign

    assign(reader, "realtor", "office", office("fairfax-va"))
    all_names = set(
        library_queryset(reader, LibraryFilters()).values_list("name", flat=True)
    )
    assert "Everyone form" in all_names
    assert "Realtor form" in all_names

    narrowed = set(
        library_queryset(reader, LibraryFilters(role="realtor")).values_list(
            "name", flat=True
        )
    )
    assert narrowed == {"Realtor form"}


def test_effective_and_expiry_boundaries_are_deterministic(seeded):
    now = timezone.now()
    live = publish_document(
        key="windowed",
        name="Windowed",
        owner_office=office("onest-head-office"),
        effective_at=now,
        expires_at=now + timedelta(days=1),
    )
    reader = agent()
    assert live.pk in library_queryset(reader, LibraryFilters(), at=now).values_list(
        "pk", flat=True
    )
    assert live.pk not in library_queryset(
        reader, LibraryFilters(), at=now + timedelta(days=1)
    ).values_list("pk", flat=True)


def test_overlapping_windows_pick_highest_version_then_pk(seeded):
    now = timezone.now()
    older = publish_document(
        key="overlap",
        name="Older",
        owner_office=office("onest-head-office"),
        version_number=1,
        effective_at=now - timedelta(days=2),
        expires_at=now + timedelta(days=2),
    )
    newer = publish_document(
        key="overlap",
        name="Newer",
        owner_office=office("onest-head-office"),
        version_number=2,
        effective_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=3),
    )
    reader = agent()
    ids = list(
        library_queryset(reader, LibraryFilters(), at=now).values_list("pk", flat=True)
    )
    assert newer.pk in ids
    assert older.pk not in ids


def test_resolve_redirects_superseded_to_current(seeded):
    v1 = publish_document(
        key="redirect-me",
        name="Old",
        owner_office=office("onest-head-office"),
        version_number=1,
    )
    v2 = publish_document(
        key="redirect-me",
        name="New",
        owner_office=office("onest-head-office"),
        version_number=2,
    )
    v1.status = DocumentVersion.Status.SUPERSEDED
    v1.save(update_fields=["status"])

    reader = agent()
    outcome, version = resolve_consumer_document(reader, v1.pk)
    assert outcome == "redirect"
    assert version.pk == v2.pk


def test_out_of_scope_and_draft_are_404(seeded):
    draft = publish_document(
        key="draft-form",
        name="Draft",
        owner_office=office("onest-head-office"),
        status=DocumentVersion.Status.DRAFT,
    )
    hidden = publish_document(
        key="hidden-form",
        name="Hidden",
        owner_office=office("fairfax-va"),
        audience=(
            AudienceSelector(
                kind=DocumentAudience.Kind.OFFICE, office=office("fairfax-va")
            ),
        ),
    )
    stranger = completed_user(email="stranger@example.com", office=office("harrisburg"))
    with pytest.raises(Http404):
        resolve_consumer_document(stranger, draft.pk)
    with pytest.raises(Http404):
        resolve_consumer_document(stranger, hidden.pk)


def test_detail_redirects_with_superseded_query(seeded, client):
    v1 = publish_document(
        key="bookmark",
        name="Old bookmark",
        owner_office=office("onest-head-office"),
        version_number=1,
    )
    v2 = publish_document(
        key="bookmark",
        name="Current bookmark",
        owner_office=office("onest-head-office"),
        version_number=2,
    )
    v1.status = DocumentVersion.Status.SUPERSEDED
    v1.save(update_fields=["status"])

    reader = agent()
    client.force_login(reader)
    response = client.get(reverse("document_detail", args=[v1.pk]))
    assert response.status_code == 302
    expected = f"{reverse('document_detail', args=[v2.pk])}?superseded=1"
    assert response["Location"] == expected


def test_library_page_query_count_is_bounded(seeded, client):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    reader = agent()

    def cost(count: int) -> int:
        from apps.documents.models import DocumentFamily, DocumentVersion

        DocumentVersion.objects.all().delete()
        DocumentFamily.objects.all().delete()
        for index in range(count):
            publish_document(
                key=f"item-{index}",
                name=f"Item {index}",
                owner_office=office("onest-head-office"),
            )
        client.force_login(reader)
        with CaptureQueriesContext(connection) as captured:
            response = client.get(reverse("documents_forms"), HTTP_X_INERTIA="true")
        assert response.status_code == 200
        return len(captured)

    assert cost(2) <= cost(5) + 5


def test_library_inertia_page(seeded, client):
    reader = agent()
    publish_document(
        key="library",
        name="Library item",
        owner_office=office("onest-head-office"),
    )
    client.force_login(reader)
    response = client.get(reverse("documents_forms"), HTTP_X_INERTIA="true")
    assert response.status_code == 200
    payload = json.loads(response.content)
    assert payload["component"] == "DocumentsForms"
    assert payload["props"]["library"]["items"]


def test_search_does_not_leak_out_of_scope_titles(seeded):
    from apps.web.search.providers import search_documents

    publish_document(
        key="secret-fairfax",
        name="Secret Fairfax Form",
        owner_office=office("fairfax-va"),
        audience=(
            AudienceSelector(
                kind=DocumentAudience.Kind.OFFICE, office=office("fairfax-va")
            ),
        ),
    )
    stranger = completed_user(
        email="search-stranger@example.com", office=office("harrisburg")
    )
    hits = search_documents(stranger, "Secret Fairfax", limit=10)
    assert hits == []
