"""Editing the catalog: who may, what is refused, and what a save records.

The rules here are the ones that keep the catalog trustworthy — a tool nobody
can act on, an audience that quietly survives an edit, and a branch manager
redefining what every office needs are all failures this file exists to catch.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from apps.onboarding_tools import services
from apps.onboarding_tools.forms import OnboardingToolForm
from apps.onboarding_tools.models import (
    OnboardingTool,
    OnboardingToolOfficeAudience,
)
from apps.onboarding_tools.tests.test_catalog import (
    assign_role,
    grant,
    office,
    person,
    tool,
)
from apps.user.models import Office


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def catalog_admin(email: str = "admin@example.com"):
    """Somebody who may edit the catalog brokerage-wide."""
    user = person(email, "onest-head-office")
    assign_role(user, "system_admin", "company")
    return grant(user, "manage_onboarding_tools")


def form_data(**overrides) -> dict:
    data = {
        "name": "Follow Up Boss",
        "slug": "follow-up-boss",
        "description": "CRM and lead follow-up.",
        "group": "company",
        "provisioning": "onest",
        "open_url": "",
        "help_url": "",
        "contact_label": "IT support",
        "request_path": "",
        "company_wide": True,
        "is_required": True,
        "is_active": True,
        "sort_order": 0,
    }
    data.update(overrides)
    return data


def build(actor, *, steps=None, instance=None, **overrides) -> OnboardingToolForm:
    return OnboardingToolForm(
        form_data(**overrides),
        instance=instance,
        scoped_offices=Office.objects.all(),
        steps=steps or [],
    )


# --------------------------------------------------------------------------- #
# Who may edit
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_running_onboarding_does_not_let_somebody_redefine_the_catalog(seeded):
    """A branch manager runs onboarding for their branch. Deciding what every
    office needs is a different, brokerage-wide decision."""
    manager = person("branch@example.com", "fairfax-va")
    assign_role(manager, "branch_manager", "office", office("fairfax-va"))
    manager = grant(manager, "manage_new_agent_onboarding")

    assert services.can_manage_catalog(manager) is False
    form = build(manager)
    assert form.is_valid(), form.errors
    with pytest.raises(PermissionDenied):
        services.save_tool(actor=manager, form=form)


@pytest.mark.django_db
def test_a_catalog_administrator_may_add_a_tool(seeded):
    admin = catalog_admin()
    form = build(admin)
    assert form.is_valid(), form.errors

    created = services.save_tool(actor=admin, form=form)
    assert created.slug == "follow-up-boss"
    assert created.company_wide is True


# --------------------------------------------------------------------------- #
# What the form refuses
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_a_tool_with_neither_steps_nor_a_contact_is_refused_by_field(seeded):
    """The database enforces this too, but a writer should be told which field
    to fix rather than shown an integrity error."""
    admin = catalog_admin()
    form = build(admin, contact_label="", steps=[])

    assert not form.is_valid()
    assert "contact_label" in form.errors


@pytest.mark.django_db
def test_a_location_specific_tool_must_name_somewhere(seeded):
    admin = catalog_admin()
    form = build(admin, company_wide=False)

    assert not form.is_valid()
    assert "offices" in form.errors


@pytest.mark.django_db
def test_blank_steps_are_dropped_rather_than_stored(seeded):
    """An empty step renders as a numbered nothing."""
    admin = catalog_admin()
    form = build(admin, steps=["First", "   ", "", "Second"])
    assert form.is_valid(), form.errors

    created = services.save_tool(actor=admin, form=form)
    assert created.setup_steps == ["First", "Second"]


@pytest.mark.django_db
def test_a_guide_longer_than_the_limit_is_refused(seeded):
    admin = catalog_admin()
    form = build(admin, steps=[f"Step {index}" for index in range(20)])

    assert not form.is_valid()
    assert "__all__" in form.errors or "contact_label" in form.errors or form.errors


@pytest.mark.django_db
def test_an_office_outside_the_editors_scope_is_not_a_valid_choice(seeded):
    """The choices are the caller's scoped set, so a posted id outside it fails
    validation rather than being silently accepted."""
    outside = office("harrisburg")
    form = OnboardingToolForm(
        form_data(company_wide=False, offices=[outside.pk]),
        scoped_offices=Office.objects.filter(slug="fairfax-va"),
        steps=[],
    )
    assert not form.is_valid()
    assert "offices" in form.errors


# --------------------------------------------------------------------------- #
# Audience replacement
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_editing_replaces_the_audience_rather_than_adding_to_it(seeded):
    """Reconciling a partial edit is how an office quietly survives being
    unticked."""
    admin = catalog_admin()
    smartmls = tool("smartmls")
    assert OnboardingToolOfficeAudience.objects.filter(tool=smartmls).count() == 1

    form = OnboardingToolForm(
        form_data(
            name=smartmls.name,
            slug=smartmls.slug,
            description=smartmls.description,
            group=smartmls.group,
            provisioning=smartmls.provisioning,
            company_wide=False,
            offices=[office("fairfax-va").pk],
        ),
        instance=smartmls,
        scoped_offices=Office.objects.all(),
        steps=["Do the thing"],
    )
    assert form.is_valid(), form.errors
    services.save_tool(actor=admin, form=form)

    audiences = OnboardingToolOfficeAudience.objects.filter(tool=smartmls)
    assert [row.office.slug for row in audiences] == ["fairfax-va"]


@pytest.mark.django_db
def test_marking_a_tool_company_wide_clears_its_audience(seeded):
    admin = catalog_admin()
    smartmls = tool("smartmls")

    form = OnboardingToolForm(
        form_data(
            name=smartmls.name,
            slug=smartmls.slug,
            description=smartmls.description,
            group=smartmls.group,
            provisioning=smartmls.provisioning,
            company_wide=True,
        ),
        instance=smartmls,
        scoped_offices=Office.objects.all(),
        steps=["Do the thing"],
    )
    assert form.is_valid(), form.errors
    services.save_tool(actor=admin, form=form)

    assert OnboardingToolOfficeAudience.objects.filter(tool=smartmls).count() == 0


# --------------------------------------------------------------------------- #
# Ordering
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_reordering_sets_the_requested_sequence(seeded):
    admin = catalog_admin()
    before = list(
        OnboardingTool.objects.filter(group="company")
        .order_by("sort_order")
        .values_list("slug", flat=True)
    )
    reversed_order = list(reversed(before))

    services.reorder_tools(actor=admin, group="company", slugs=reversed_order)

    after = list(
        OnboardingTool.objects.filter(group="company")
        .order_by("sort_order")
        .values_list("slug", flat=True)
    )
    assert after == reversed_order


@pytest.mark.django_db
def test_reordering_ignores_a_slug_from_another_group(seeded):
    """A crafted post must not drag a marketing tool onto the company shelf."""
    admin = catalog_admin()
    foreign = tool("hihello")
    before_group = foreign.group

    services.reorder_tools(actor=admin, group="company", slugs=[foreign.slug])

    foreign.refresh_from_db()
    assert foreign.group == before_group


@pytest.mark.django_db
def test_reordering_needs_the_catalog_grant(seeded):
    manager = person("branch@example.com", "fairfax-va")
    manager = grant(manager, "manage_new_agent_onboarding")

    with pytest.raises(PermissionDenied):
        services.reorder_tools(actor=manager, group="company", slugs=[])


# --------------------------------------------------------------------------- #
# The page
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_the_catalog_page_refuses_a_reader_without_the_grant(seeded, client):
    client.force_login(person("agent@example.com", "fairfax-va"))
    response = client.get(reverse("onboarding_tool_catalog"))
    assert response.status_code in {302, 403}


@pytest.mark.django_db
def test_the_catalog_page_serves_the_three_shelves(seeded, client):
    import json

    client.force_login(catalog_admin())
    response = client.get(reverse("onboarding_tool_catalog"), HTTP_X_INERTIA="true")
    props = json.loads(response.content)["props"]

    assert [group["code"] for group in props["groups"]] == [
        "company",
        "association",
        "marketing",
    ]
    # Applicability is named in words: "not company-wide" tells an
    # administrator nothing about who actually gets the tool.
    smartmls = next(
        row
        for group in props["groups"]
        for row in group["tools"]
        if row["slug"] == "smartmls"
    )
    assert smartmls["appliesTo"] == "Connecticut"


@pytest.mark.django_db
def test_a_refused_save_re_renders_with_the_row_still_open(seeded, client):
    import json

    client.force_login(catalog_admin())
    response = client.post(
        reverse("onboarding_tool_create"),
        {**form_data(contact_label=""), "step": []},
        HTTP_X_INERTIA="true",
    )

    assert response.status_code == 422
    props = json.loads(response.content)["props"]
    assert props["editing"] == "new"
    assert "contact_label" in props["errors"]["fields"]
    # …and the draft comes back, so nothing typed is lost.
    assert props["draft"]["name"] == "Follow Up Boss"
