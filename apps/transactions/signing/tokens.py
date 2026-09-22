"""Magic-link access tokens for external (email) package signers.

Only the SHA-256 hex digest is persisted. The raw token exists for the length
of one request — long enough to put in an email body — and can never be
recovered from the database, so a leaked dump does not grant signing access.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.transactions.models import SignatureAccessToken, SignaturePackageSigner

logger = logging.getLogger("apps.transactions")

DEFAULT_TTL_SECONDS = 7 * 24 * 60 * 60
TOKEN_BYTES = 32


def _configured_ttl() -> int:
    raw = getattr(
        settings,
        "TRANSACTION_SIGNATURE_MAGIC_LINK_TTL_SECONDS",
        DEFAULT_TTL_SECONDS,
    )
    try:
        return max(300, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_TTL_SECONDS


def hash_token(raw: str) -> str:
    """Stable digest used as the stored lookup key."""
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()


def issue_access_token(
    signer: SignaturePackageSigner,
    *,
    ttl: int | None = None,
) -> tuple[SignatureAccessToken, str]:
    """Mint a fresh link for ``signer`` and retire any earlier live links.

    Returns ``(token_row, raw_token)``. The caller is responsible for putting
    the raw value in exactly one outbound email and then dropping it.
    """
    seconds = _configured_ttl() if ttl is None else max(300, int(ttl))
    now = timezone.now()
    invalidate_signer_tokens(signer, now=now)

    raw = secrets.token_urlsafe(TOKEN_BYTES)
    token = SignatureAccessToken.objects.create(
        signer=signer,
        token_hash=hash_token(raw),
        expires_at=now + timedelta(seconds=seconds),
    )
    return token, raw


def lookup_active_token(raw: str) -> SignatureAccessToken | None:
    """Resolve a raw link to a live token row, or ``None``.

    The digest comparison is constant-time even though the lookup itself is an
    indexed equality match, so a timing signal cannot confirm a near-miss.
    """
    value = (raw or "").strip()
    if not value:
        return None
    digest = hash_token(value)
    token = (
        SignatureAccessToken.objects.select_related(
            "signer",
            "signer__package",
            "signer__package__transaction",
        )
        .filter(token_hash=digest, consumed_at__isnull=True)
        .first()
    )
    if token is None:
        return None
    if not hmac.compare_digest(token.token_hash, digest):
        return None
    if token.expires_at <= timezone.now():
        return None
    return token


def consume_token(token: SignatureAccessToken) -> SignatureAccessToken:
    """Burn a link once its ceremony has produced a durable outcome."""
    if token.consumed_at is None:
        token.consumed_at = timezone.now()
        token.save(update_fields=["consumed_at"])
    return token


def invalidate_signer_tokens(signer: SignaturePackageSigner, *, now=None) -> int:
    """Consume every live link for a signer (re-send, decline, or cancel)."""
    moment = now or timezone.now()
    return SignatureAccessToken.objects.filter(
        signer=signer, consumed_at__isnull=True
    ).update(consumed_at=moment)


def invalidate_package_tokens(package_id: int, *, now=None) -> int:
    """Consume every live link across a package once it reaches a terminal state."""
    moment = now or timezone.now()
    return SignatureAccessToken.objects.filter(
        signer__package_id=package_id, consumed_at__isnull=True
    ).update(consumed_at=moment)


def mark_token_sent(token: SignatureAccessToken) -> None:
    """Record delivery so reminder cadence can be measured from the last send."""
    token.last_sent_at = timezone.now()
    token.save(update_fields=["last_sent_at"])


__all__ = [
    "DEFAULT_TTL_SECONDS",
    "consume_token",
    "hash_token",
    "invalidate_package_tokens",
    "invalidate_signer_tokens",
    "issue_access_token",
    "lookup_active_token",
    "mark_token_sent",
]
