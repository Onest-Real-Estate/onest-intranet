import pytest
from allauth.account.signals import user_signed_up
from django.contrib.auth.models import Group

from apps.user.models import User
from apps.user.roles import (
    ADMIN,
    AGENT,
    BRANCH_MANAGER,
    REGION_MANAGER,
    SEEDED_GROUPS,
    primary_role_label,
    seed_role_groups,
)


class _FakeSocialLogin:
    def __init__(self, extra_data):
        self.account = type("Account", (), {"extra_data": extra_data})()


@pytest.mark.django_db
def test_new_signup_gets_default_group():
    user = User.objects.create_user(email="bob@example.com")
    user_signed_up.send(sender=User, request=None, user=user)
    assert list(user.groups.values_list("name", flat=True)) == ["Users"]


@pytest.mark.django_db
def test_signal_creates_default_group_when_missing():
    Group.objects.filter(name="Users").delete()
    user = User.objects.create_user(email="bob@example.com")
    user_signed_up.send(sender=User, request=None, user=user)
    assert Group.objects.filter(name="Users").exists()


@pytest.mark.django_db
def test_signal_is_idempotent():
    user = User.objects.create_user(email="bob@example.com")
    user_signed_up.send(sender=User, request=None, user=user)
    user_signed_up.send(sender=User, request=None, user=user)
    assert user.groups.count() == 1


@pytest.mark.django_db
def test_microsoft_signup_copies_display_name_and_phone():
    user = User.objects.create_user(
        email="jane@example.com", first_name="Jane", last_name="Doe"
    )
    user_signed_up.send(
        sender=User,
        request=None,
        user=user,
        sociallogin=_FakeSocialLogin(
            {
                "displayName": "Jane Q Doe",
                "mobilePhone": "2025550100",
            }
        ),
    )
    user.refresh_from_db()
    assert user.display_name == "Jane Q Doe"
    assert user.phone_number == "(202) 555-0100"


@pytest.mark.django_db
def test_microsoft_signup_ignores_non_us_phone():
    user = User.objects.create_user(email="jane@example.com")
    user_signed_up.send(
        sender=User,
        request=None,
        user=user,
        sociallogin=_FakeSocialLogin({"mobilePhone": "+44 20 7946 0958"}),
    )
    user.refresh_from_db()
    assert user.phone_number == ""


@pytest.mark.django_db
def test_seed_role_groups_creates_management_roles():
    seed_role_groups()
    names = set(
        Group.objects.filter(name__in=SEEDED_GROUPS).values_list("name", flat=True)
    )
    assert names == set(SEEDED_GROUPS)


@pytest.mark.django_db
def test_primary_role_label_prefers_superuser():
    user = User.objects.create_superuser(email="root@example.com", password="x")
    group, _ = Group.objects.get_or_create(name=AGENT)
    user.groups.add(group)
    assert primary_role_label(user) == "Superadmin"


@pytest.mark.django_db
def test_primary_role_label_uses_highest_priority_group():
    user = User.objects.create_user(email="mgr@example.com")
    admin, _ = Group.objects.get_or_create(name=ADMIN)
    branch, _ = Group.objects.get_or_create(name=BRANCH_MANAGER)
    user.groups.add(admin, branch)
    assert primary_role_label(user) == "Admin"


@pytest.mark.django_db
def test_primary_role_label_for_region_and_branch_managers():
    region_user = User.objects.create_user(email="region@example.com")
    region_group, _ = Group.objects.get_or_create(name=REGION_MANAGER)
    region_user.groups.add(region_group)
    assert primary_role_label(region_user) == "Region manager"

    branch_user = User.objects.create_user(email="branch@example.com")
    branch_group, _ = Group.objects.get_or_create(name=BRANCH_MANAGER)
    branch_user.groups.add(branch_group)
    assert primary_role_label(branch_user) == "Branch manager"
