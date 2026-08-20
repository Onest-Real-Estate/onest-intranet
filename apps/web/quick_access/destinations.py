"""Destination validation — the only place a link's target is judged safe.

Two shapes are allowed and nothing else:

* an **external** ``https://`` URL with a hostname and no embedded
  credentials. ``http://`` is refused rather than upgraded, because silently
  rewriting an administrator's URL hides a mistake instead of reporting it;
  ``javascript:``, ``data:``, and protocol-relative values are refused for the
  obvious reason.
* an **internal** destination *key* from
  :data:`apps.web.quick_access.catalog.INTERNAL_DESTINATIONS`. A key is not a
  path: the path is produced by ``reverse()`` when the link renders, so a route
  rename can never leave a live launcher pointing at a stranger's URL.

Query strings survive; fragments and userinfo do not. A link record must never
carry a credential, so a URL that tries to smuggle one in is rejected outright
rather than stripped.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.web.quick_access.catalog import internal_destination_keys

MAX_DESTINATION_LENGTH = 500

#: Query/fragment names that would put a secret in a stored URL. Matching is on
#: the whole parameter name, so ``token`` is refused and ``tokenized`` is not.
CREDENTIAL_PARAMETERS: frozenset[str] = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "auth",
        "client_secret",
        "id_token",
        "password",
        "pwd",
        "refresh_token",
        "secret",
        "session",
        "sig",
        "signature",
        "token",
    }
)


def _validate_external(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https":
        raise ValidationError(_("External links must start with https://."))
    if not parsed.hostname:
        raise ValidationError(_("Enter a full https:// address including a host."))
    if parsed.username is not None or parsed.password is not None:
        raise ValidationError(
            _("Remove the credentials from the address. Links never carry secrets.")
        )
    if parsed.fragment:
        raise ValidationError(_("Remove the # fragment from the address."))
    names = {
        pair.split("=", 1)[0].strip().lower()
        for pair in parsed.query.split("&")
        if pair
    }
    if names & CREDENTIAL_PARAMETERS:
        raise ValidationError(
            _(
                "This address carries what looks like a credential. Store "
                "sign-in secrets in the identity provider, not in the link."
            )
        )
    return value


def _validate_internal(value: str) -> str:
    if value not in internal_destination_keys():
        raise ValidationError(_("Choose one of the approved internal destinations."))
    return value


def validate_destination(destination_type: str, value: str) -> str:
    """Return the normalized destination, or raise ``ValidationError``.

    Fails closed: an unrecognized ``destination_type`` is refused rather than
    treated as a URL.
    """
    value = (value or "").strip()
    if not value:
        raise ValidationError(_("Enter a destination."))
    if len(value) > MAX_DESTINATION_LENGTH:
        raise ValidationError(_("This destination is too long."))
    if destination_type == "external_url":
        return _validate_external(value)
    if destination_type == "internal_route":
        return _validate_internal(value)
    raise ValidationError(_("Choose a destination type."))
