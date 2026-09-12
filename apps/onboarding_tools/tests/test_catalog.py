"""The catalog's two load-bearing rules: where a tool applies, and who may
watch somebody's progress.

Both are the reason this is data rather than an enum, so both are tested
against the real seeded rows rather than fixtures invented here.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.onboarding_tools import services
from apps.onboarding_tools.models import (
    AgentToolStatus,
    OnboardingTool,
    OnboardingToolOfficeAudience,
    ToolState,
)
from apps.user.models import Office, UserRoleAssignment
from apps.user.services.role_assignments import get_effective_access
from apps.user.tests.test_profile import completed_user


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def office(slug: str) -> Office:
    return Office.objects.get(slug=slug)


def person(email: str, slug: str = "fairfax-va"):
    return completed_user(email=email, office=office(slug))


def assign_role(user, role: str, scope_type: str, scope_office=None) -> None:
    assignment = UserRoleAssignment(
        user=user, role=role, scope_type=scope_type, scope_office=scope_office
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()


def grant(user, codename: str = "manage_new_agent_onboarding"):
    """A role assignment carries *scope*; Django permissions are granted
    separately in this project, so an onboarding manager needs both."""
    from django.contrib.auth.models import Permission

    user.user_permissions.add(
        Permission.objects.get(content_type__app_label="web", codename=codename)
    )
    # `has_perm` caches on first call, so hand back a fresh instance.
    return type(user).objects.get(pk=user.pk)


def manager(email: str = "admin@example.com", slug: str = "onest-head-office"):
    """Somebody who may move other people's checklists brokerage-wide."""
    user = person(email, slug)
    assign_role(user, "system_admin", "company")
    return grant(user)


def tool(slug: str) -> OnboardingTool:
    return OnboardingTool.objects.get(slug=slug)


# --------------------------------------------------------------------------- #
# The catalog itself
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_the_seed_matches_the_three_groups(seeded):
    counts = {
        group: OnboardingTool.objects.filter(group=group).count()
        for group in ("company", "association", "marketing")
    }
    assert counts == {"company": 9, "association": 7, "marketing": 7}


@pytest.mark.django_db
def test_every_tool_tells_the_agent_how_to_get_it(seeded):
    """The reason the catalog is worth having. A row that names a tool without
    saying how to obtain it has moved the problem, not solved it."""
    for row in OnboardingTool.objects.all():
        assert row.setup_steps or row.contact_label, row.slug


@pytest.mark.django_db
def test_a_tool_with_neither_steps_nor_a_contact_is_refused(seeded):
    """Enforced by the database, not only by the seed's good manners."""
    from django.db.utils import IntegrityError

    with pytest.raises(IntegrityError):
        OnboardingTool.objects.create(
            slug="mystery",
            name="Mystery",
            description="Nobody knows how to get this.",
            group="company",
        )


# --------------------------------------------------------------------------- #
# Location
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_a_connecticut_agent_gets_the_connecticut_association_tools(seeded):
    ct = person("ct@example.com", "connecticut")
    names = {row.name for row in OnboardingTool.objects.for_office(ct.office)}
    assert {"SmartMLS", "CT Realtors", "SentriLock"} <= names


@pytest.mark.django_db
def test_an_agent_elsewhere_is_not_told_to_join_the_wrong_mls(seeded):
    """The bug the whole audience model exists to prevent."""
    va = person("va@example.com", "fairfax-va")
    names = {row.name for row in OnboardingTool.objects.for_office(va.office)}
    assert "SmartMLS" not in names
    assert "CT Realtors" not in names
    # …but the company-wide set still applies.
    assert {"SkySlope", "Lofty", "Office 365"} <= names


@pytest.mark.django_db
def test_a_branch_under_a_state_inherits_its_tools(seeded):
    """`include_descendants` is what makes a state expressible without one row
    per branch."""
    branch = Office.objects.create(
        name="New Haven",
        slug="new-haven",
        parent=office("connecticut"),
        stable_key="new-haven",
    )
    names = {row.name for row in OnboardingTool.objects.for_office(branch)}
    assert "SmartMLS" in names


@pytest.mark.django_db
def test_a_row_without_descendants_covers_only_its_own_office(seeded):
    branch = Office.objects.create(
        name="New Haven",
        slug="new-haven-2",
        parent=office("connecticut"),
        stable_key="new-haven-2",
    )
    OnboardingToolOfficeAudience.objects.filter(tool=tool("smartmls")).update(
        include_descendants=False
    )
    names = {row.name for row in OnboardingTool.objects.for_office(branch)}
    assert "SmartMLS" not in names


@pytest.mark.django_db
def test_an_agent_with_no_office_gets_only_the_company_wide_set(seeded):
    """Guessing an association from a blank field would tell somebody to join
    the wrong one."""
    rows = OnboardingTool.objects.for_office(None)
    assert rows.count() > 0
    assert all(row.company_wide for row in rows)


@pytest.mark.django_db
def test_an_inactive_tool_leaves_every_checklist(seeded):
    va = person("va@example.com")
    OnboardingTool.objects.filter(slug="lofty").update(is_active=False)
    names = {item.tool.name for item in services.checklist_for(va)}
    assert "Lofty" not in names


# --------------------------------------------------------------------------- #
# Progress
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_a_tool_with_no_row_reads_as_not_started(seeded):
    """Rows are created lazily, so adding a tool to the catalog costs nothing."""
    agent = person("agent@example.com")
    checklist = services.checklist_for(agent)
    assert checklist
    assert all(item.state == ToolState.NOT_STARTED for item in checklist)
    assert AgentToolStatus.objects.count() == 0


