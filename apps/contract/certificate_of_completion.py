"""Certificate of completion PDF for Hub-native agent contract signatures."""

from __future__ import annotations

import io
from typing import Any

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

#: Content marker probed by final signed-PDF structural validation.
CERTIFICATE_MARKER = "certificate_of_completion"


def build_certificate_of_completion(*, facts: dict[str, Any]) -> bytes:
    """Render a human-readable evidence PDF (not a cryptographic certificate).

    Visible fields are the approved, minimized set: party identity, contract /
    version / document ids, timestamps, method, disclosure version, hashed
    request metadata, and checksums. Raw IP / UA strings are never included.
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    width, height = letter
    del width
    y = height - inch

    def line(text: str, *, size: int = 10, gap: float = 14) -> None:
        nonlocal y
        c.setFont("Helvetica", size)
        c.drawString(inch, y, text[:110])
        y -= gap

    c.setFont("Helvetica-Bold", 16)
    c.drawString(inch, y, "Certificate of Completion")
    y -= 28
    line("oNEST Hub — Agent contract electronic signature evidence", size=11, gap=18)
    line(f"Marker: {CERTIFICATE_MARKER}", size=8, gap=14)
    line("(Legal must approve this form before production use.)", size=9, gap=20)

    ordered = [
        ("Contract public id", facts.get("contractPublicId")),
        ("Version number", facts.get("versionNumber")),
        ("Document identifier", facts.get("documentIdentifier")),
        ("Verification identifier", facts.get("verificationIdentifier")),
        ("Party", facts.get("partyDisplayName")),
        ("Signer email", facts.get("signerEmail")),
        ("Signed at (UTC)", facts.get("signedAt")),
        ("Consent accepted at (UTC)", facts.get("consentAcceptedAt")),
        ("Disclosure version", facts.get("disclosureVersion")),
        ("Signature method", facts.get("signatureMethod")),
        ("Signing intent id", facts.get("intentPublicId")),
        ("Signature record id", facts.get("signaturePublicId")),
        ("Review PDF SHA-256", facts.get("reviewChecksum")),
        ("Signed PDF SHA-256", facts.get("signedChecksum")),
        ("Appearance SHA-256", facts.get("appearanceChecksum")),
        ("Request IP hash", facts.get("requestIpHash")),
        ("Request UA hash", facts.get("requestUaHash")),
        ("Org seal subject", facts.get("sealCertSubject") or "(not sealed)"),
        ("Org seal fingerprint", facts.get("sealCertFingerprint") or "(none)"),
        ("Renderer version", facts.get("rendererVersion") or ""),
    ]
    for label, value in ordered:
        line(f"{label}: {value if value not in (None, '') else '—'}")

    y -= 10
    line(
        "This record associates the named recipient's authenticated electronic",
        size=9,
        gap=12,
    )
    line(
        "signature with the issued contract PDF under the ESIGN Act and UETA,",
        size=9,
        gap=12,
    )
    line(
        "as disclosed and acknowledged during the Hub signing ceremony.",
        size=9,
        gap=12,
    )
    c.showPage()
    c.save()
    return buf.getvalue()
