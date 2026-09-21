"""Operational onboarding measures: correct, scoped, bounded, and anonymous."""

from __future__ import annotations

import json
import logging
from datetime import timedelta

import pytest
from django.core.management import CommandError, call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.onboarding_tools.models import AgentToolStatus, ToolState
from apps.training.models import TrainingProgress
from apps.user.models import User, UserOnboardingCase
from apps.user.services.onboarding_metrics import journey_health
from apps.user.tests.test_onboarding_administration import (
    account,
    branch_manager,
    confirm_required_setup,
    office,
)
from apps.user.tests.test_onboarding_next_steps import guide, tool
from apps.web.reporting.registry import REPORT_BY_KEY, run_report
from apps.web.tests.test_reporting import grant

EMAILS = ("waiting@example.com", "released@example.com", "failed@example.com")


def released(email: str, *, hours_to_setup: int) -> User:
    user = account(email, "fairfax-va")
    joined = timezone.now() - timedelta(days=2)
    User.objects.filter(pk=user.pk).update(date_joined=joined, last_login=joined)
    case = confirm_required_setup(user)
    case.required_setup_completed_at = joined + timedelta(hours=hours_to_setup)
    case.save(update_fields=["required_setup_completed_at"])
    return User.objects.get(pk=user.pk)


@pytest.fixture
def journeys():
    waiting = account(EMAILS[0], "fairfax-va", complete=False)
    ready = released(EMAILS[1], hours_to_setup=2)
    failed = released(EMAILS[2], hours_to_setup=4)

    ready_case = UserOnboardingCase.objects.get(user=ready)
    ready_case.office_handoff_state = UserOnboardingCase.OfficeHandoffState.NOTIFIED
    ready_case.save(update_fields=["office_handoff_state"])
    failed_case = UserOnboardingCase.objects.get(user=failed)
    failed_case.office_handoff_state = (
        UserOnboardingCase.OfficeHandoffState.NOTIFICATION_FAILED
    )
    failed_case.office_handoff_office = failed.office
    failed_case.office_handoff_onboarding_version = failed.onboarding_version
    failed_case.save(
        update_fields=[
            "office_handoff_state",
            "office_handoff_office",
            "office_handoff_onboarding_version",
        ]
    )

    start = ready_case.required_setup_completed_at
    assert start is not None
    AgentToolStatus.objects.create(
        agent=ready,
        tool=tool("lofty"),
        state=ToolState.READY,
        invitation_sent_at=start + timedelta(hours=6),
        ready_at=start + timedelta(hours=30),
    )
    content = guide(slug="lofty-activation", tool_code="lofty")
    TrainingProgress.objects.create(
        user=ready,
        content=content,
        status=TrainingProgress.Status.COMPLETED,
        started_at=start + timedelta(hours=7),
        completed_at=start + timedelta(hours=8),
    )
    return waiting, ready, failed


def population(*users: User):
    return User.objects.filter(pk__in=[user.pk for user in users])


@pytest.mark.django_db
def test_health_counts_the_funnel_handoff_tools_and_guides(journeys):
    health = journey_health(population(*journeys), now=timezone.now())

    assert health.population == 3
    assert health.journeys_started == 2
    assert health.required_setup_completed == 2
    assert health.median_hours_to_required_setup == 3.0
    assert health.current_steps["profile"] == 1
    assert health.current_steps["activation"] == 2
    assert sum(health.current_steps.values()) == health.population
    assert health.handoff_states["notified"] == 1
    assert health.handoff_states["notification_failed"] == 1
    assert health.blockers["office_handoff_failed"] == 1
    assert health.agents_blocked_by_source == 1
    lofty = next(item for item in health.tools if item.tool == "lofty")
    assert (lofty.invitations_sent, lofty.ready) == (1, 1)
    assert lofty.median_hours_to_invitation == 6.0
    assert lofty.median_hours_to_ready == 30.0
    assert (lofty.guides_opened, lofty.guides_completed) == (1, 1)


@pytest.mark.django_db
def test_legacy_backfilled_users_do_not_distort_the_setup_median(journeys):
    legacy = account("legacy@example.com", "fairfax-va")
    case = confirm_required_setup(legacy)
    # This is the shape produced by migrations 0003 and 0031: an existing
    # account was marked complete without a real completion timestamp, and its
    # compatibility checkpoint was backfilled from ``date_joined``.
    User.objects.filter(pk=legacy.pk).update(
        profile_completed_at=None,
    )
    case.required_setup_completed_at = legacy.date_joined
    case.save(update_fields=["required_setup_completed_at"])

    health = journey_health(population(*journeys, legacy), now=timezone.now())
    assert health.median_hours_to_required_setup == 3.0


@pytest.mark.django_db
def test_query_cost_does_not_grow_with_the_population(journeys):
    now = timezone.now()
    with CaptureQueriesContext(connection) as small:
        journey_health(population(*journeys), now=now)
    more = [
        released(f"more-{index}@example.com", hours_to_setup=1) for index in range(4)
    ]
    with CaptureQueriesContext(connection) as large:
        journey_health(population(*journeys, *more), now=now)
    assert len(large) == len(small)


@pytest.mark.django_db
def test_report_is_scoped_reconciles_and_names_nobody(journeys):
    outsider = account("outsider@example.com", "charlottesville-va", complete=False)
    manager = branch_manager("fairfax-va", "manager@example.com")
    grant(manager, "web.view_reports")

    _context, result, columns = run_report(
        manager, REPORT_BY_KEY["onboardingJourneyHealth"]
    )

    steps = {
        row["measure"]: row["value"]
        for row in result.rows
        if row["group"] == "current_step"
    }
    # Reconciliation: the step breakdown sums to the scoped population.
    assert sum(steps.values()) == result.aggregates["total"]
    assert sum(point.value for point in result.series) == result.aggregates["total"]
    assert {column.key for column in columns} == {"group", "measure", "value"}
    rendered = json.dumps(result.rows, default=str)
    for email in (*EMAILS, outsider.email, manager.email):
        assert email not in rendered
    fairfax_only = journey_health(
        User.objects.filter(office=office("fairfax-va")), now=timezone.now()
    )
    assert result.aggregates["total"] == fairfax_only.population


@pytest.mark.django_db
def test_command_prints_aggregates_only(journeys, capsys):
    call_command("onboarding_health", "--office", "fairfax-va")
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["required_setup_completed"] >= 2
    assert payload["tools"]
    for email in EMAILS:
        assert email not in output

    with pytest.raises(CommandError):
        call_command("onboarding_health", "--office", "no-such-office")


@pytest.mark.django_db
def test_rejected_requests_log_a_stable_code_and_no_request_data(client, caplog):
    user = account("stale@example.com", "fairfax-va", complete=False)
    client.force_login(user)

    with caplog.at_level(logging.WARNING, logger="apps.user.services"):
        response = client.post(
            reverse("onboarding_profile_finalize"),
            json.dumps({"confirm_review": True, "expected_onboarding_version": 99}),
            content_type="application/json",
            HTTP_X_INERTIA="true",
        )

    assert response.status_code == 409
    codes = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("onboarding_error")
    ]
    assert codes == ["onboarding_error code=stale_onboarding_version"]
    assert "stale@example.com" not in caplog.text
