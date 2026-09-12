"""The invitation lifecycle: transitions, provenance, events, and the merge.

The catalog is now the only source of tool state, so these cover the rules that
replaced the retired four-value enum: which moves are allowed, what a recorded
invitation proves, what the durable event may carry, and how legacy rows fold
in without losing what they knew.
"""

from __future__ import annotations

import json
from importlib import import_module

import pytest
from django.apps import apps as django_apps
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.db.utils import IntegrityError
from django.test.utils import CaptureQueriesContext

from apps.audit.models import AuditEvent, DomainEvent
from apps.onboarding_tools import services
from apps.onboarding_tools.models import AgentToolStatus, ToolState
from apps.onboarding_tools.payloads import tool_payload
from apps.onboarding_tools.tests.test_catalog import manager, person, tool
from apps.user.models import OnboardingToolSetup, UserOnboardingCase

LEGACY_MIGRATION = "apps.onboarding_tools.migrations.0004_migrate_legacy_tool_setups"


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


# --------------------------------------------------------------------------- #
# Transitions
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_forward_moves_may_skip_ahead(seeded):
    """A self-serve tool goes straight to ready; that is not out of order."""
    agent = person("agent@example.com")
    admin = manager()

    row = services.set_state(
        actor=admin, agent=agent, tool=tool("onedrive"), state=ToolState.READY
    )

    assert row.state == ToolState.READY
    assert row.ready_at is not None


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("start", "target"),
    [
        (ToolState.READY, ToolState.IN_PROGRESS),
        (ToolState.INVITATION_SENT, ToolState.REQUESTED),
        (ToolState.NOT_APPLICABLE, ToolState.IN_PROGRESS),
    ],
)
def test_moving_back_demands_a_reason(seeded, start, target):
    agent = person("agent@example.com")
    admin = manager()
    services.set_state(actor=admin, agent=agent, tool=tool("lofty"), state=start)

    with pytest.raises(ValidationError) as refused:
        services.set_state(actor=admin, agent=agent, tool=tool("lofty"), state=target)
    assert "note" in refused.value.message_dict

    row = services.set_state(
        actor=admin,
        agent=agent,
        tool=tool("lofty"),
        state=target,
        note="Vendor withdrew the seat.",
    )
    assert row.state == target
    assert row.note == "Vendor withdrew the seat."


@pytest.mark.django_db
def test_a_self_serve_tool_has_no_invitation_to_send(seeded):
    agent = person("agent@example.com")
    admin = manager()

    with pytest.raises(ValidationError) as refused:
        services.set_state(
            actor=admin,
            agent=agent,
            tool=tool("onedrive"),
            state=ToolState.INVITATION_SENT,
        )

    assert "state" in refused.value.message_dict


@pytest.mark.django_db
def test_invitation_sent_records_who_sent_it_and_when(seeded):
    agent = person("agent@example.com")
    admin = manager()

    row = services.set_state(
        actor=admin,
        agent=agent,
        tool=tool("skyslope"),
        state=ToolState.INVITATION_SENT,
    )

    assert row.invitation_sent_at is not None
    assert row.invitation_sent_by == admin
    # Requesting is implied by sending: the checkpoint before it is not lost.
    assert row.requested_at is not None

    first_sent = row.invitation_sent_at
    resent = services.set_state(
        actor=admin,
        agent=agent,
        tool=tool("skyslope"),
        state=ToolState.INVITATION_SENT,
        note="Agent never received the first one.",
    )
    assert resent.invitation_sent_at >= first_sent


@pytest.mark.django_db
def test_moving_back_behind_the_invitation_clears_its_provenance(seeded):
    agent = person("agent@example.com")
    admin = manager()
    services.set_state(
        actor=admin, agent=agent, tool=tool("lofty"), state=ToolState.INVITATION_SENT
    )

    corrected = services.set_state(
        actor=admin,
        agent=agent,
        tool=tool("lofty"),
        state=ToolState.REQUESTED,
        note="Marked sent by mistake; nothing left our office.",
    )

    assert corrected.invitation_sent_at is None
    assert corrected.invitation_sent_by is None


