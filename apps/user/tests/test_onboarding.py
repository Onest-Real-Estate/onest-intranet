import io
import json
import re

import pytest
from django.urls import reverse
from PIL import Image

from apps.user.models import Office, User

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def inertia_page_script(response):
    match = re.search(
        rb'<script data-page="app" type="application/json">(.*?)</script>',
        response.content,
        re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def assignable_office():
    return Office.objects.get(slug="charlottesville-va")


def valid_profile_post(**overrides):
    data = {
        "first_name": "Bob",
        "last_name": "Lee",
        "phone_number": "2025550100",
        "street_address": "1 Main St",
        "city": "Fairfax",
        "state": "VA",
        "zip_code": "22030",
        "office": str(assignable_office().pk),
        "mls_number": "",
        "nrds_number": "",
    }
    data.update(overrides)
    return data


def make_image(fmt="JPEG", size=(300, 300)) -> io.BytesIO:
    """Create an in-memory image file for upload tests."""
    buf = io.BytesIO()
    img = Image.new("RGB", size, color=(255, 100, 50))
    img.save(buf, format=fmt)
    buf.name = "photo.jpg" if fmt == "JPEG" else "photo.png"
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Basic flow
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_onboarding_requires_login(client):
    response = client.get(reverse("onboarding"))
    assert response.status_code == 302
    assert response.url == f"{reverse('login')}?next=/onboarding"


@pytest.mark.django_db
def test_onboarding_renders_page_with_initial_values(client):
    user = User.objects.create_user(
        email="bob@example.com",
        first_name="Bob",
        last_name="Lee",
        phone_number="(202) 555-0100",
    )
    client.force_login(user)
    response = client.get(reverse("onboarding"), HTTP_X_INERTIA="true")
    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["component"] == "Onboarding"
    assert data["props"]["initial"]["firstName"] == "Bob"
    assert data["props"]["initial"]["lastName"] == "Lee"
    assert data["props"]["initial"]["phoneNumber"] == "(202) 555-0100"
    assert data["props"]["errors"] == {}
    group_labels = [group["label"] for group in data["props"]["offices"]]
    assert "Mid-Atlantic" in group_labels
    assert any(state["code"] == "VA" for state in data["props"]["states"])


@pytest.mark.django_db
def test_completed_profile_redirects_from_onboarding(client):
    user = User.objects.create_user(email="bob@example.com", profile_completed=True)
    client.force_login(user)
    response = client.get(reverse("onboarding"))
    assert response.status_code == 302
    assert response.url == reverse("dashboard")


@pytest.mark.django_db
def test_onboarding_submit_saves_details_and_completes(client):
    user = User.objects.create_user(email="bob@example.com")
    client.force_login(user)
    response = client.post(reverse("onboarding_submit"), valid_profile_post())
    assert response.status_code == 302
    assert response.url == reverse("dashboard")
    user.refresh_from_db()
    assert user.first_name == "Bob"
    assert user.last_name == "Lee"
    assert user.display_name == "Bob Lee"
    assert user.phone_number == "(202) 555-0100"
    assert user.street_address == "1 Main St"
    assert user.city == "Fairfax"
    assert user.state == "VA"
    assert user.zip_code == "22030"
    assert user.office == assignable_office()
    assert user.profile_completed is True
    assert user.profile_completed_at is not None


@pytest.mark.django_db
def test_onboarding_accepts_optional_mls_and_nrds(client):
    user = User.objects.create_user(email="bob@example.com")
    client.force_login(user)
    client.post(
        reverse("onboarding_submit"),
        valid_profile_post(mls_number="ABC123", nrds_number="123456789"),
    )
    user.refresh_from_db()
    assert user.mls_number == "ABC123"
    assert user.nrds_number == "123456789"


@pytest.mark.django_db
def test_onboarding_submit_rerenders_with_errors(client):
    user = User.objects.create_user(email="bob@example.com")
    client.force_login(user)
    response = client.post(reverse("onboarding_submit"), {"first_name": ""})
    assert response.status_code == 422
    data = inertia_page_script(response)
    assert data["component"] == "Onboarding"
    assert "first_name" in data["props"]["errors"]
    user.refresh_from_db()
    assert user.profile_completed is False


@pytest.mark.django_db
def test_onboarding_submit_rerenders_with_errors_for_inertia(client):
    user = User.objects.create_user(email="bob@example.com")
    client.force_login(user)
    response = client.post(
        reverse("onboarding_submit"),
        {"first_name": ""},
        HTTP_X_INERTIA="true",
    )
    assert response.status_code == 422
    data = json.loads(response.content)
    assert "first_name" in data["props"]["errors"]
    assert data["props"]["initial"]["firstName"] == ""


@pytest.mark.django_db
def test_onboarding_rejects_invalid_us_phone(client):
    user = User.objects.create_user(email="bob@example.com")
    client.force_login(user)
    response = client.post(
        reverse("onboarding_submit"),
        valid_profile_post(phone_number="123"),
        HTTP_X_INERTIA="true",
    )
    assert response.status_code == 422
    data = json.loads(response.content)
    assert "phone_number" in data["props"]["errors"]


# ---------------------------------------------------------------------------
# Office constraints
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_onboarding_rejects_region_as_office(client):
    user = User.objects.create_user(email="bob@example.com")
    client.force_login(user)
    region = Office.objects.get(slug="region-mid-atlantic")
    response = client.post(
        reverse("onboarding_submit"),
        valid_profile_post(office=str(region.pk)),
        HTTP_X_INERTIA="true",
    )
    assert response.status_code == 422
    data = json.loads(response.content)
    assert "office" in data["props"]["errors"]


@pytest.mark.django_db
def test_onboarding_rejects_inactive_office(client):
    """Office that becomes inactive between form load and submit is rejected."""
    user = User.objects.create_user(email="bob@example.com")
    client.force_login(user)
    office = assignable_office()
    office.is_active = False
    office.save()
    response = client.post(
        reverse("onboarding_submit"),
        valid_profile_post(office=str(office.pk)),
        HTTP_X_INERTIA="true",
    )
    assert response.status_code == 422
    data = json.loads(response.content)
    assert "office" in data["props"]["errors"]


@pytest.mark.django_db
def test_onboarding_rejects_unknown_office_id(client):
    user = User.objects.create_user(email="bob@example.com")
    client.force_login(user)
    response = client.post(
        reverse("onboarding_submit"),
        valid_profile_post(office="999999"),
        HTTP_X_INERTIA="true",
    )
    assert response.status_code == 422
    data = json.loads(response.content)
    assert "office" in data["props"]["errors"]


# ---------------------------------------------------------------------------
# Idempotency / double submit
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_completed_user_submit_redirects_without_error(client):
    """Submitting onboarding a second time just redirects — no crash or duplicate."""
    user = User.objects.create_user(email="bob@example.com", profile_completed=True)
    client.force_login(user)
    response = client.post(reverse("onboarding_submit"), valid_profile_post())
    assert response.status_code == 302
    assert response.url == reverse("dashboard")


# ---------------------------------------------------------------------------
# Mass-assignment protection
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_onboarding_cannot_set_is_staff(client):
    user = User.objects.create_user(email="bob@example.com", is_staff=False)
    client.force_login(user)
    post = valid_profile_post()
    post["is_staff"] = "true"
    response = client.post(reverse("onboarding_submit"), post)
    assert response.status_code == 403
    user.refresh_from_db()
    assert user.is_staff is False


@pytest.mark.django_db
def test_onboarding_cannot_set_is_superuser(client):
    user = User.objects.create_user(email="bob@example.com")
    client.force_login(user)
    post = valid_profile_post()
    post["is_superuser"] = "true"
    response = client.post(reverse("onboarding_submit"), post)
    assert response.status_code == 403
    user.refresh_from_db()
    assert user.is_superuser is False


@pytest.mark.django_db
def test_onboarding_cannot_set_profile_completed_directly(client):
    user = User.objects.create_user(email="bob@example.com")
    client.force_login(user)
    post = valid_profile_post()
    post["profile_completed"] = "true"
    response = client.post(reverse("onboarding_submit"), post)
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Authorization: one user cannot edit another
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_onboarding_submit_acts_on_authenticated_user_only(client):
    """The submit always operates on the logged-in user, not any other user."""
    alice = User.objects.create_user(email="alice@example.com")
    bob = User.objects.create_user(email="bob@example.com")
    client.force_login(alice)
    # Even if Bob's PK is somehow in the payload, Alice's session is what matters.
    client.post(reverse("onboarding_submit"), valid_profile_post())
    alice.refresh_from_db()
    bob.refresh_from_db()
    assert alice.profile_completed is True
    assert bob.profile_completed is False


# ---------------------------------------------------------------------------
# Completion timestamp and version
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_onboarding_sets_completed_at(client):
    user = User.objects.create_user(email="bob@example.com")
    client.force_login(user)
    client.post(reverse("onboarding_submit"), valid_profile_post())
    user.refresh_from_db()
    assert user.profile_completed_at is not None


@pytest.mark.django_db
def test_admin_reset_clears_completion(client):
    """Admin reset_onboarding action clears profile_completed and completed_at."""
    user = User.objects.create_user(
        email="bob@example.com",
        profile_completed=True,
        is_staff=False,
    )
    from django.utils import timezone

    user.profile_completed_at = timezone.now()
    user.save()
    initial_version = user.onboarding_version

    from django.test import RequestFactory

    from apps.user.admin import UserAdmin

    admin_instance = UserAdmin(User, None)
    qs = User.objects.filter(pk=user.pk)
    request = RequestFactory().get("/")
    request.user = User.objects.create_superuser(
        email="admin@example.com", password="x"
    )
    from django.contrib.messages.storage.cookie import CookieStorage

    request._messages = CookieStorage(request)  # ty: ignore[unresolved-attribute]
    admin_instance.reset_onboarding(request, qs)
    user.refresh_from_db()
    assert user.profile_completed is False
    assert user.profile_completed_at is None
    assert user.onboarding_version == initial_version + 1


# ---------------------------------------------------------------------------
# Headshot upload endpoint
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_headshot_upload_requires_login(client):
    response = client.post(reverse("headshot_upload"))
    assert response.status_code == 401
    data = json.loads(response.content)
    assert data["error"] == "authentication_required"


@pytest.mark.django_db
def test_headshot_upload_rejects_missing_file(client):
    user = User.objects.create_user(email="bob@example.com")
    client.force_login(user)
    response = client.post(reverse("headshot_upload"), {})
    assert response.status_code == 400


@pytest.mark.django_db
def test_headshot_upload_accepts_valid_jpeg(client, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    user = User.objects.create_user(email="bob@example.com")
    client.force_login(user)
    img = make_image("JPEG", (300, 300))
    img.name = "photo.jpg"
    response = client.post(
        reverse("headshot_upload"),
        {"headshot": img},
        format="multipart",
    )
    assert response.status_code == 200
    data = json.loads(response.content)
    assert "url" in data


@pytest.mark.django_db
def test_headshot_upload_rejects_tiny_image(client, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    user = User.objects.create_user(email="bob@example.com")
    client.force_login(user)
    img = make_image("JPEG", (50, 50))
    img.name = "tiny.jpg"
    response = client.post(
        reverse("headshot_upload"),
        {"headshot": img},
        format="multipart",
    )
    assert response.status_code == 422
    data = json.loads(response.content)
    assert "error" in data


@pytest.mark.django_db
def test_headshot_upload_rejects_oversized_file(client, settings, tmp_path):
    """Files over 5 MB must be rejected."""
    settings.MEDIA_ROOT = str(tmp_path)
    user = User.objects.create_user(email="bob@example.com")
    client.force_login(user)

    from django.core.exceptions import ValidationError
    from django.core.files.uploadedfile import InMemoryUploadedFile

    from apps.user.headshot import MAX_BYTES, validate_headshot

    data = io.BytesIO(b"0" * (MAX_BYTES + 1))
    upload = InMemoryUploadedFile(
        data, "headshot", "big.jpg", "image/jpeg", MAX_BYTES + 1, None
    )
    with pytest.raises(ValidationError, match="5 MB"):
        validate_headshot(upload)


@pytest.mark.django_db
def test_headshot_upload_rejects_non_image(client, settings, tmp_path):
    """Plain text or HTML masquerading as an image must be rejected."""
    settings.MEDIA_ROOT = str(tmp_path)
    user = User.objects.create_user(email="bob@example.com")
    client.force_login(user)
    buf = io.BytesIO(b"<html><body>not an image</body></html>")
    buf.name = "evil.jpg"
    response = client.post(
        reverse("headshot_upload"),
        {"headshot": buf},
        format="multipart",
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# ProfileCompletionMiddleware gate
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_incomplete_profile_redirected_to_onboarding(client):
    user = User.objects.create_user(email="bob@example.com")
    client.force_login(user)
    response = client.get(reverse("dashboard"))
    assert response.status_code == 302
    assert response.url == reverse("onboarding")


@pytest.mark.django_db
def test_incomplete_profile_cannot_open_profile_page(client):
    user = User.objects.create_user(email="bob@example.com")
    client.force_login(user)
    response = client.get(reverse("profile"))
    assert response.status_code == 302
    assert response.url == reverse("onboarding")


@pytest.mark.django_db
def test_complete_profile_not_redirected(client):
    user = User.objects.create_user(email="bob@example.com", profile_completed=True)
    client.force_login(user)
    response = client.get(reverse("dashboard"))
    assert response.status_code == 200


@pytest.mark.django_db
def test_anonymous_not_redirected_to_onboarding(client):
    response = client.get(reverse("dashboard"))
    assert response.status_code == 302
    assert response.url == f"{reverse('login')}?next=/dashboard"


@pytest.mark.django_db
def test_staff_not_redirected_to_onboarding(client):
    user = User.objects.create_user(email="admin@example.com", is_staff=True)
    client.force_login(user)
    response = client.get(reverse("dashboard"))
    assert response.status_code == 200


@pytest.mark.django_db
def test_logout_not_blocked_by_middleware(client):
    user = User.objects.create_user(email="bob@example.com")
    client.force_login(user)
    response = client.post(reverse("logout"))
    assert response.status_code == 302
    assert response.url == reverse("login")
