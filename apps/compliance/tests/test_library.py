"""Compliance library visibility, versioning, and publish immutability."""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.http import Http404

from apps.compliance.administration import (
    TransitionRefused,
    policy_version_token,
    transition,
    update_draft,
)
from apps.compliance.audience import AudienceSelector
from apps.compliance.services import (
    LibraryFilters,
    library_queryset,
    library_summary,
    resolve_consumer_policy,
)
from apps.compliance.tests.factories import (
    agent,
    office,
    publish_policy,
    publisher,
)


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def test_library_lists_only_current_live_version(seeded):
    actor = publisher()
    v1 = publish_policy(
        title="Logo pack",
        owner_office=office("fairfax-va"),
        audience=(AudienceSelector(kind="office", office=office("fairfax-va")),),
        actor=actor,
    )
    from apps.compliance.administration import duplicate_version

    draft = duplicate_version(
        actor=actor, version=v1, expected_version=policy_version_token(v1)
    )
    for action in ("submit", "approve", "publish"):
        transition(
            actor=actor,
            version=draft,
            action=action,
            expected_version=policy_version_token(draft),
        )
        draft.refresh_from_db()
    v1.refresh_from_db()
    assert draft.status == draft.Status.PUBLISHED
    assert v1.status == v1.Status.SUPERSEDED

    reader = agent()
    ids = set(library_queryset(reader, LibraryFilters()).values_list("pk", flat=True))
    assert draft.pk in ids
    assert v1.pk not in ids


def test_jurisdiction_filters_by_license_or_office_state(seeded):
    publish_policy(
        title="VA only",
        owner_office=office("onest-head-office"),
        jurisdiction_state_codes=["VA"],
    )
    publish_policy(
        title="Nationwide",
        owner_office=office("onest-head-office"),
        jurisdiction_state_codes=[],
    )
    reader = agent()
    reader.license_state = "VA"
    reader.save(update_fields=["license_state"])
    titles = set(
        library_queryset(reader, LibraryFilters()).values_list("title", flat=True)
    )
    assert "VA only" in titles
    assert "Nationwide" in titles

    outsider = agent(email="md-agent@example.com")
    outsider.license_state = "MD"
    if outsider.office:
        outsider.office.state = "MD"
        outsider.office.save(update_fields=["state"])
    outsider.save(update_fields=["license_state"])
    titles = set(
        library_queryset(outsider, LibraryFilters()).values_list("title", flat=True)
    )
    assert "VA only" not in titles
    assert "Nationwide" in titles


def test_resolve_redirects_superseded_to_current(seeded):
    actor = publisher()
    v1 = publish_policy(
        title="Brand kit",
        owner_office=office("fairfax-va"),
        audience=(AudienceSelector(kind="office", office=office("fairfax-va")),),
        actor=actor,
    )
    from apps.compliance.administration import duplicate_version

    draft = duplicate_version(
        actor=actor, version=v1, expected_version=policy_version_token(v1)
    )
    for action in ("submit", "approve", "publish"):
        transition(
            actor=actor,
            version=draft,
            action=action,
            expected_version=policy_version_token(draft),
        )
        draft.refresh_from_db()
    reader = agent()
    outcome, resolved = resolve_consumer_policy(reader, v1.pk)
    assert outcome == "redirect"
    assert resolved.pk == draft.pk


def test_resolve_404_when_out_of_audience(seeded):
    row = publish_policy(
        title="Office only",
        owner_office=office("fairfax-va"),
        audience=(
            AudienceSelector(kind="office", office=office("charlottesville-va")),
        ),
    )
    reader = agent()
    with pytest.raises(Http404):
        resolve_consumer_policy(reader, row.pk)


def test_published_policy_cannot_be_edited(seeded):
    actor = publisher()
    row = publish_policy(title="Immutable", actor=actor)
    with pytest.raises((TransitionRefused, ValidationError)):
        update_draft(
            actor=actor,
            version=row,
            cleaned={"title": "Changed", "summary": row.summary, "body": row.body},
            selectors=[AudienceSelector(kind="company")],
            expected_version=policy_version_token(row),
        )


def test_library_summary_counts_visible_policies(seeded):
    publish_policy(title="Handbook", is_mandatory=True)
    reader = agent()
    summary = library_summary(reader)
    assert summary["published"] >= 1
    assert summary["outstanding"] >= 1
    assert summary["overdue"] >= 0
