"""Onboarding races against real PostgreSQL row locks.

SQLite serializes writers and drops ``FOR UPDATE``, so these tests skip unless
the active connection is PostgreSQL. Run them in the docker stack:
``make dockerexec cmd="uv run pytest apps/user/tests/test_onboarding_concurrency.py"``.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from importlib import import_module

import pytest
from django.apps import apps as django_apps
from django.conf import settings
from django.db import connections
from django.test import Client

from apps.audit.models import AuditEvent, DomainEvent
from apps.onboarding_tools.models import AgentToolStatus, ToolState
from apps.user.models import User, UserOnboardingCase
from apps.user.services.onboarding_operations import (
    StaleOnboardingVersion,
    perform_tool_action,
)
from apps.user.services.onboarding_profile import finalize_profile

# ``serialized_rollback`` restores the migration-seeded catalog and offices
# after each flush, so later tests on the same worker database still see them.
pytestmark = [
    # Skip before database setup: serialized rollback cannot run on SQLite.
    pytest.mark.skipif(
        "postgresql" not in settings.DATABASES["default"]["ENGINE"],
        reason="Onboarding races require PostgreSQL row locks",
    ),
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]


@pytest.fixture
def seeded(settings, tmp_path):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    settings.MEDIA_ROOT = str(tmp_path)
    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()
    # Idempotent: a no-op when serialized rollback already restored the rows.
    import_module("apps.onboarding_tools.migrations.0002_seed_catalog").seed(
        django_apps, None
    )


def race(*calls: Callable[[], object]) -> list[object]:
    """Start every call at once on its own connection; collect result or error."""
    barrier = threading.Barrier(len(calls))
    outcomes: list[object] = [None] * len(calls)

    def run(index: int, call: Callable[[], object]) -> None:
        try:
            barrier.wait()
            outcomes[index] = call()
        except Exception as exc:  # the outcome under test, not swallowed
            outcomes[index] = exc
        finally:
            connections.close_all()

    threads = [
        threading.Thread(target=run, args=(index, call))
        for index, call in enumerate(calls)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not any(thread.is_alive() for thread in threads)
    return outcomes


def ready_to_finalize() -> User:
    from apps.user.tests.test_onboarding_profile import (
        agent,
        fill_sections,
        upload_headshot,
    )

    user = agent(email="race.agent@example.com")
    browser = Client()
    browser.force_login(user)
    upload_headshot(browser)
    fill_sections(browser)
    return User.objects.get(pk=user.pk)


def test_double_finalize_completes_once_and_hands_off_once(seeded):
    user = ready_to_finalize()
    version = user.onboarding_version

    def submit():
        return finalize_profile(
            user=User.objects.get(pk=user.pk),
            confirmed=True,
            expected_onboarding_version=version,
        )

    outcomes = race(submit, submit)

    assert not [item for item in outcomes if isinstance(item, Exception)]
    assert User.objects.get(pk=user.pk).profile_completed is True
    assert DomainEvent.objects.filter(name="user.onboarded").count() == 1
    # Seeded offices have no Branch Admin, so the one handoff is recorded as
    # unavailable; either way there is exactly one.
    assert (
        AuditEvent.objects.filter(
            action__in=(
                "user.onboarding.office_handoff_requested",
                "user.onboarding.office_handoff_unavailable",
            ),
            target_id=str(user.pk),
        ).count()
        == 1
    )
    assert UserOnboardingCase.objects.filter(user=user).count() == 1


def test_two_admins_recording_one_invitation_write_once(seeded):
    from apps.user.tests.test_onboarding_administration import (
        account,
        action_version,
        company_admin,
        confirm_required_setup,
    )

    agent = account("race.target@example.com", "fairfax-va")
    confirm_required_setup(agent)
    first_admin = company_admin("first.admin@example.com")
    second_admin = company_admin("second.admin@example.com")
    version = action_version(agent)

    def record(actor: User) -> Callable[[], object]:
        return lambda: perform_tool_action(
            actor=User.objects.get(pk=actor.pk),
            user=User.objects.get(pk=agent.pk),
            tool="lofty",
            action="mark_invitation_sent",
            reason="",
            expected_version=version,
        )

    outcomes = race(record(first_admin), record(second_admin))

    # One writer wins; the other is told its page is stale, never overwrites.
    errors = [item for item in outcomes if isinstance(item, Exception)]
    assert len(errors) == 1
    assert isinstance(errors[0], StaleOnboardingVersion)
    status = AgentToolStatus.objects.get(agent=agent, tool__slug="lofty")
    assert status.state == ToolState.INVITATION_SENT
    assert getattr(status, "invitation_sent_by_id", None) in {
        first_admin.pk,
        second_admin.pk,
    }
    assert (
        DomainEvent.objects.filter(
            name="onboarding_tool.state_changed", subject=f"user:{agent.pk}"
        ).count()
        == 1
    )


def test_two_admins_initiating_one_contract_create_one(seeded):
    from apps.contract.models import AgentContract
    from apps.user.services.onboarding_operations import initiate_contract
    from apps.user.tests.test_onboarding_administration import (
        account,
        action_version,
        company_admin,
        confirm_required_setup,
    )

    agent = account("race.contract@example.com", "fairfax-va")
    confirm_required_setup(agent)
    admins = [
        company_admin("contract.one@example.com"),
        company_admin("contract.two@example.com"),
    ]
    version = action_version(agent)

    def initiate(actor: User) -> Callable[[], object]:
        return lambda: initiate_contract(
            actor=User.objects.get(pk=actor.pk),
            user=User.objects.get(pk=agent.pk),
            expected_version=version,
        )

    outcomes = race(*(initiate(admin) for admin in admins))

    errors = [item for item in outcomes if isinstance(item, Exception)]
    assert all(isinstance(error, StaleOnboardingVersion) for error in errors)
    assert len(errors) <= 1
    assert AgentContract.objects.filter(recipient=agent).count() == 1
