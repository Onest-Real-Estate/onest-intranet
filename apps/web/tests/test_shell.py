from dataclasses import replace

from django.test import override_settings

from apps.user.services.role_assignments import EffectiveAccess
from apps.web.shell import authorization_version, help_configuration


def access(**overrides):
    base = EffectiveAccess(
        assignments=(),
        role_keys=("Users",),
        permissions=frozenset({"web.view_dashboard"}),
        region_keys=frozenset(),
        office_keys=frozenset({"cedar-ridge"}),
        company_wide=False,
    )
    return replace(base, **overrides)


@override_settings(HUB_HELP_URL="https://help.onest.realestate/hub")
def test_help_configuration_accepts_configured_https_url():
    assert help_configuration() == {"url": "https://help.onest.realestate/hub"}


@override_settings(HUB_HELP_URL="javascript:alert(1)")
def test_help_configuration_fails_closed_for_unsafe_url():
    assert help_configuration() == {"url": None}


@override_settings(HUB_HELP_URL="https://user:secret@help.example.com")
def test_help_configuration_rejects_credential_bearing_url():
    assert help_configuration() == {"url": None}


def test_authorization_version_is_stable_and_changes_with_effective_access():
    original = access()
    assert authorization_version(original) == authorization_version(original)
    assert authorization_version(original) != authorization_version(
        access(permissions=frozenset())
    )
    assert authorization_version(original) != authorization_version(
        access(office_keys=frozenset({"another-office"}))
    )
