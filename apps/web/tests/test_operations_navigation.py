import json

import pytest
from django.contrib.auth.models import Group, Permission
from django.urls import reverse

from apps.user.models import Office, User
from apps.user.roles import ADMIN, AGENT, BRANCH_MANAGER, REGION_MANAGER, ScopeType
from apps.user.services.role_assignments import (
    create_role_assignment,
    get_effective_permissions,
)
from apps.web.authorization import ROUTE_POLICIES
from apps.web.operations import (
    OPERATIONS_DESTINATIONS,
    OPERATIONS_FEATURES,
    ROLE_OPERATION_PERMISSIONS,
    operations_policy_key,
)


def user(email: str) -> User:
    return User.objects.create_user(email=email, profile_completed=True)


def branch_office() -> Office:
    office = Office.assignable_queryset().filter(kind=Office.Kind.BRANCH).first()
    assert office is not None
    return office


def permission(codename: str) -> Permission:
    return Permission.objects.get(
        content_type__app_label="web",
        content_type__model="operationspermission",
        codename=codename.removeprefix("web."),
    )


def inertia_props(response) -> dict:
    return json.loads(response.content)["props"]


@pytest.mark.django_db
def test_registry_has_exact_destinations_order_routes_and_permissions():
    assert [destination.label for destination in OPERATIONS_DESTINATIONS] == [
        "Users",
        "New Agent List",
        "Add New User",
        "Assign User Roles",
        "Agent Contracts",
        "Transactions",
        "Inventory",
        "Reservations",
        "Announcements",
        "Training",
        "Documents",
        "Compliance",
        "Feedback",
        "Platform Tasks",
        "Offices",
        "IT Support",
    ]
    assert [destination.order for destination in OPERATIONS_DESTINATIONS] == list(
        range(10, 170, 10)
    )
    assert [destination.section for destination in OPERATIONS_DESTINATIONS] == [
        *("People" for _ in range(5)),
        *("Operations" for _ in range(3)),
        *("Content" for _ in range(3)),
        *("Governance & support" for _ in range(5)),
    ]
    assert len({destination.key for destination in OPERATIONS_DESTINATIONS}) == 16
    assert (
        len({destination.route_name for destination in OPERATIONS_DESTINATIONS}) == 16
    )
    assert (
        len({destination.permission for destination in OPERATIONS_DESTINATIONS}) == 16
    )
    for destination in OPERATIONS_DESTINATIONS:
        assert reverse(destination.route_name) == f"/{destination.path}"
        assert destination.feature in OPERATIONS_FEATURES
        assert OPERATIONS_FEATURES[destination.feature] is (
            destination.route_name == "admin_new_agents"
        )


@pytest.mark.django_db
def test_every_destination_policy_matches_its_minimum_permission_and_scope():
    for destination in OPERATIONS_DESTINATIONS:
        policy = ROUTE_POLICIES[operations_policy_key(destination)]
        assert policy.route_names == (destination.route_name,)
        assert policy.all_permissions == (destination.permission,)
        assert policy.scope_rule == destination.scope_rule
        assert policy.access == "permission_protected"


@pytest.mark.django_db
def test_admin_group_receives_all_operations_permissions():
    group = Group.objects.get(name=ADMIN)
    actual = {
        f"{app_label}.{codename}"
        for app_label, codename in group.permissions.values_list(
            "content_type__app_label", "codename"
        )
        if app_label == "web"
    }
    assert actual.issuperset(ROLE_OPERATION_PERMISSIONS[ADMIN])


@pytest.mark.django_db
def test_scoped_management_role_permission_matrix():
    expected = {
        REGION_MANAGER: {
            "Users",
            "New Agent List",
            "Transactions",
            "Inventory",
            "Reservations",
            "Training",
            "Documents",
            "Feedback",
            "Offices",
        },
        BRANCH_MANAGER: {
            "Users",
            "New Agent List",
            "Inventory",
            "Reservations",
            "Training",
            "Documents",
            "Feedback",
            "Offices",
        },
    }
    for role, labels in expected.items():
        allowed = ROLE_OPERATION_PERMISSIONS[role]
        assert {
            destination.label
            for destination in OPERATIONS_DESTINATIONS
            if destination.permission in allowed
        } == labels
    assert "web.assign_user_roles" not in ROLE_OPERATION_PERMISSIONS[BRANCH_MANAGER]


