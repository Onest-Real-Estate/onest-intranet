"""Versioned electronic-signature disclosure for agent contract signing.

Legal must approve the disclosure text before production. Bump
``DISCLOSURE_VERSION`` whenever the copy changes so signatures record which
text the signer acknowledged.
"""

from __future__ import annotations

DISCLOSURE_VERSION = "2026-08-26.1"

DISCLOSURE_TITLE = "Electronic signature disclosure"

DISCLOSURE_BODY = (
    "By continuing, you agree to sign this agent contract electronically using "
    "DocuSeal. Your signature on the PDF is an electronic signature under "
    "applicable law—not a handwritten wet-ink mark on paper, and not merely "
    "checking a box on this page. The acknowledgement below records that you "
    "have read this disclosure; the DocuSeal signature and date fields on the "
    "agreement are the legally operative electronic signature.\n\n"
    "You are signing as the named recipient on this exact issued contract "
    "version. Only you may complete this ceremony with your authenticated "
    "session. Do not sign if the PDF does not match the agreement you intend "
    "to accept. After you finish in DocuSeal, oNEST stores an immutable "
    "signature record and the signed PDF before showing a success state."
)

ACKNOWLEDGEMENT_LABEL = (
    "I have read the electronic signature disclosure and I intend to sign "
    "this contract electronically as the named recipient."
)


def disclosure_payload() -> dict[str, str]:
    return {
        "version": DISCLOSURE_VERSION,
        "title": DISCLOSURE_TITLE,
        "body": DISCLOSURE_BODY,
        "acknowledgementLabel": ACKNOWLEDGEMENT_LABEL,
    }
