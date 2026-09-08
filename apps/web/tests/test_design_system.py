import json

import pytest
from django.urls import reverse

from apps.user.models import User


@pytest.mark.django_db
def test_design_system_requires_login(client):
    response = client.get(reverse("design_system"))
    assert response.status_code == 302


@pytest.mark.django_db
def test_design_system_uses_list_contract_and_filters_authorized_payload(client):
    user = User.objects.create_user(email="catalog@example.com", profile_completed=True)
    client.force_login(user)

    response = client.get(
        reverse("design_system"),
        {"q": "Avery", "status": "pending_signature"},
        HTTP_X_INERTIA="true",
    )

    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["component"] == "DesignSystem"
    contracts = data["props"]["contracts"]
    assert contracts["filters"] == {
        "q": "Avery",
        "status": "pending_signature",
    }
    assert [item["id"] for item in contracts["items"]] == ["ON-1048"]
    assert contracts["pagination"]["totalItems"] == 1
