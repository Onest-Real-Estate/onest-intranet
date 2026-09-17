"""SSRF defenses for announcement article URL fetching.

Every outbound request to a user-supplied URL goes through this module first.
The contract matches the OWASP SSRF cheat sheet for the hub's threat model:

* HTTPS only, no credentials in the URL, port 443 only.
* Hostname must resolve to public addresses only — loopback, private,
  link-local, multicast, and other special-use ranges are refused.
* Redirects are not followed blindly: each ``Location`` is re-validated, or
  redirects are refused entirely depending on the caller.
* DNS rebinding is mitigated by resolving before connect and connecting to the
  checked address with an explicit ``Host`` header.

Nothing here returns raw upstream exceptions to the caller.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse, urlunparse

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

ALLOWED_PORTS: frozenset[int] = frozenset({443})
MAX_REDIRECTS = 3

#: Hosts that must never be contacted, even if they resolve publicly in tests.
BLOCKED_HOSTNAMES: frozenset[str] = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
        "metadata.google",
        "metadata",
    }
)


class UnsafeArticleUrl(ValidationError):
    """The supplied URL is not safe to fetch."""


@dataclass(frozen=True)
class SafeUrl:
    """A validated HTTPS URL plus the public addresses it currently resolves to."""

    url: str
    hostname: str
    port: int
    addresses: tuple[str, ...]


def _is_blocked_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return True
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or (ip.version == 4 and ip in ipaddress.ip_network("169.254.0.0/16"))
        or (ip.version == 4 and ip in ipaddress.ip_network("100.64.0.0/10"))
        or (ip.version == 6 and ip in ipaddress.ip_network("fc00::/7"))
        or (ip.version == 6 and ip in ipaddress.ip_network("fe80::/10"))
        or (ip.version == 6 and getattr(ip, "is_site_local", False))
    )


def resolve_public_addresses(hostname: str) -> tuple[str, ...]:
    """Resolve ``hostname`` and refuse if any answer is non-public."""
    lowered = hostname.lower().rstrip(".")
    if lowered in BLOCKED_HOSTNAMES or lowered.endswith(".localhost"):
        raise UnsafeArticleUrl(
            {"url": _("That address cannot be fetched from the hub.")}
        )
    try:
        infos = socket.getaddrinfo(lowered, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeArticleUrl(
            {"url": _("That address could not be resolved.")}
        ) from exc
    addresses: list[str] = []
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        address = str(sockaddr[0])
        if _is_blocked_ip(address):
            raise UnsafeArticleUrl(
                {"url": _("That address cannot be fetched from the hub.")}
            )
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise UnsafeArticleUrl({"url": _("That address could not be resolved.")})
    return tuple(addresses)


def validate_fetch_url(raw: str) -> SafeUrl:
    """Normalize and authorize one candidate article or image URL."""
    text = (raw or "").strip()
    if not text:
        raise UnsafeArticleUrl({"url": _("Paste a public HTTPS article URL.")})
    if len(text) > 2000:
        raise UnsafeArticleUrl({"url": _("That URL is too long.")})

    parsed = urlparse(text)
    if parsed.scheme.lower() != "https":
        raise UnsafeArticleUrl({"url": _("Only HTTPS article URLs are supported.")})
    if parsed.username or parsed.password:
        raise UnsafeArticleUrl(
            {"url": _("URLs with usernames or passwords cannot be fetched.")}
        )
    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    if not hostname:
        raise UnsafeArticleUrl({"url": _("That URL is missing a host name.")})
    if hostname in BLOCKED_HOSTNAMES or hostname.endswith(".localhost"):
        raise UnsafeArticleUrl(
            {"url": _("That address cannot be fetched from the hub.")}
        )

    # Literal IP in the host — still must be public.
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if _is_blocked_ip(hostname):
            raise UnsafeArticleUrl(
                {"url": _("That address cannot be fetched from the hub.")}
            )

    port = parsed.port or 443
    if port not in ALLOWED_PORTS:
        raise UnsafeArticleUrl({"url": _("Only the standard HTTPS port is allowed.")})

    addresses = resolve_public_addresses(hostname)
    # Rebuild without fragment; keep path/query.
    netloc = hostname if port == 443 else f"{hostname}:{port}"
    normalized = urlunparse(("https", netloc, parsed.path or "/", "", parsed.query, ""))
    return SafeUrl(url=normalized, hostname=hostname, port=port, addresses=addresses)


def validate_redirect_target(location: str, *, base_url: str) -> SafeUrl:
    """Validate one redirect Location against the same SSRF rules as the start URL."""
    if not location or not location.strip():
        raise UnsafeArticleUrl({"url": _("The site returned an invalid redirect.")})
    absolute = urljoin(base_url, location.strip())
    return validate_fetch_url(absolute)
