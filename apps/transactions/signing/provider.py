"""Signing provider seam for transaction packages.

Only ``hub_native`` exists and it is the decided implementation: Hub field
placement, the Hub signing pad, and a pyHanko PKCS#12 organization seal. The
protocol exists so views depend on a named capability surface rather than on
module internals, and so an unknown ``TRANSACTION_SIGNING_PROVIDER`` fails at
resolution instead of silently degrading.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.transactions.models import (
    SignatureAccessToken,
    SignaturePackage,
    SignaturePackageSigner,
)
from apps.user.models import User

HUB_NATIVE = "hub_native"
DEFAULT_PROVIDER = HUB_NATIVE


@runtime_checkable
class SigningProvider(Protocol):
    """What a signing backend must be able to do for a package."""

    name: str

    def send_package(
        self, actor: User, package: Any, *, expected_version: str = ""
    ) -> SignaturePackage:
        """Validate a draft and release it to its first signers."""
        ...

    def remind_signer(
        self, signer: SignaturePackageSigner, *, reminder_day: int = 0
    ) -> bool:
        """Nudge one outstanding signer. Returns whether a reminder went out."""
        ...

    def start_ceremony(
        self,
        *,
        package: SignaturePackage,
        signer: SignaturePackageSigner,
        consent_accepted: bool,
        disclosure_version: str,
        request_meta: Any,
        actor: User | None = None,
        access_token: SignatureAccessToken | None = None,
    ) -> dict[str, Any]:
        """Record consent and open a short-lived signing intent."""
        ...

    def complete_ceremony(
        self,
        *,
        intent_public_id: UUID,
        signer: SignaturePackageSigner,
        signature_data_url: str,
        signed_date: str,
        initials_data_url: str = "",
        text_values: dict[str, str] | None = None,
        request_meta: Any,
        access_token: SignatureAccessToken | None = None,
    ) -> dict[str, Any]:
        """Turn an intent into a durable signature and advance routing."""
        ...

    def decline_ceremony(
        self,
        *,
        package: SignaturePackage,
        signer: SignaturePackageSigner,
        reason: str = "",
        request_meta: Any = None,
        access_token: SignatureAccessToken | None = None,
    ) -> dict[str, Any]:
        """Refuse on behalf of one signer, ending the package."""
        ...

    def finalize_package(self, package_id: int) -> str:
        """Produce sealed artifacts for a fully signed package."""
        ...


class HubNativeSigningProvider:
    """Hub-owned ceremony with a pyHanko organization seal."""

    name = HUB_NATIVE

    def send_package(
        self, actor: User, package: Any, *, expected_version: str = ""
    ) -> SignaturePackage:
        from apps.transactions.signing.authoring import validate_and_send

        return validate_and_send(actor, package, expected_version=expected_version)

    def remind_signer(
        self, signer: SignaturePackageSigner, *, reminder_day: int = 0
    ) -> bool:
        from apps.transactions.signing.notification_schedule import remind_signer

        return remind_signer(signer, reminder_day=reminder_day)

    def start_ceremony(
        self,
        *,
        package: SignaturePackage,
        signer: SignaturePackageSigner,
        consent_accepted: bool,
        disclosure_version: str,
        request_meta: Any,
        actor: User | None = None,
        access_token: SignatureAccessToken | None = None,
    ) -> dict[str, Any]:
        from apps.transactions.signing.ceremony import start_intent

        return start_intent(
            package=package,
            signer=signer,
            consent_accepted=consent_accepted,
            disclosure_version=disclosure_version,
            request_meta=request_meta,
            actor=actor,
            access_token=access_token,
        )

    def complete_ceremony(
        self,
        *,
        intent_public_id: UUID,
        signer: SignaturePackageSigner,
        signature_data_url: str,
        signed_date: str,
        initials_data_url: str = "",
        text_values: dict[str, str] | None = None,
        request_meta: Any,
        access_token: SignatureAccessToken | None = None,
    ) -> dict[str, Any]:
        from apps.transactions.signing.ceremony import complete_signing

        return complete_signing(
            intent_public_id=intent_public_id,
            signer=signer,
            signature_data_url=signature_data_url,
            signed_date=signed_date,
            initials_data_url=initials_data_url,
            text_values=text_values,
            request_meta=request_meta,
            access_token=access_token,
        )

    def decline_ceremony(
        self,
        *,
        package: SignaturePackage,
        signer: SignaturePackageSigner,
        reason: str = "",
        request_meta: Any = None,
        access_token: SignatureAccessToken | None = None,
    ) -> dict[str, Any]:
        from apps.transactions.signing.ceremony import decline_signing

        return decline_signing(
            package=package,
            signer=signer,
            reason=reason,
            request_meta=request_meta,
            access_token=access_token,
        )

    def finalize_package(self, package_id: int) -> str:
        from apps.transactions.signing.finalize import finalize_package

        return finalize_package(package_id)


_PROVIDERS: dict[str, type[HubNativeSigningProvider]] = {
    HUB_NATIVE: HubNativeSigningProvider,
}


def get_signing_provider(name: str | None = None) -> SigningProvider:
    """Resolve the configured backend, failing loudly on an unknown name."""
    code = (
        name
        or getattr(settings, "TRANSACTION_SIGNING_PROVIDER", DEFAULT_PROVIDER)
        or DEFAULT_PROVIDER
    ).strip()
    provider = _PROVIDERS.get(code)
    if provider is None:
        raise ImproperlyConfigured(
            f"Unknown TRANSACTION_SIGNING_PROVIDER {code!r}. "
            f"Known providers: {sorted(_PROVIDERS)}."
        )
    return provider()


__all__ = [
    "DEFAULT_PROVIDER",
    "HUB_NATIVE",
    "HubNativeSigningProvider",
    "SigningProvider",
    "get_signing_provider",
]
