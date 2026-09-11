"""Microsoft SSO: linking a sign-in to an account that already has its email."""

import copy

import pytest
from allauth.account.models import EmailAddress
from allauth.core import context
from allauth.socialaccount.adapter import get_adapter
from allauth.socialaccount.helpers import complete_social_login
from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from apps.user.models import User

GRAPH_PROFILE = {
    "id": "entra-object-id-1",
    "mail": "support@onest.realestate",
    "userPrincipalName": "support@onest.realestate",
    "givenName": "Support",
    "surname": "Team",
    "displayName": "Support Team",
}


def providers(*, verified_email: bool) -> dict:
    configured = copy.deepcopy(settings.SOCIALACCOUNT_PROVIDERS)
    configured["microsoft"]["VERIFIED_EMAIL"] = verified_email
    return configured


def sign_in_with_microsoft(profile: dict = GRAPH_PROFILE):
    """Run the real provider parsing and login completion for a Graph profile."""
    request = RequestFactory().get("/accounts/microsoft/login/callback/")
    SessionMiddleware(lambda _request: HttpResponse()).process_request(request)
    MessageMiddleware(lambda _request: HttpResponse()).process_request(request)
    request.user = AnonymousUser()
    # allauth's middleware normally publishes the request to its adapters.
    with context.request_context(request):
        provider = get_adapter().get_provider(request, "microsoft")
        login = provider.sociallogin_from_response(request, profile)
        return request, complete_social_login(request, login)


@pytest.mark.parametrize(
    ("tenant", "trusted"),
    [
        ("common", False),
        ("organizations", False),
        ("consumers", False),
        ("0b8e1c1f-4a52-4e0f-9f0b-2f3c6a1d9e77", True),
    ],
)
def test_only_a_single_tenant_authority_vouches_for_microsoft_emails(tenant, trusted):
    assert (tenant not in settings.MICROSOFT_MULTI_TENANT_AUTHORITIES) is trusted
    assert settings.SOCIALACCOUNT_PROVIDERS["microsoft"]["VERIFIED_EMAIL"] is (
        settings.MICROSOFT_TENANT not in settings.MICROSOFT_MULTI_TENANT_AUTHORITIES
    )


@pytest.mark.django_db
def test_verified_sign_in_links_the_existing_account_instead_of_asking_again():
    existing = User.objects.create_user(email="support@onest.realestate")
    EmailAddress.objects.create(
        user=existing, email=existing.email, verified=False, primary=False
    )

    with override_settings(SOCIALACCOUNT_PROVIDERS=providers(verified_email=True)):
        request, response = sign_in_with_microsoft()

    assert "signup" not in response.get("Location", "")
    assert request.user.pk == existing.pk
    assert User.objects.filter(email__iexact="support@onest.realestate").count() == 1
    account = SocialAccount.objects.get(provider="microsoft")
    assert account.user.pk == existing.pk
    assert account.uid == "entra-object-id-1"


@pytest.mark.django_db
def test_unverified_sign_in_never_takes_over_an_existing_account():
    existing = User.objects.create_user(email="support@onest.realestate")

    with override_settings(SOCIALACCOUNT_PROVIDERS=providers(verified_email=False)):
        request, _response = sign_in_with_microsoft()

    assert request.user.is_authenticated is False
    assert not SocialAccount.objects.filter(user=existing).exists()


@pytest.mark.django_db
def test_verified_sign_in_for_a_new_email_still_creates_an_account():
    with override_settings(SOCIALACCOUNT_PROVIDERS=providers(verified_email=True)):
        request, _response = sign_in_with_microsoft(
            {
                **GRAPH_PROFILE,
                "id": "entra-object-id-2",
                "mail": "new.agent@onest.realestate",
            }
        )

    created = User.objects.get(email="new.agent@onest.realestate")
    assert request.user.pk == created.pk
    assert SocialAccount.objects.filter(user=created, provider="microsoft").exists()
