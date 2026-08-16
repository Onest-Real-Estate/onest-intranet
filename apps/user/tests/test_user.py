import pytest
from django.db import IntegrityError

from apps.user.models import User


@pytest.mark.django_db
def test_create_user():
    user = User.objects.create_user(email="jane@example.com", password="secret")
    assert user.email == "jane@example.com"
    assert not user.is_staff
    assert not user.is_superuser


@pytest.mark.django_db
def test_create_user_normalizes_email():
    # normalize_email keeps the local part as-is and lowercases the domain.
    user = User.objects.create_user(email="JANE@Example.COM")
    assert user.email == "JANE@example.com"


@pytest.mark.django_db
def test_create_user_requires_email():
    with pytest.raises(ValueError):
        User.objects.create_user(email="", password="secret")


@pytest.mark.django_db
def test_create_superuser():
    user = User.objects.create_superuser(email="root@example.com", password="secret")
    assert user.is_staff
    assert user.is_superuser


@pytest.mark.django_db
def test_create_superuser_enforces_staff_and_superuser():
    with pytest.raises(ValueError):
        User.objects.create_superuser(
            email="root@example.com", password="secret", is_staff=False
        )
    with pytest.raises(ValueError):
        User.objects.create_superuser(
            email="root@example.com", password="secret", is_superuser=False
        )


@pytest.mark.django_db
def test_display_name_defaults_to_blank():
    user = User.objects.create_user(email="jane@example.com")
    assert user.display_name == ""


@pytest.mark.django_db
def test_email_is_unique():
    User.objects.create_user(email="jane@example.com")
    with pytest.raises(IntegrityError):
        User.objects.create_user(email="jane@example.com")


@pytest.mark.django_db
def test_str_uses_display_name_or_email():
    user = User.objects.create_user(email="jane@example.com")
    assert str(user) == "jane@example.com"
    user.display_name = "Jane Doe"
    assert str(user) == "Jane Doe"
