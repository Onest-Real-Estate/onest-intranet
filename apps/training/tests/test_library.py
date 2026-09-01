"""Training library visibility and filters."""

from __future__ import annotations

import json

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.training.audience import (
    AudienceSelector,
    visible_training_content,
)
from apps.training.models import TrainingAudience, TrainingContent, TrainingProgress
from apps.training.services import (
    TrainingFilters,
    apply_filters,
    build_library,
    order_for_library,
)
from apps.training.taxonomy import LIBRARY_VIEW_RECOMMENDED, LIBRARY_VIEW_REQUIRED
from apps.training.tests.factories import (
    agent,
    category,
    office,
    publish_content,
    video_with_transcription,
)


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def test_visible_content_respects_audience(seeded):
    reader = agent()
    other = agent(email="other@example.com", slug="harrisburg")
    visible = publish_content(
        slug="visible",
        title="Visible",
        owner_office=office("onest-head-office"),
        audience=(AudienceSelector(kind=TrainingAudience.Kind.COMPANY),),
    )
    hidden = publish_content(
        slug="hidden",
        title="Hidden",
        owner_office=office("onest-head-office"),
        audience=(
            AudienceSelector(
                kind=TrainingAudience.Kind.USER,
                user=other,
            ),
        ),
    )
    ids = set(visible_training_content(reader).values_list("pk", flat=True))
    assert visible.pk in ids
    assert hidden.pk not in ids


def test_draft_and_expired_content_hidden(seeded):
    reader = agent()
    draft = TrainingContent.objects.create(
        owner_office=office("onest-head-office"),
        slug="draft",
        title="Draft",
        content_type="article",
        category=category(),
        status=TrainingContent.Status.DRAFT,
    )
    expired = publish_content(
        slug="expired",
        title="Expired",
        owner_office=office("onest-head-office"),
    )
    expired.expires_at = timezone.now() - timezone.timedelta(days=1)
    expired.save(update_fields=["expires_at"])
    ids = set(visible_training_content(reader).values_list("pk", flat=True))
    assert draft.pk not in ids
    assert expired.pk not in ids


def test_completion_filter_uses_progress_stub(seeded):
    reader = agent()
    item = publish_content(
        slug="progress",
        title="Progress",
        owner_office=office("onest-head-office"),
    )
    TrainingProgress.objects.create(
        user=reader,
        content=item,
        status=TrainingProgress.Status.COMPLETED,
        completed_at=timezone.now(),
    )
    filters = TrainingFilters.from_params(
        {"completion": "completed"},
        known_category_codes={"general"},
    )
    rows = list(apply_filters(visible_training_content(reader), filters, user=reader))
    assert rows == [item]


def test_transcription_search_narrows_library(seeded):
    reader = agent()
    match = video_with_transcription(
        slug="form-21",
        title="Form 21 walkthrough",
        owner_office=office("onest-head-office"),
        segments=[{"startMs": 1000, "endMs": 4000, "text": "how to fill out Form 21"}],
    )
    other = publish_content(
        slug="other",
        title="Other topic",
        owner_office=office("onest-head-office"),
        body="unrelated",
    )
    library = build_library(reader, params={"q": "Form 21"}, page=1)
    ids = {row["id"] for row in library["items"]}
    assert match.pk in ids
    assert other.pk not in ids


def test_detail_denies_out_of_audience(seeded, client):
    reader = agent()
    hidden = publish_content(
        slug="private",
        title="Private",
        owner_office=office("onest-head-office"),
        audience=(
            AudienceSelector(
                kind=TrainingAudience.Kind.ROLE,
                role="system_admin",
            ),
        ),
    )
    client.force_login(reader)
    response = client.get(reverse("training_detail", args=[hidden.pk]))
    assert response.status_code == 403


def test_library_inertia_page(seeded, client):
    reader = agent()
    publish_content(
        slug="library",
        title="Library item",
        owner_office=office("onest-head-office"),
        is_required=True,
    )
    client.force_login(reader)
    response = client.get(reverse("training_learning"), HTTP_X_INERTIA="true")
    assert response.status_code == 200
    payload = json.loads(response.content)
    assert payload["component"] == "TrainingLearning"
    assert payload["props"]["library"]["items"]


def test_required_view_filters_to_required_only(seeded):
    reader = agent()
    required = publish_content(
        slug="required",
        title="Required",
        owner_office=office("onest-head-office"),
        is_required=True,
    )
    optional = publish_content(
        slug="optional",
        title="Optional",
        owner_office=office("onest-head-office"),
        is_required=False,
    )
    filters = TrainingFilters.from_params(
        {"view": LIBRARY_VIEW_REQUIRED},
        known_category_codes={"general"},
    )
    rows = list(apply_filters(visible_training_content(reader), filters, user=reader))
    assert rows == [required]
    assert optional not in rows


def test_recommended_view_filters_to_optional_only(seeded):
    reader = agent()
    required = publish_content(
        slug="required",
        title="Required",
        owner_office=office("onest-head-office"),
        is_required=True,
    )
    optional = publish_content(
        slug="optional",
        title="Optional",
        owner_office=office("onest-head-office"),
        is_required=False,
    )
    filters = TrainingFilters.from_params(
        {"view": LIBRARY_VIEW_RECOMMENDED},
        known_category_codes={"general"},
    )
    rows = list(apply_filters(visible_training_content(reader), filters, user=reader))
    assert rows == [optional]
    assert required not in rows


def test_required_items_sort_before_optional(seeded):
    reader = agent()
    optional = publish_content(
        slug="optional",
        title="Optional",
        owner_office=office("onest-head-office"),
        is_required=False,
    )
    required = publish_content(
        slug="required",
        title="Required",
        owner_office=office("onest-head-office"),
        is_required=True,
    )
    rows = list(order_for_library(visible_training_content(reader)))
    assert [row.pk for row in rows].index(required.pk) < [row.pk for row in rows].index(
        optional.pk
    )


def test_library_page_query_count_is_bounded(seeded, client):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    reader = agent()

    def cost(count: int) -> int:
        TrainingContent.objects.all().delete()
        for index in range(count):
            publish_content(
                slug=f"item-{index}",
                title=f"Item {index}",
                owner_office=office("onest-head-office"),
            )
        client.force_login(reader)
        with CaptureQueriesContext(connection) as captured:
            response = client.get(reverse("training_learning"), HTTP_X_INERTIA="true")
        assert response.status_code == 200
        return len(captured)

    assert cost(2) == cost(5)
