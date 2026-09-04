"""TrainingContent.clean and publish-time validation debt."""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from apps.training.models import TrainingContent
from apps.training.services import validation_debt
from apps.training.tests.factories import category, office, publish_content


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def _draft(**overrides) -> TrainingContent:
    defaults = {
        "owner_office": office("onest-head-office"),
        "slug": "draft-item",
        "title": "Draft item",
        "body": "Safe body",
        "content_type": "article",
        "category": category(),
        "status": TrainingContent.Status.DRAFT,
    }
    defaults.update(overrides)
    return TrainingContent(**defaults)


def test_rejects_non_https_external_url(seeded):
    row = _draft(external_url="http://insecure.example/resource")
    with pytest.raises(ValidationError) as caught:
        row.full_clean()
    assert "external_url" in caught.value.message_dict


def test_rejects_unsafe_body_links(seeded):
    row = _draft(body="See [x](javascript:alert(1)) and [y](http://plain.test)")
    with pytest.raises(ValidationError) as caught:
        row.full_clean()
    assert "body" in caught.value.message_dict


def test_rejects_unknown_tool_code(seeded):
    row = _draft(tool_code="not-a-real-tool")
    with pytest.raises(ValidationError) as caught:
        row.full_clean()
    assert "tool_code" in caught.value.message_dict


def test_validation_debt_for_video_without_media(seeded):
    row = publish_content(
        slug="bare-video",
        title="Bare video",
        owner_office=office("onest-head-office"),
        content_type="video",
        body="",
    )
    fields = {field for field, _msg in validation_debt(row)}
    assert "embed" in fields


def test_validation_debt_for_tool_onboarding_without_tool(seeded):
    row = publish_content(
        slug="tool-gap",
        title="Tool gap",
        owner_office=office("onest-head-office"),
        content_type="tool_onboarding",
        tool_code="",
    )
    fields = {field for field, _msg in validation_debt(row)}
    assert "tool_code" in fields


def test_validation_debt_for_missing_category(seeded):
    row = publish_content(
        slug="no-category",
        title="No category",
        owner_office=office("onest-head-office"),
    )
    row.category = None
    fields = {field for field, _msg in validation_debt(row)}
    assert "category" in fields


def test_validation_debt_for_unconfigured_quiz(seeded):
    row = publish_content(
        slug="bare-quiz",
        title="Bare quiz",
        owner_office=office("onest-head-office"),
        content_type="quiz",
    )
    fields = {field for field, _msg in validation_debt(row)}
    assert "quiz" in fields


def test_validation_debt_for_unconfigured_live_session(seeded):
    row = publish_content(
        slug="bare-session",
        title="Bare session",
        owner_office=office("onest-head-office"),
        content_type="live_session",
    )
    fields = {field for field, _msg in validation_debt(row)}
    assert "session" in fields


def test_published_clean_surfaces_validation_debt(seeded):
    row = publish_content(
        slug="publish-debt",
        title="Publish debt",
        owner_office=office("onest-head-office"),
        content_type="tool_onboarding",
        tool_code="",
    )
    with pytest.raises(ValidationError) as caught:
        row.full_clean()
    assert "tool_code" in caught.value.message_dict
