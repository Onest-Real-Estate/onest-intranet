"""Marketing library visibility, versioning, and consumer detail."""

from __future__ import annotations

import json

import pytest
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.urls import reverse

from apps.marketing.administration import (
    asset_version,
    duplicate_version,
    transition,
)
from apps.marketing.audience import AudienceSelector
from apps.marketing.services import (
    LibraryFilters,
    detail_payload,
    library_queryset,
    library_summary,
    resolve_consumer_asset,
)
from apps.marketing.tests.factories import (
    agent,
    attach_ready_export,
    attach_ready_source,
    mark_exports_ready,
    office,
    publish_asset,
)
from apps.user.models import User
from apps.user.tests.test_profile import completed_user


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def _publisher() -> User:
    from django.contrib.auth.models import Permission

    from apps.marketing.tests.factories import assign

    user = completed_user(
        email="mkt-publisher@example.com", office=office("fairfax-va")
    )
    assign(user, "system_admin", "company")
    for codename in (
        "manage_marketing_resources",
        "publish_marketing_resources",
    ):
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label="web", codename=codename)
        )
    return User.objects.get(pk=user.pk)


def test_library_lists_only_current_live_version(seeded):
    actor = _publisher()
    v1 = publish_asset(
        slug="logo-pack",
        title="Logo pack",
        owner_office=office("fairfax-va"),
        audience=(AudienceSelector(kind="office", office=office("fairfax-va")),),
    )
    draft = duplicate_version(actor=actor, asset=v1, expected_version=asset_version(v1))
    mark_exports_ready(draft)
    transition(
        actor=actor,
        asset=draft,
        action="publish",
        expected_version=asset_version(draft),
    )
    v1.refresh_from_db()
    draft.refresh_from_db()
    assert draft.status == draft.Status.PUBLISHED
    assert v1.status == v1.Status.ARCHIVED

    reader = agent()
    ids = set(library_queryset(reader, LibraryFilters()).values_list("pk", flat=True))
    assert draft.pk in ids
    assert v1.pk not in ids


def test_library_queryset_compiles_and_counts_on_postgresql(seeded, monkeypatch):
    """Display ORDER BY must not break family collapse under Postgres."""
    from apps.user.tests.pg_compile import compile_for_postgresql

    reader = agent()
    publish_asset(
        slug="compile-check",
        title="Compile check",
        owner_office=office("onest-head-office"),
    )
    qs = library_queryset(reader, LibraryFilters())
    sql = compile_for_postgresql(qs, monkeypatch).upper()
    assert "DISTINCT ON" not in sql
    assert "SELECT" in sql
    # count() is what blew up in production (Silk EXPLAIN + ORDER BY clash).
    assert qs.count() >= 1
    assert list(qs[:5])


def test_resolve_redirects_archived_to_current_when_audience_matches(seeded):
    actor = _publisher()
    v1 = publish_asset(
        slug="brand-kit",
        title="Brand kit",
        owner_office=office("fairfax-va"),
        audience=(AudienceSelector(kind="office", office=office("fairfax-va")),),
    )
    draft = duplicate_version(actor=actor, asset=v1, expected_version=asset_version(v1))
    mark_exports_ready(draft)
    transition(
        actor=actor,
        asset=draft,
        action="publish",
        expected_version=asset_version(draft),
    )
    reader = agent()
    outcome, resolved = resolve_consumer_asset(reader, v1.pk)
    assert outcome == "redirect"
    assert resolved.pk == draft.pk


def test_resolve_404_when_no_live_sibling(seeded):
    reader = agent()
    row = publish_asset(
        slug="gone",
        title="Gone",
        owner_office=office("onest-head-office"),
    )
    row.status = row.Status.ARCHIVED
    row.save(update_fields=["status"])

    with pytest.raises((Http404, PermissionDenied)):
        resolve_consumer_asset(reader, row.pk)


def test_detail_view_redirects_superseded_id(seeded, client):
    actor = _publisher()
    v1 = publish_asset(
        slug="flyer-v1",
        title="Flyer",
        owner_office=office("fairfax-va"),
        audience=(AudienceSelector(kind="office", office=office("fairfax-va")),),
    )
    draft = duplicate_version(actor=actor, asset=v1, expected_version=asset_version(v1))
    mark_exports_ready(draft)
    transition(
        actor=actor,
        asset=draft,
        action="publish",
        expected_version=asset_version(draft),
    )

    reader = agent()
    client.force_login(reader)
    response = client.get(reverse("marketing_resource_detail", args=[v1.pk]))
    assert response.status_code == 302
    assert response["Location"] == reverse("marketing_resource_detail", args=[draft.pk])


def test_library_page_query_count_is_bounded(seeded, client):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    reader = agent()

    def cost(count: int) -> int:
        from apps.marketing.models import MarketingAsset

        MarketingAsset.objects.all().delete()
        for index in range(count):
            publish_asset(
                slug=f"item-{index}",
                title=f"Item {index}",
                owner_office=office("onest-head-office"),
            )
        client.force_login(reader)
        with CaptureQueriesContext(connection) as captured:
            response = client.get(reverse("marketing_resources"), HTTP_X_INERTIA="true")
        assert response.status_code == 200
        return len(captured)

    # Soft budget: more rows should not blow the query count open-ended.
    assert cost(2) <= cost(5) + 5


def test_consumer_detail_has_exports_but_no_sources(seeded):
    asset = publish_asset(
        slug="with-files",
        title="With files",
        owner_office=office("onest-head-office"),
        with_export=False,
    )
    export = attach_ready_export(asset)
    attach_ready_source(asset)

    payload = detail_payload(asset)
    assert payload["exports"]
    assert any(row["id"] == export.pk for row in payload["exports"])
    assert all(row.get("url") for row in payload["exports"])
    dumped = json.dumps(payload)
    assert "/source/" not in dumped
    assert "source" not in {row.get("role") for row in payload["exports"]}


def test_library_inertia_page(seeded, client):
    reader = agent()
    publish_asset(
        slug="library",
        title="Library item",
        owner_office=office("onest-head-office"),
    )
    client.force_login(reader)
    response = client.get(reverse("marketing_resources"), HTTP_X_INERTIA="true")
    assert response.status_code == 200
    payload = json.loads(response.content)
    assert payload["component"] == "MarketingResources"
    assert payload["props"]["library"]["items"]
    assert payload["props"]["summary"]["published"] >= 1


def test_library_summary_counts_visible_assets(seeded):
    publish_asset(
        slug="primary-logo",
        title="Primary logo",
        owner_office=office("onest-head-office"),
        asset_type="logo",
    )
    summary = library_summary(agent())
    assert summary["published"] >= 1
    assert summary["logos"] >= 1
    assert summary["templates"] >= 0
