"""Versioned electronic-signature disclosure for agent contract signing.

Legal must approve the disclosure text before production. Bump
``DISCLOSURE_VERSION`` whenever the copy changes so signatures record which
text the signer acknowledged.
"""

from __future__ import annotations

DISCLOSURE_VERSION = "2026-08-29.1"

DISCLOSURE_TITLE = "Electronic signature disclosure (ESIGN / UETA)"

DISCLOSURE_BODY = (
    "By continuing, you agree to receive and sign this agent contract "
    "electronically. Your signature on the PDF is an electronic signature under "
    "the Electronic Signatures in Global and National Commerce Act (ESIGN Act, "
    "15 U.S.C. §7001 et seq.) and applicable Uniform Electronic Transactions Act "
    "(UETA) provisions—not a handwritten wet-ink mark on paper, and not merely "
    "checking a box on this page.\n\n"
    "The acknowledgement below records that you have read this disclosure and "
    "consent to electronic records and signatures for this transaction. The "
    "drawn or typed signature and date fields you complete on the agreement are "
    "the legally operative electronic signature.\n\n"
    "You are signing as the named recipient on this exact issued contract "
    "version, using hardware and software capable of accessing PDF documents in "
    "your authenticated oNEST Hub session. Only you may complete this ceremony. "
    "Do not sign if the PDF does not match the agreement you intend to accept.\n\n"
    "You may request a paper copy of this agreement through your brokerage's "
    "standard contract administration process. After you finish signing, oNEST "
    "stores an immutable signature record, the signed PDF (including any "
    "organization cryptographic seal), and a certificate of completion before "
    "showing a success state."
)

ACKNOWLEDGEMENT_LABEL = (
    "I have read this ESIGN/UETA disclosure, I consent to electronic records "
    "and signatures for this agent contract, and I intend to sign electronically "
    "as the named recipient."
)


def disclosure_payload() -> dict[str, str]:
    return {
        "version": DISCLOSURE_VERSION,
        "title": DISCLOSURE_TITLE,
        "body": DISCLOSURE_BODY,
        "acknowledgementLabel": ACKNOWLEDGEMENT_LABEL,
    }
