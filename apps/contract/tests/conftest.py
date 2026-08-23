"""Fixtures for agent contract domain tests."""

from __future__ import annotations

import pytest

from apps.user.models import Office, User, UserRoleAssignment
from apps.user.tests.test_profile import completed_user


@pytest.fixture
def seeded_offices():
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def office(slug: str) -> Office:
    return Office.objects.get(slug=slug)


def assign(user: User, role: str, scope_type: str, scope_office=None) -> None:
    assignment = UserRoleAssignment(
        user=user, role=role, scope_type=scope_type, scope_office=scope_office
    )
    assignment.refresh_status()
    assignment.full_clean()
    assignment.save()


def company_admin(seeded_offices) -> User:
    user = completed_user(
        email="contract.admin@example.com", office=office("onest-head-office")
    )
    assign(user, "system_admin", "company")
    return user


def branch_admin(seeded_offices, slug="fairfax-va") -> User:
    user = completed_user(email=f"branch.{slug}@example.com", office=office(slug))
    assign(user, "branch_manager", "office", office(slug))
    return user


def agent(seeded_offices, *, email="agent@example.com", slug="fairfax-va") -> User:
    return completed_user(email=email, office=office(slug))
