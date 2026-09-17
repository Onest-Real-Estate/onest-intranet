import io
import json
import re

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from PIL import Image

from apps.user.models import Office, User
from apps.user.roles import AGENT, role_group_name

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


def make_agent(user):
    group, _created = Group.objects.get_or_create(name=role_group_name(AGENT))
    user.groups.add(group)
    return user


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
def test_onboarding_link_opens_the_dashboard_dialog_with_initial_values(client):
    user = make_agent(
        User.objects.create_user(
            email="bob@example.com",
            first_name="Bob",
            last_name="Lee",
            phone_number="(202) 555-0100",
        )
    )
    client.force_login(user)
    response = client.get(reverse("onboarding"))
    assert response.status_code == 302
    assert response.url == f"{reverse('dashboard')}?onboarding=open"

    response = client.get(response.url, HTTP_X_INERTIA="true")
    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["component"] == "Dashboard"
    setup = data["props"]["onboardingProfile"]
    assert setup["initial"]["firstName"] == "Bob"
    assert setup["initial"]["lastName"] == "Lee"
    assert setup["initial"]["phoneNumber"] == "(202) 555-0100"
    assert setup["validation"] == {"fields": {}, "form": []}
    group_labels = [group["label"] for group in setup["offices"]]
    assert "Mid-Atlantic" in group_labels
    assert any(state["code"] == "VA" for state in setup["states"])


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("?section=contact", "?onboarding=open&section=contact"),
        ("?section=../admin", "?onboarding=open"),
        ("", "?onboarding=open"),
    ],
)
def test_onboarding_link_keeps_only_a_valid_section(client, query, expected):
    client.force_login(make_agent(User.objects.create_user(email="bob@example.com")))
    response = client.get(f"{reverse('onboarding')}{query}")
    assert response.status_code == 302
    assert response.url == f"{reverse('dashboard')}{expected}"


@pytest.mark.django_db
def test_completed_agent_onboarding_link_opens_the_activation_center(client):
    user = make_agent(
        User.objects.create_user(email="bob@example.com", profile_completed=True)
    )
    client.force_login(user)
    response = client.get(f"{reverse('onboarding')}?section=contact")
    assert response.status_code == 302
    assert response.url == f"{reverse('dashboard')}?onboarding=open"


@pytest.mark.django_db
def test_incomplete_non_agent_onboarding_link_goes_to_their_profile(client):
    client.force_login(User.objects.create_user(email="operations@example.com"))
    response = client.get(reverse("onboarding"))
    assert response.status_code == 302
    assert response.url == reverse("profile")


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
    assert data["url"].startswith("http://testserver/account/headshot/file?v=")
    assert "headshots/" not in data["url"]


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
def test_incomplete_agent_loads_dashboard_shell_with_strict_gate(client):
    user = make_agent(
        User.objects.create_user(
            email="bob@example.com",
            phone_number="2025550199",
            street_address="41 Private Lane",
        )
    )
    client.force_login(user)
    response = client.get(reverse("dashboard"))
    assert response.status_code == 200
    page = inertia_page_script(response)
    assert "deferredProps" not in page
    props = page["props"]
    assert props["onboardingJourney"]["strictGateActive"] is True
    assert props["onboardingJourney"]["currentStep"]["code"] == "profile"
    assert props["features"] == {}
    assert props["primaryOffice"] is None
    assert props["notifications"] is None
    protected_widget_keys = {
        "metrics",
        "quickApps",
        "announcements",
        "transactions",
        "training",
        "schedule",
        "actionItems",
        "agentOnboarding",
        "contractsAwaitingSignature",
    }
    assert protected_widget_keys.isdisjoint(props)
    # The agent's own values reach them only inside their own setup form.
    assert "41 Private Lane" in json.dumps(props["onboardingProfile"])
    shell = {key: value for key, value in props.items() if key != "onboardingProfile"}
    serialized = json.dumps(shell)
    assert "2025550199" not in serialized
    assert "41 Private Lane" not in serialized


@pytest.mark.django_db
def test_incomplete_profile_cannot_open_profile_page(client):
    user = make_agent(User.objects.create_user(email="bob@example.com"))
    client.force_login(user)
    response = client.get(reverse("profile"))
    assert response.status_code == 302
    assert response.url == reverse("dashboard")


@pytest.mark.django_db
def test_incomplete_non_agent_is_not_forced_into_agent_journey(client):
    user = User.objects.create_user(email="operations@example.com")
    client.force_login(user)
    response = client.get(reverse("profile"))
    assert response.status_code == 200


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
