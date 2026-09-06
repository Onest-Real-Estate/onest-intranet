"""Agent Office Inventory browser HTTP and payload tests."""

from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.inventory.browser import (
    build_agent_inventory_page,
    parse_agent_filters,
    parse_availability_interval,
)
from apps.inventory.models import InventoryItem
from apps.inventory.taxonomy import (
    ItemAvailabilityState,
    ItemCategory,
    ItemCondition,
    TrackingMode,
)
from apps.user.models import Office, UserRoleAssignment
from apps.user.tests.test_profile import completed_user


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


def agent(email: str = "agent@example.com", slug: str = "fairfax-va"):
    return completed_user(email=email, office=office(slug))


def make_item(
    owner_slug: str,
    name: str,
    *,
    state=ItemAvailabilityState.AVAILABLE,
    category=ItemCategory.OTHER,
    condition=ItemCondition.GOOD,
    tracking=TrackingMode.POOLED,
    quantity=3,
    asset_id="",
    **extra,
):
    kwargs = {
        "owner_office": office(owner_slug),
        "name": name,
        "category": category,
        "tracking_mode": tracking,
        "condition": condition,
        "availability_state": state,
        **extra,
    }
    if tracking == TrackingMode.SERIALIZED:
        kwargs["asset_id"] = asset_id or f"AST-{name[:8]}"
        kwargs["total_quantity"] = 1
    else:
        kwargs["total_quantity"] = quantity
    return InventoryItem.objects.create(**kwargs)


def inertia_props(response) -> dict:
    return json.loads(response.content)["props"]


def inertia_component(response) -> str:
    return json.loads(response.content)["component"]


@pytest.mark.django_db
def test_browser_requires_authentication(client, seeded):
    response = client.get(reverse("office_inventory"))
    assert response.status_code in {302, 401, 403}


@pytest.mark.django_db
def test_agent_sees_only_own_office_reservable_items(client, seeded):
    make_item("fairfax-va", "Fairfax kit")
    make_item("harrisburg", "Harrisburg kit")
    make_item("fairfax-va", "Damaged kit", state=ItemAvailabilityState.DAMAGED)
    user = agent()
    client.force_login(user)
    response = client.get(reverse("office_inventory"), HTTP_X_INERTIA="true")
    assert response.status_code == 200
    assert inertia_component(response) == "OfficeInventory"
    props = inertia_props(response)
    names = {row["name"] for row in props["items"]["items"]}
    assert names == {"Fairfax kit"}
    assert props["office"]["name"] == office("fairfax-va").name


@pytest.mark.django_db
def test_no_office_empty_state(client, seeded):
    user = completed_user(email="homeless@example.com", office=None)
    client.force_login(user)
    response = client.get(reverse("office_inventory"), HTTP_X_INERTIA="true")
    props = inertia_props(response)
    assert props["empty"]["kind"] == "no-office"
    assert props["items"]["items"] == []


@pytest.mark.django_db
def test_filters_category_condition_and_search(client, seeded):
    make_item(
        "fairfax-va",
        "Blue sign",
        category=ItemCategory.SIGNAGE,
        condition=ItemCondition.EXCELLENT,
    )
    make_item(
        "fairfax-va",
        "Desk lamp",
        category=ItemCategory.ELECTRONICS,
        condition=ItemCondition.FAIR,
    )
    client.force_login(agent())
    response = client.get(
        reverse("office_inventory"),
        {
            "q": "sign",
            "category": ItemCategory.SIGNAGE,
            "condition": ItemCondition.EXCELLENT,
        },
        HTTP_X_INERTIA="true",
    )
    props = inertia_props(response)
    names = {row["name"] for row in props["items"]["items"]}
    assert names == {"Blue sign"}