@pytest.mark.django_db
def test_states_after_the_invitation_keep_the_provenance(seeded):
    agent = person("agent@example.com")
    admin = manager()
    services.set_state(
        actor=admin, agent=agent, tool=tool("lofty"), state=ToolState.INVITATION_SENT
    )

    ready = services.set_state(
        actor=admin, agent=agent, tool=tool("lofty"), state=ToolState.READY
    )

    assert ready.invitation_sent_at is not None
    assert ready.ready_at is not None


# --------------------------------------------------------------------------- #
# Constraints
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_the_database_refuses_invitation_sent_without_a_timestamp(seeded):
    agent = person("agent@example.com")

    with pytest.raises(IntegrityError):
        AgentToolStatus.objects.create(
            agent=agent, tool=tool("lofty"), state=ToolState.INVITATION_SENT
        )


@pytest.mark.django_db
def test_the_database_refuses_a_named_sender_without_a_time(seeded):
    agent = person("agent@example.com")
    admin = manager()

    with pytest.raises(IntegrityError):
        AgentToolStatus.objects.create(
            agent=agent,
            tool=tool("lofty"),
            state=ToolState.REQUESTED,
            invitation_sent_by=admin,
        )


# --------------------------------------------------------------------------- #
# The writer
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_repeating_the_same_command_changes_and_records_nothing_twice(
    seeded, django_capture_on_commit_callbacks
):
    agent = person("agent@example.com")
    admin = manager()

    # The audit entry is written after commit, so the callbacks have to run for
    # "was this recorded twice" to be answerable at all.
    with django_capture_on_commit_callbacks(execute=True):
        first = services.set_state(
            actor=admin, agent=agent, tool=tool("lofty"), state=ToolState.REQUESTED
        )
        second = services.set_state(
            actor=admin, agent=agent, tool=tool("lofty"), state=ToolState.REQUESTED
        )

    assert first.pk == second.pk
    assert (
        AuditEvent.objects.filter(action="onboarding_tool.state_changed").count() == 1
    )
    assert DomainEvent.objects.filter(name="onboarding_tool.state_changed").count() == 1


@pytest.mark.django_db
def test_an_agent_cannot_move_their_own_tools(seeded):
    agent = manager("agent@example.com", "fairfax-va")

    with pytest.raises(PermissionDenied):
        services.set_state(
            actor=agent,
            agent=agent,
            tool=tool("lofty"),
            state=ToolState.INVITATION_SENT,
        )


@pytest.mark.django_db
def test_the_event_carries_identifiers_and_never_the_note(seeded):
    agent = person("agent@example.com")
    admin = manager()

    services.set_state(
        actor=admin,
        agent=agent,
        tool=tool("lofty"),
        state=ToolState.INVITATION_SENT,
        note="Sent from ada@example.com with the vendor signup link.",
    )

    event = DomainEvent.objects.get(name="onboarding_tool.state_changed")
    assert event.payload["tool"] == "lofty"
    assert event.payload["agent_id"] == agent.pk
    assert event.payload["office_id"] == agent.office_id
    assert event.payload["from"] == ToolState.NOT_STARTED
    assert event.payload["to"] == ToolState.INVITATION_SENT
    assert event.payload["actor_id"] == admin.pk
    assert event.payload["invitation_sent_at"]

    recorded = json.dumps(event.payload)
    assert "vendor signup link" not in recorded
    assert "ada@example.com" not in recorded


# --------------------------------------------------------------------------- #
# Composition
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_bulk_composition_does_not_grow_with_the_number_of_agents(seeded):
    admin = manager()
    agents = [person(f"agent-{index}@example.com") for index in range(3)]
    services.set_state(
        actor=admin,
        agent=agents[0],
        tool=tool("lofty"),
        state=ToolState.INVITATION_SENT,
    )

    with CaptureQueriesContext(connection) as few:
        services.bulk_agent_onboarding_states(agents)

    more = agents + [person(f"extra-{index}@example.com") for index in range(6)]
    with CaptureQueriesContext(connection) as many:
        services.bulk_agent_onboarding_states(more)

    assert len(many) == len(few)


