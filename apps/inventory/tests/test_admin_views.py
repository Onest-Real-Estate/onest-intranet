"""Admin inventory HTTP surface tests."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.audit.models import AuditEvent
from apps.inventory.models import InventoryItem
from apps.inventory.taxonomy import (
    ItemAvailabilityState,
    ItemCategory,
    ItemCondition,
    TrackingMode,
)
from apps.user.models import Office, UserRoleAssignment
from apps.user.tests.test_profile import completed_user

MID_ATLANTIC = "region-mid-atlantic"


def _tiny_png() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )


@pytest.fixture
def seeded(db):
    from apps.user.office_seed import seed_offices
    from apps.user.roles import seed_brokerage_roles, seed_role_groups

    seed_role_groups()
    seed_brokerage_roles()
    seed_offices()


def office(slug: str) -> Office:
    return Office.objects.get(slug=slug)


def manager(email: str = "mgr@example.com"):
    from django.contrib.auth.models import Permission

    user = completed_user(email=email, office=office("fairfax-va"))
    assignment = UserRoleAssignment(
        user=user,
        role="branch_manager",
        scope_type="office",
        scope_office=office("fairfax-va"),
    )
    assignment.refresh_status()
    assignment.save()
    manage = Permission.objects.get(
        content_type__app_label="inventory", codename="manage_inventory"
    )
    view_sensitive = Permission.objects.get(
        content_type__app_label="inventory", codename="view_inventory_sensitive"
    )
    user.user_permissions.add(manage, view_sensitive)
    return user


def regional_manager(email: str = "regional@example.com"):
    from django.contrib.auth.models import Permission

    user = completed_user(email=email, office=office("fairfax-va"))
    assignment = UserRoleAssignment(
        user=user,
        role="region_manager",
        scope_type="region",
        scope_office=office(MID_ATLANTIC),
    )
    assignment.refresh_status()
    assignment.save()
    manage = Permission.objects.get(
        content_type__app_label="inventory", codename="manage_inventory"
    )
    view = Permission.objects.get(
        content_type__app_label="web", codename="view_inventory"
    )
    user.user_permissions.add(manage, view)
    return user


def viewer(email: str = "viewer@example.com"):
    from django.contrib.auth.models import Permission

    user = completed_user(email=email, office=office("fairfax-va"))
    view = Permission.objects.get(
        content_type__app_label="web", codename="view_inventory"
    )
    user.user_permissions.add(view)
    return user


def inertia_props(response) -> dict:
    return json.loads(response.content)["props"]


@pytest.mark.django_db
def test_inventory_admin_requires_permission(client, seeded):
    agent = completed_user(email="agent@example.com", office=office("fairfax-va"))
    client.force_login(agent)
    response = client.get(reverse("admin_inventory"))
    assert response.status_code == 403


@pytest.mark.django_db
def test_manager_sees_scoped_inventory_list(client, seeded):
    InventoryItem.objects.create(
        owner_office=office("fairfax-va"),
        name="Fairfax chair",
        category=ItemCategory.FURNITURE,
        tracking_mode=TrackingMode.POOLED,
        total_quantity=2,
        condition=ItemCondition.GOOD,
    )
    InventoryItem.objects.create(
        owner_office=office("harrisburg"),
        name="Harrisburg chair",
        category=ItemCategory.FURNITURE,
        tracking_mode=TrackingMode.POOLED,
        total_quantity=1,
        condition=ItemCondition.GOOD,
    )
    client.force_login(manager())
    response = client.get(reverse("admin_inventory"), HTTP_X_INERTIA="true")
    assert response.status_code == 200
    props = inertia_props(response)
    names = {row["name"] for row in props["items"]["items"]}
    assert names == {"Fairfax chair"}


@pytest.mark.django_db
def test_create_item_via_json_post(client, seeded):
    actor = manager()
    client.force_login(actor)
    response = client.post(
        reverse("admin_inventory_create"),
        data=json.dumps(
            {
                "name": "Branch laptop",
                "owner_office": office("fairfax-va").pk,
                "category": ItemCategory.ELECTRONICS,
                "tracking_mode": TrackingMode.SERIALIZED,
                "condition": ItemCondition.GOOD,
                "asset_id": "LAP-900",
                "total_quantity": 1,
                "context": "sheet",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 302
    item = InventoryItem.objects.get(asset_id="LAP-900")
    assert item.name == "Branch laptop"


@pytest.mark.django_db
def test_out_of_scope_item_is_not_found(client, seeded):
    other = InventoryItem.objects.create(
        owner_office=office("harrisburg"),
        name="Hidden",
        category=ItemCategory.OTHER,
        tracking_mode=TrackingMode.POOLED,
        total_quantity=1,
        condition=ItemCondition.GOOD,
    )
    client.force_login(manager())
    response = client.get(reverse("admin_inventory_item", args=[other.public_id]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_stale_version_returns_conflict(client, seeded):
    item = InventoryItem.objects.create(
        owner_office=office("fairfax-va"),
        name="Chair",
        category=ItemCategory.FURNITURE,
        tracking_mode=TrackingMode.POOLED,
        total_quantity=3,
        condition=ItemCondition.GOOD,
    )
    client.force_login(manager())
    detail = client.get(
        reverse("admin_inventory_item", args=[item.public_id]),
        HTTP_X_INERTIA="true",
    )
    version = inertia_props(detail)["version"]
    item.name = "Changed elsewhere"
    item.save(update_fields=["name", "updated_at"])
    response = client.post(
        reverse("admin_inventory_update", args=[item.public_id]),
        data=json.dumps(
            {
                "name": "Chair",
                "category": item.category,
                "condition": item.condition,
                "expected_version": version,
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 409


@pytest.mark.django_db
def test_list_sorts_by_quantity_desc(client, seeded):
    InventoryItem.objects.create(
        owner_office=office("fairfax-va"),
        name="Small kit",
        category=ItemCategory.OTHER,
        tracking_mode=TrackingMode.POOLED,
        total_quantity=2,
        condition=ItemCondition.GOOD,
    )
    InventoryItem.objects.create(
        owner_office=office("fairfax-va"),
        name="Large kit",
        category=ItemCategory.OTHER,
        tracking_mode=TrackingMode.POOLED,
        total_quantity=8,
        condition=ItemCondition.GOOD,
    )
    client.force_login(manager())
    response = client.get(
        reverse("admin_inventory"),
        {"sort": "quantity", "direction": "desc"},
        HTTP_X_INERTIA="true",
    )
    props = inertia_props(response)
    quantities = [row["totalQuantity"] for row in props["items"]["items"]]
    assert quantities == sorted(quantities, reverse=True)
    assert props["items"]["sort"] == {"key": "quantity", "direction": "desc"}


@pytest.mark.django_db
def test_viewer_can_list_but_not_create(client, seeded):
    client.force_login(viewer())
    list_response = client.get(reverse("admin_inventory"), HTTP_X_INERTIA="true")
    assert list_response.status_code == 200
    props = inertia_props(list_response)
    assert props["capabilities"]["canManage"] is False

    create_response = client.post(
        reverse("admin_inventory_create"),
        data=json.dumps(
            {
                "name": "Blocked",
                "owner_office": office("fairfax-va").pk,
                "category": ItemCategory.OTHER,
                "tracking_mode": TrackingMode.POOLED,
                "condition": ItemCondition.GOOD,
                "total_quantity": 1,
                "context": "sheet",
            }
        ),
        content_type="application/json",
    )
    assert create_response.status_code == 403


@pytest.mark.django_db
def test_transition_marks_damaged_and_audits(
    client, seeded, django_capture_on_commit_callbacks
):
    item = InventoryItem.objects.create(
        owner_office=office("fairfax-va"),
        name="Projector",
        category=ItemCategory.ELECTRONICS,
        tracking_mode=TrackingMode.SERIALIZED,
        total_quantity=1,
        asset_id="PROJ-1",
        condition=ItemCondition.GOOD,
    )
    client.force_login(manager())
    detail = client.get(
        reverse("admin_inventory_item", args=[item.public_id]),
        HTTP_X_INERTIA="true",
    )
    version = inertia_props(detail)["version"]
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            reverse("admin_inventory_transition", args=[item.public_id]),
            data=json.dumps(
                {
                    "action": "mark_damaged",
                    "expected_version": version,
                    "reason": "Dropped during move",
                }
            ),
            content_type="application/json",
        )
    assert response.status_code == 302
    item.refresh_from_db()
    assert item.availability_state == ItemAvailabilityState.DAMAGED
    assert AuditEvent.objects.filter(action="inventory.item.state_changed").exists()


@pytest.mark.django_db
def test_transfer_moves_item_within_scope(
    client, seeded, django_capture_on_commit_callbacks
):
    item = InventoryItem.objects.create(
        owner_office=office("fairfax-va"),
        name="Rolling cart",
        category=ItemCategory.FURNITURE,
        tracking_mode=TrackingMode.POOLED,
        total_quantity=1,
        condition=ItemCondition.GOOD,
    )
    client.force_login(regional_manager())
    detail = client.get(
        reverse("admin_inventory_item", args=[item.public_id]),
        HTTP_X_INERTIA="true",
    )
    version = inertia_props(detail)["version"]
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            reverse("admin_inventory_transfer", args=[item.public_id]),
            data=json.dumps(
                {
                    "to_office": office("charlottesville-va").pk,
                    "expected_version": version,
                    "reason": "Branch consolidation",
                }
            ),
            content_type="application/json",
        )
    assert response.status_code == 302
    item.refresh_from_db()
    assert item.owner_office.slug == "charlottesville-va"
    assert AuditEvent.objects.filter(action="inventory.item.transferred").exists()


@pytest.mark.django_db
def test_transfer_rejects_out_of_scope_destination(client, seeded):
    item = InventoryItem.objects.create(
        owner_office=office("fairfax-va"),
        name="Desk",
        category=ItemCategory.FURNITURE,
        tracking_mode=TrackingMode.POOLED,
        total_quantity=1,
        condition=ItemCondition.GOOD,
    )
    client.force_login(manager())
    detail = client.get(
        reverse("admin_inventory_item", args=[item.public_id]),
        HTTP_X_INERTIA="true",
    )
    version = inertia_props(detail)["version"]
    response = client.post(
        reverse("admin_inventory_transfer", args=[item.public_id]),
        data=json.dumps(
            {
                "to_office": office("harrisburg").pk,
                "expected_version": version,
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 422
    item.refresh_from_db()
    assert item.owner_office.slug == "fairfax-va"


@pytest.mark.django_db
def test_photo_upload_rejects_invalid_type(client, seeded):
    item = InventoryItem.objects.create(
        owner_office=office("fairfax-va"),
        name="Sign",
        category=ItemCategory.SIGNAGE,
        tracking_mode=TrackingMode.SERIALIZED,
        total_quantity=1,
        asset_id="SIGN-1",
        condition=ItemCondition.GOOD,
    )
    client.force_login(manager())
    detail = client.get(
        reverse("admin_inventory_item", args=[item.public_id]),
        HTTP_X_INERTIA="true",
    )
    version = inertia_props(detail)["version"]
    response = client.post(
        reverse("admin_inventory_photo", args=[item.public_id]),
        data={
            "expected_version": version,
            "photo": SimpleUploadedFile("notes.txt", b"not an image", "text/plain"),
        },
    )
    assert response.status_code == 422
    item.refresh_from_db()
    assert not item.photo


@pytest.mark.django_db
def test_photo_upload_accepts_png(client, seeded, django_capture_on_commit_callbacks):
    item = InventoryItem.objects.create(
        owner_office=office("fairfax-va"),
        name="Banner",
        category=ItemCategory.SIGNAGE,
        tracking_mode=TrackingMode.SERIALIZED,
        total_quantity=1,
        asset_id="BAN-1",
        condition=ItemCondition.GOOD,
    )
    client.force_login(manager())
    detail = client.get(
        reverse("admin_inventory_item", args=[item.public_id]),
        HTTP_X_INERTIA="true",
    )
    version = inertia_props(detail)["version"]
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            reverse("admin_inventory_photo", args=[item.public_id]),
            data={
                "expected_version": version,
                "photo": SimpleUploadedFile("banner.png", _tiny_png(), "image/png"),
            },
        )
    assert response.status_code == 302
    item.refresh_from_db()
    assert item.photo.name.endswith(".png")
    assert AuditEvent.objects.filter(action="inventory.item.updated").exists()


@pytest.mark.django_db
def test_quantity_reduction_blocked_below_committed(client, seeded):
    from datetime import timedelta
    from uuid import uuid4

    from django.utils import timezone

    from apps.inventory.reservations import ActorContext, create_reservation
    from apps.user.tests.test_profile import completed_user

    item = InventoryItem.objects.create(
        owner_office=office("fairfax-va"),
        name="Chairs",
        category=ItemCategory.FURNITURE,
        tracking_mode=TrackingMode.POOLED,
        total_quantity=5,
        condition=ItemCondition.GOOD,
    )
    agent = completed_user(email="agent@example.com", office=office("fairfax-va"))
    today = timezone.localdate()
    pickup = today + timedelta(days=4)
    while pickup.weekday() >= 5:
        pickup += timedelta(days=1)
    return_day = pickup + timedelta(days=1)
    while return_day.weekday() >= 5:
        return_day += timedelta(days=1)
    create_reservation(
        actor=ActorContext(user=agent, permissions=frozenset()),
        item_public_id=str(item.public_id),
        pickup=pickup.isoformat(),
        return_date=return_day.isoformat(),
        quantity=2,
        purpose="",
        submission_key=str(uuid4()),
    )
    client.force_login(manager())
    detail = client.get(
        reverse("admin_inventory_item", args=[item.public_id]),
        HTTP_X_INERTIA="true",
    )
    version = inertia_props(detail)["version"]
    response = client.post(
        reverse("admin_inventory_update", args=[item.public_id]),
        data=json.dumps(
            {
                "name": item.name,
                "category": item.category,
                "condition": item.condition,
                "total_quantity": 1,
                "expected_version": version,
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 422
    item.refresh_from_db()
    assert item.total_quantity == 5


@pytest.mark.django_db
@patch("apps.inventory.services.committed_quantity", return_value=1)
def test_retire_blocked_with_active_commitments(mock_committed, client, seeded):
    item = InventoryItem.objects.create(
        owner_office=office("fairfax-va"),
        name="Tablet",
        category=ItemCategory.ELECTRONICS,
        tracking_mode=TrackingMode.SERIALIZED,
        total_quantity=1,
        asset_id="TAB-1",
        condition=ItemCondition.GOOD,
    )
    client.force_login(manager())
    detail = client.get(
        reverse("admin_inventory_item", args=[item.public_id]),
        HTTP_X_INERTIA="true",
    )
    version = inertia_props(detail)["version"]
    response = client.post(
        reverse("admin_inventory_transition", args=[item.public_id]),
        data=json.dumps(
            {
                "action": "retire",
                "expected_version": version,
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 422
    item.refresh_from_db()
    assert item.availability_state != ItemAvailabilityState.RETIRED
    mock_committed.assert_called()