@pytest.mark.django_db
def test_readiness_counts_only_required_tools(seeded):
    """An optional tool left alone must not make somebody read as incomplete."""
    agent = person("agent@example.com")
    required = {
        item.tool.slug
        for item in services.checklist_for(agent)
        if item.tool.is_required
    }
    assert "facebook" not in required
    assert services.readiness_for(agent).total == len(required)


@pytest.mark.django_db
def test_marking_a_tool_ready_moves_the_figure(seeded):
    agent = person("agent@example.com")
    admin = manager()

    before = services.readiness_for(agent)
    services.set_state(
        actor=admin, agent=agent, tool=tool("office-365"), state=ToolState.READY
    )
    after = services.readiness_for(agent)

    assert after.ready == before.ready + 1
    assert after.percent > before.percent


@pytest.mark.django_db
def test_ready_stamps_a_timestamp_and_reverting_clears_it(seeded):
    agent = person("agent@example.com")
    admin = manager()

    row = services.set_state(
        actor=admin, agent=agent, tool=tool("lofty"), state=ToolState.READY
    )
    assert row.ready_at is not None

    # Coming back out of a settled state is a correction, so it carries a
    # reason: the agent was already told this one was working.
    row = services.set_state(
        actor=admin,
        agent=agent,
        tool=tool("lofty"),
        state=ToolState.BLOCKED,
        note="Vendor suspended the seat.",
    )
    assert row.ready_at is None


@pytest.mark.django_db
def test_not_needed_counts_as_settled(seeded):
    """A tool somebody has been excused from is not outstanding work."""
    agent = person("agent@example.com")
    admin = manager()

    before = services.readiness_for(agent).ready
    services.set_state(
        actor=admin,
        agent=agent,
        tool=tool("closely"),
        state=ToolState.NOT_APPLICABLE,
    )
    assert services.readiness_for(agent).ready == before + 1


@pytest.mark.django_db
def test_an_agent_cannot_mark_their_own_tools_ready(seeded):
    """Self-attestation tells nobody anything, and the figure would stop
    meaning "IT confirmed this works"."""
    agent = manager("agent@example.com", "fairfax-va")

    with pytest.raises(PermissionDenied):
        services.set_state(
            actor=agent, agent=agent, tool=tool("lofty"), state=ToolState.READY
        )


@pytest.mark.django_db
def test_somebody_without_the_onboarding_grant_cannot_move_a_checklist(seeded):
    agent = person("agent@example.com")
    colleague = person("colleague@example.com")

    with pytest.raises(PermissionDenied):
        services.set_state(
            actor=colleague, agent=agent, tool=tool("lofty"), state=ToolState.READY
        )


@pytest.mark.django_db
def test_an_unknown_state_is_refused(seeded):
    agent = person("agent@example.com")
    admin = manager()

    with pytest.raises(ValidationError):
        services.set_state(
            actor=admin, agent=agent, tool=tool("lofty"), state="probably_fine"
        )


# --------------------------------------------------------------------------- #
# Who may watch whose progress
# --------------------------------------------------------------------------- #


def watchable(user) -> set[str]:
    return set(
        AgentToolStatus.objects.for_reader(user, access=get_effective_access(user))
        .values_list("agent__email", flat=True)
        .distinct()
    )


@pytest.mark.django_db
def test_an_agent_sees_their_own_progress(seeded):
    agent = person("agent@example.com")
    other = person("other@example.com")
    admin = manager()
    for who in (agent, other):
        services.set_state(
            actor=admin, agent=who, tool=tool("lofty"), state=ToolState.READY
        )

    assert watchable(agent) == {"agent@example.com"}


@pytest.mark.django_db
def test_a_branch_manager_sees_their_branch_and_not_a_sibling(seeded):
    fairfax = person("fx@example.com", "fairfax-va")
    harrisburg = person("hb@example.com", "harrisburg")
    admin = manager()
    for who in (fairfax, harrisburg):
        services.set_state(
            actor=admin, agent=who, tool=tool("lofty"), state=ToolState.READY
        )

    branch_lead = person("branch@example.com", "fairfax-va")
    assign_role(branch_lead, "branch_manager", "office", office("fairfax-va"))

    assert watchable(branch_lead) == {"fx@example.com"}


@pytest.mark.django_db
def test_company_reach_sees_every_office(seeded):
    fairfax = person("fx@example.com", "fairfax-va")
    harrisburg = person("hb@example.com", "harrisburg")
    admin = manager()
    for who in (fairfax, harrisburg):
        services.set_state(
            actor=admin, agent=who, tool=tool("lofty"), state=ToolState.READY
        )

    assert {"fx@example.com", "hb@example.com"} <= watchable(admin)


@pytest.mark.django_db
def test_the_checklist_does_not_cost_a_query_per_tool(
    seeded, django_assert_num_queries
):
    """Two dozen tools must not become two dozen queries."""
    agent = person("agent@example.com", "connecticut")
    admin = manager()
    services.set_state(
        actor=admin, agent=agent, tool=tool("lofty"), state=ToolState.READY
    )

    # One read for the catalog, one for this agent's statuses, plus the walk
    # up the office tree that decides which location-specific tools apply.
    # That walk is O(tree depth) — three or four — and crucially *not* O(tools):
    # the cost does not grow as the catalog does, which is the property that
    # matters when this list doubles.
    with django_assert_num_queries(4):
        rows = services.checklist_for(agent)
    assert len(rows) == 23