@pytest.mark.django_db
def test_the_agent_and_operational_payloads_agree_on_one_row(seeded):
    from apps.user.services.onboarding_state import build_onboarding_states

    agent = person("agent@example.com")
    admin = manager()
    services.set_state(
        actor=admin,
        agent=agent,
        tool=tool("lofty"),
        state=ToolState.INVITATION_SENT,
    )

    mine = next(
        tool_payload(item)
        for item in services.checklist_for(agent)
        if item.tool.slug == "lofty"
    )
    operational = next(
        row
        for row in build_onboarding_states([agent])[0].tool_setups
        if row["key"] == "lofty"
    )

    assert mine["state"]["code"] == operational["state"] == ToolState.INVITATION_SENT
    assert mine["invitation"]["state"] == operational["invitationState"] == "sent"
    assert mine["invitation"]["sentAt"] == operational["invitationSentAt"]


# --------------------------------------------------------------------------- #
# The legacy merge
# --------------------------------------------------------------------------- #


def legacy_row(agent, admin, tool_code: str, state: str):
    case, _created = UserOnboardingCase.objects.get_or_create(user=agent)
    return OnboardingToolSetup.objects.create(
        case=case, tool=tool_code, state=state, updated_by=admin
    )


def run_legacy_migration():
    import_module(LEGACY_MIGRATION).migrate_legacy_tool_setups(django_apps, None)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("legacy_state", "expected"),
    [
        ("not_started", ToolState.NOT_STARTED),
        ("in_progress", ToolState.IN_PROGRESS),
        ("ready", ToolState.READY),
        ("blocked", ToolState.BLOCKED),
        ("not_required", ToolState.NOT_APPLICABLE),
    ],
)
def test_every_legacy_state_lands_on_its_catalog_equivalent(
    seeded, legacy_state, expected
):
    agent = person("agent@example.com")
    admin = manager()
    legacy_row(agent, admin, "lofty", legacy_state)

    run_legacy_migration()

    row = AgentToolStatus.objects.get(agent=agent, tool__slug="lofty")
    assert row.state == expected
    assert (row.ready_at is not None) == (expected == ToolState.READY)


@pytest.mark.django_db
def test_the_legacy_microsoft_code_lands_on_the_catalog_slug(seeded):
    agent = person("agent@example.com")
    admin = manager()
    legacy_row(agent, admin, "microsoft365", "ready")

    run_legacy_migration()

    assert AgentToolStatus.objects.filter(
        agent=agent, tool__slug="office-365", state=ToolState.READY
    ).exists()


@pytest.mark.django_db
def test_a_retired_legacy_tool_is_left_alone(seeded):
    """Dotloop has no catalog row; inventing one would be making data up."""
    agent = person("agent@example.com")
    admin = manager()
    legacy_row(agent, admin, "dotloop", "ready")

    run_legacy_migration()

    assert not AgentToolStatus.objects.filter(agent=agent).exists()


@pytest.mark.django_db
def test_the_further_along_row_survives_a_conflict(seeded):
    agent = person("agent@example.com")
    admin = manager()
    services.set_state(
        actor=admin, agent=agent, tool=tool("lofty"), state=ToolState.READY
    )
    legacy_row(agent, admin, "lofty", "in_progress")

    run_legacy_migration()

    row = AgentToolStatus.objects.get(agent=agent, tool__slug="lofty")
    assert row.state == ToolState.READY
    assert row.ready_at is not None


@pytest.mark.django_db
def test_a_further_along_legacy_row_wins_over_an_untouched_one(seeded):
    agent = person("agent@example.com")
    admin = manager()
    services.set_state(
        actor=admin, agent=agent, tool=tool("lofty"), state=ToolState.REQUESTED
    )
    legacy_row(agent, admin, "lofty", "ready")

    run_legacy_migration()

    row = AgentToolStatus.objects.get(agent=agent, tool__slug="lofty")
    assert row.state == ToolState.READY
    assert row.ready_at is not None


@pytest.mark.django_db
def test_the_merge_is_repeatable(seeded):
    agent = person("agent@example.com")
    admin = manager()
    legacy_row(agent, admin, "lofty", "ready")

    run_legacy_migration()
    run_legacy_migration()

    assert AgentToolStatus.objects.filter(agent=agent, tool__slug="lofty").count() == 1