@pytest.mark.django_db
def test_asset_id_search_requires_sensitive_grant(client, seeded):
    make_item(
        "fairfax-va",
        "Camera",
        tracking=TrackingMode.SERIALIZED,
        asset_id="CAM-99",
    )
    user = agent()
    client.force_login(user)
    response = client.get(
        reverse("office_inventory"),
        {"q": "CAM-99"},
        HTTP_X_INERTIA="true",
    )
    assert inertia_props(response)["items"]["items"] == []

    from django.contrib.auth.models import Permission

    user.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="inventory",
            codename="view_inventory_sensitive",
        )
    )
    response = client.get(
        reverse("office_inventory"),
        {"q": "CAM-99"},
        HTTP_X_INERTIA="true",
    )
    names = {row["name"] for row in inertia_props(response)["items"]["items"]}
    assert names == {"Camera"}
    row = inertia_props(response)["items"]["items"][0]
    assert row["assetId"] == "CAM-99"


@pytest.mark.django_db
def test_agent_payload_omits_private_fields(client, seeded):
    item = make_item(
        "fairfax-va",
        "Laptop",
        tracking=TrackingMode.SERIALIZED,
        asset_id="LAP-1",
    )
    InventoryItem.objects.filter(pk=item.pk).update(
        serial_number="SN-SECRET",
        internal_notes="Insurance rider",
        replacement_value=Decimal("1200.00"),
        notes="Pick up at front desk",
        storage_location="Cabinet A",
    )
    client.force_login(agent())
    response = client.get(reverse("office_inventory"), HTTP_X_INERTIA="true")
    row = inertia_props(response)["items"]["items"][0]
    assert "replacementValue" not in row
    assert "internalNotes" not in row
    assert "serialNumber" not in row
    assert "assetId" not in row
    assert row["notes"] == "Pick up at front desk"
    assert row["storageLocation"] == "Cabinet A"


@pytest.mark.django_db
def test_availability_for_valid_date_range(client, seeded):
    make_item("fairfax-va", "Signs", quantity=5)
    pickup = timezone.localdate().isoformat()
    ret = (timezone.localdate() + timedelta(days=2)).isoformat()
    client.force_login(agent())
    response = client.get(
        reverse("office_inventory"),
        {"pickup": pickup, "return": ret, "quantity": "2"},
        HTTP_X_INERTIA="true",
    )
    props = inertia_props(response)
    assert props["dateErrors"] == []
    availability = props["items"]["items"][0]["availability"]
    assert availability["isAvailable"] is True
    assert availability["availableQuantity"] == 5
    assert availability["requestedQuantity"] == 2
    assert "reasonLabel" in availability


@pytest.mark.django_db
def test_invalid_date_range_reports_errors(client, seeded):
    make_item("fairfax-va", "Signs")
    client.force_login(agent())
    response = client.get(
        reverse("office_inventory"),
        {"pickup": "2026-05-10", "return": "2026-05-01"},
        HTTP_X_INERTIA="true",
    )
    props = inertia_props(response)
    assert props["dateErrors"]
    assert props["items"]["items"][0]["availability"] is None


