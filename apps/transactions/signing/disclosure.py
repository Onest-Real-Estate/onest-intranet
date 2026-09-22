"""Versioned e-signature disclosure for transaction document packages.

Separate from :mod:`apps.contract.signing_disclosure` on purpose: that copy
names the agent contract and the authenticated Hub recipient, while a deal
package is signed by outside parties (buyers, sellers, lenders) who may arrive
through a magic link. Legal must approve this text before production; bump
``DISCLOSURE_VERSION`` whenever the copy changes so every signature records
which text the signer acknowledged.
"""

from __future__ import annotations

DISCLOSURE_VERSION = "2026-09-22.1"

DISCLOSURE_TITLE = "Electronic signature disclosure (ESIGN / UETA)"

DISCLOSURE_BODY = (
    "By continuing, you agree to receive and sign these transaction documents "
    "electronically. Your signature on the PDF is an electronic signature under "
    "the Electronic Signatures in Global and National Commerce Act (ESIGN Act, "
    "15 U.S.C. §7001 et seq.) and applicable Uniform Electronic Transactions Act "
    "(UETA) provisions—not a handwritten wet-ink mark on paper, and not merely "
    "checking a box on this page.\n\n"
    "The acknowledgement below records that you have read this disclosure and "
    "consent to electronic records and signatures for this transaction. The "
    "drawn or typed signature, initials, date, and text fields assigned to you "
    "are the legally operative electronic signature.\n\n"
    "You are signing as the named party on this exact package of documents, "
    "using hardware and software capable of accessing PDF documents. The link "
    "or session that brought you here is personal to you and must not be "
    "forwarded. Do not sign if the documents do not match the agreement you "
    "intend to accept.\n\n"
    "You may request a paper copy of these documents through the brokerage's "
    "standard transaction administration process, and you may decline to sign "
    "electronically at any point before you submit. After every party finishes "
    "signing, oNEST stores an immutable signature record, the signed PDFs "
    "(including any organization cryptographic seal), and a certificate of "
    "completion listing each signer."
)

ACKNOWLEDGEMENT_LABEL = (
    "I have read this ESIGN/UETA disclosure, I consent to electronic records "
    "and signatures for these transaction documents, and I intend to sign "
    "electronically as the named party."
)

DECLINE_LABEL = (
    "I do not consent to sign electronically. Notify the brokerage so the "
    "package can be handled another way."
)


def disclosure_payload() -> dict[str, str]:
    """Camel-cased disclosure contract for the ceremony page."""
    return {
        "version": DISCLOSURE_VERSION,
        "title": DISCLOSURE_TITLE,
        "body": DISCLOSURE_BODY,
        "acknowledgementLabel": ACKNOWLEDGEMENT_LABEL,
        "declineLabel": DECLINE_LABEL,
    }


__all__ = [
    "ACKNOWLEDGEMENT_LABEL",
    "DECLINE_LABEL",
    "DISCLOSURE_BODY",
    "DISCLOSURE_TITLE",
    "DISCLOSURE_VERSION",
    "disclosure_payload",
]