@pytest.mark.django_db
def test_brokerage_admin_can_reach_every_registered_destination(client):
    actor = User.objects.create_superuser(email="system@example.com")
    admin = user("broker-admin@example.com")
    create_role_assignment(
        actor=actor,
        target_user=admin,
        role=ADMIN,
        scope_type=ScopeType.COMPANY,
    )
    assert get_effective_permissions(admin).issuperset(
        ROLE_OPERATION_PERMISSIONS[ADMIN]
    )
    client.force_login(admin)

    dashboard = client.get(reverse("dashboard"), HTTP_X_INERTIA="true")
    assert {destination.feature for destination in OPERATIONS_DESTINATIONS}.issubset(
        inertia_props(dashboard)["features"]
    )

    for destination in OPERATIONS_DESTINATIONS:
        response = client.get(
            reverse(destination.route_name),
            HTTP_X_INERTIA="true",
        )
        assert response.status_code == 200
        props = inertia_props(response)
        if destination.route_name == "admin_new_agents":
            assert "agents" in props
            assert "filterOptions" in props
            continue
        assert props["title"] == destination.label
        assert props["administrative"] is True
        assert props["scope"] == {
            "level": "brokerage",
            "label": "Brokerage-wide",
        }
        assert "count" not in props
        assert "records" not in props


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("route_name", "permission_name"),
    [
        ("admin_add_user", "web.add_users"),
        ("admin_assign_roles", "web.assign_user_roles"),
        ("admin_compliance", "web.view_compliance"),
        ("admin_platform_tasks", "web.view_platform_tasks"),
        ("admin_it_support", "web.view_it_support"),
    ],
)
def test_high_risk_direct_routes_require_their_own_permission(
    client,
    route_name,
    permission_name,
):
    account = user(f"{route_name}@example.com")
    account.user_permissions.add(permission("web.view_users"))
    client.force_login(account)

    denied = client.get(reverse(route_name), HTTP_X_INERTIA="true")
    assert denied.status_code == 403
    assert json.loads(denied.content)["component"] == "PermissionDenied"

    account.user_permissions.add(permission(permission_name))
    allowed = client.get(reverse(route_name), HTTP_X_INERTIA="true")
    assert allowed.status_code == 200


@pytest.mark.django_db
def test_feature_availability_never_grants_permission(client, monkeypatch):
    account = user("no-permission@example.com")
    client.force_login(account)
    monkeypatch.setitem(OPERATIONS_FEATURES, "admin-compliance", True)

    response = client.get(reverse("admin_compliance"), HTTP_X_INERTIA="true")

    assert response.status_code == 403
    assert b"Compliance" not in response.content


@pytest.mark.django_db
def test_permission_revocation_takes_effect_on_the_next_nested_visit(client):
    account = user("revoked@example.com")
    granted = permission("web.view_users")
    account.user_permissions.add(granted)
    client.force_login(account)
    assert client.get(reverse("admin_users")).status_code == 200

    account.user_permissions.remove(granted)
    response = client.get(reverse("admin_users"), HTTP_X_INERTIA="true")

    assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("persona", "role", "scope_type", "permission_name", "route_name"),
    [
        (
            "regional-coordinator",
            REGION_MANAGER,
            ScopeType.REGION,
            "web.view_transactions",
            "admin_transactions",
        ),
        (
            "branch-admin",
            BRANCH_MANAGER,
            ScopeType.OFFICE,
            "web.view_users",
            "admin_users",
        ),
        (
            "compliance",
            AGENT,
            ScopeType.OFFICE,
            "web.view_compliance",
            "admin_compliance",
        ),
        (
            "accountant",
            AGENT,
            ScopeType.OFFICE,
            "web.view_transactions",
            "admin_transactions",
        ),
        (
            "marketing",
            AGENT,
            ScopeType.OFFICE,
            "web.manage_announcements",
            "admin_announcements",
        ),
        (
            "it-support",
            AGENT,
            ScopeType.OFFICE,
            "web.view_it_support",
            "admin_it_support",
        ),
    ],
)
def test_scoped_and_specialty_personas_reach_only_authorized_scope(
    client,
    persona,
    role,
    scope_type,
    permission_name,
    route_name,
):
    actor = User.objects.create_superuser(email=f"system-{persona}@example.com")
    office = branch_office()
    scope_office = office.region if scope_type == ScopeType.REGION else office
    assert scope_office is not None
    account = user(f"{persona}@example.com")
    account.office = office
    account.save(update_fields=["office"])
    create_role_assignment(
        actor=actor,
        target_user=account,
        role=role,
        scope_type=scope_type,
        scope_office=scope_office,
    )
    account.user_permissions.add(permission(permission_name))
    client.force_login(account)

    response = client.get(reverse(route_name), HTTP_X_INERTIA="true")

    assert response.status_code == 200
    scope = inertia_props(response)["scope"]
    expected_level = "region" if scope_type == ScopeType.REGION else "office"
    assert scope["level"] == expected_level
    assert scope["label"] == scope_office.name
    assert "members" not in inertia_props(response)
    assert "items" not in inertia_props(response)


@pytest.mark.django_db
def test_platform_tasks_and_it_support_return_no_internal_operational_data(client):
    account = user("support@example.com")
    account.user_permissions.add(
        permission("web.view_platform_tasks"),
        permission("web.view_it_support"),
    )
    client.force_login(account)

    for route_name in ("admin_platform_tasks", "admin_it_support"):
        props = inertia_props(client.get(reverse(route_name), HTTP_X_INERTIA="true"))
        serialized = json.dumps(props).lower()
        for forbidden in ("secret", "traceback", "worker", "log", "queue"):
            assert forbidden not in serialized
