"""Hub-native e-signature services for transaction document packages.

Layering, outermost first:

``provider``          capability seam views depend on
``authoring``         broker-side build / send / cancel (scoped + permissioned)
``ceremony``          signer-side consent, intent, signature, decline
``lifecycle``         the only writer of package and signer status
``finalize``          sealed signed PDFs and the certificate of completion
``serialize``         camelCase projections for workspace and ceremony pages

Supporting modules (``disclosure``, ``field_layout``, ``tokens``, ``emails``,
``pdf_stamp``, ``certificate``, ``notification_schedule``) hold one concern
each and never reach back up a layer.
"""

from __future__ import annotations

from apps.transactions.signing.authoring import (
    cancel_package,
    create_draft_package,
    load_package_for_reader,
    replace_package_contents,
    validate_and_send,
)
from apps.transactions.signing.ceremony import (
    RequestMeta,
    ceremony_payload,
    complete_signing,
    decline_signing,
    resolve_signer_from_hub_user,
    resolve_signer_from_token,
    start_intent,
)
from apps.transactions.signing.disclosure import (
    DISCLOSURE_VERSION,
    disclosure_payload,
)
from apps.transactions.signing.field_layout import normalize_package_fields
from apps.transactions.signing.finalize import finalize_package
from apps.transactions.signing.lifecycle import (
    assert_package_open,
    eligible_signers_queryset,
    expire_due_packages,
    set_package_status,
)
from apps.transactions.signing.notification_schedule import (
    publish_signature_reminders,
    remind_signer,
    suppress_stale_reminders,
)
from apps.transactions.signing.provider import (
    SigningProvider,
    get_signing_provider,
)
from apps.transactions.signing.serialize import (
    serialize_package,
    serialize_packages_for_reader,
    signature_schema_payload,
)

__all__ = [
    "DISCLOSURE_VERSION",
    "RequestMeta",
    "SigningProvider",
    "assert_package_open",
    "cancel_package",
    "ceremony_payload",
    "complete_signing",
    "create_draft_package",
    "decline_signing",
    "disclosure_payload",
    "eligible_signers_queryset",
    "expire_due_packages",
    "finalize_package",
    "get_signing_provider",
    "load_package_for_reader",
    "normalize_package_fields",
    "publish_signature_reminders",
    "remind_signer",
    "replace_package_contents",
    "resolve_signer_from_hub_user",
    "resolve_signer_from_token",
    "serialize_package",
    "serialize_packages_for_reader",
    "set_package_status",
    "signature_schema_payload",
    "start_intent",
    "suppress_stale_reminders",
    "validate_and_send",
]