@pytest.mark.django_db
def test_detail_hides_other_office_item(client, seeded):
    foreign = make_item("harrisburg", "Foreign chair")
    client.force_login(agent())
    response = client.get(
        reverse("office_inventory_item", args=[foreign.public_id]),
        HTTP_X_INERTIA="true",
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_detail_returns_scoped_item(client, seeded):
    item = make_item("fairfax-va", "Office chair")
    client.force_login(agent())
    response = client.get(
        reverse("office_inventory_item", args=[item.public_id]),
        HTTP_X_INERTIA="true",
    )
    assert response.status_code == 200
    assert inertia_component(response) == "OfficeInventoryItem"
    props = inertia_props(response)
    assert props["item"]["name"] == "Office chair"
    assert "replacementValue" not in props["item"]
    assert props["item"]["reserveHref"]


@pytest.mark.django_db
def test_retired_item_is_not_reachable(client, seeded):
    item = make_item("fairfax-va", "Retired")
    InventoryItem.objects.filter(pk=item.pk).update(
        availability_state=ItemAvailabilityState.RETIRED,
        retired_at=timezone.now(),
    )
    client.force_login(agent())
    response = client.get(
        reverse("office_inventory_item", args=[item.public_id]),
        HTTP_X_INERTIA="true",
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_photo_requires_public_flag_and_office_scope(client, seeded):
    item = make_item("fairfax-va", "Banner")
    item.photo.save(
        "banner.png",
        SimpleUploadedFile("banner.png", _tiny_png(), content_type="image/png"),
        save=True,
    )
    item.photo_is_public = False
    item.save(update_fields=["photo_is_public"])

    client.force_login(agent())
    response = client.get(reverse("office_inventory_photo", args=[item.public_id]))
    assert response.status_code == 404

    item.photo_is_public = True
    item.save(update_fields=["photo_is_public"])
    response = client.get(reverse("office_inventory_photo", args=[item.public_id]))
    assert response.status_code == 200
    assert response["Cache-Control"] == "private, max-age=0, no-store"


@pytest.mark.django_db
def test_foreign_office_photo_is_404(client, seeded):
    item = make_item("harrisburg", "Banner")
    item.photo.save(
        "banner.png",
        SimpleUploadedFile("banner.png", _tiny_png(), content_type="image/png"),
        save=True,
    )
    item.photo_is_public = True
    item.save(update_fields=["photo_is_public"])
    client.force_login(agent())
    response = client.get(reverse("office_inventory_photo", args=[item.public_id]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_unavailable_range_filter_empty_state(client, seeded):
    make_item("fairfax-va", "Signs", quantity=1)
    pickup = timezone.localdate().isoformat()
    ret = (timezone.localdate() + timedelta(days=1)).isoformat()

    with patch(
        "apps.inventory.availability.available_quantity_for_range",
        return_value=0,
    ):
        client.force_login(agent())
        response = client.get(
            reverse("office_inventory"),
            {
                "pickup": pickup,
                "return": ret,
                "available_only": "1",
                "quantity": "1",
            },
            HTTP_X_INERTIA="true",
        )
    props = inertia_props(response)
    assert props["empty"]["kind"] == "unavailable-range"
    assert props["items"]["items"] == []


@pytest.mark.django_db
def test_pagination_is_stable(client, seeded):
    for index in range(30):
        make_item("fairfax-va", f"Item {index:02d}")
    client.force_login(agent())
    response = client.get(
        reverse("office_inventory"),
        {"page": "2"},
        HTTP_X_INERTIA="true",
    )
    props = inertia_props(response)
    assert props["items"]["pagination"]["page"] == 2
    assert props["items"]["pagination"]["hasPrevious"] is True
    assert len(props["items"]["items"]) == 6


@pytest.mark.django_db
def test_list_query_count_is_bounded(client, seeded):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    for index in range(5):
        make_item("fairfax-va", f"Item {index}")
    client.force_login(agent())
    with CaptureQueriesContext(connection) as captured:
        response = client.get(reverse("office_inventory"), HTTP_X_INERTIA="true")
    assert response.status_code == 200
    assert len(captured) <= 20


def test_parse_availability_interval_same_day():
    interval, errors = parse_availability_interval("2026-03-01", "2026-03-01")
    assert errors == []
    assert interval is not None
    assert interval.end > interval.start


def test_parse_agent_filters_rejects_unknown_codes():
    filters = parse_agent_filters(
        {"category": "nope", "condition": "nope", "view": "masonry", "quantity": "0"}
    )
    assert filters.category == ""
    assert filters.condition == ""
    assert filters.view == "grid"
    assert filters.quantity == 1


@pytest.mark.django_db
def test_build_page_for_manager_still_uses_primary_office(seeded):
    """Administrative grants do not widen the agent browser."""
    make_item("fairfax-va", "Fairfax")
    make_item("harrisburg", "Harrisburg")
    user = agent()
    assignment = UserRoleAssignment(
        user=user,
        role="branch_manager",
        scope_type="office",
        scope_office=office("fairfax-va"),
    )
    assignment.refresh_status()
    assignment.save()
    from django.contrib.auth.models import Permission

    user.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="web",
            codename="view_inventory",
        )
    )
    payload = build_agent_inventory_page(user, filters=parse_agent_filters({}))
    names = {row["name"] for row in payload["items"]["items"]}
    assert names == {"Fairfax"}
