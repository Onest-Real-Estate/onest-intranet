"""Certificate of completion for a multi-signer transaction package.

One certificate covers the whole package: the deal, every document with its
source and signed checksums, and one block per signer. Everything printed here
is the minimized evidence set — hashed request metadata only, never a raw IP
address, user agent, or magic-link token.
"""

from __future__ import annotations

import io
from typing import Any

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

#: Content marker probed by finalize-time structural validation.
CERTIFICATE_MARKER = "transaction_certificate_of_completion"

CERTIFICATE_RENDERER_VERSION = "hub-txn-coc-1.0.0"

_LINE_WIDTH = 110
_BOTTOM_MARGIN = 0.9 * inch


class _Sheet:
    """Single-column text flow that starts a new page when it runs out of room."""

    def __init__(self, c: canvas.Canvas, *, height: float):
        self._c = c
        self._height = height
        self._y = height - inch

    def line(self, text: str, *, size: int = 10, gap: float = 14) -> None:
        if self._y <= _BOTTOM_MARGIN:
            self._c.showPage()
            self._y = self._height - inch
        self._c.setFont("Helvetica", size)
        self._c.drawString(inch, self._y, str(text)[:_LINE_WIDTH])
        self._y -= gap

    def heading(self, text: str, *, size: int = 12, gap: float = 18) -> None:
        if self._y <= _BOTTOM_MARGIN + gap:
            self._c.showPage()
            self._y = self._height - inch
        self._c.setFont("Helvetica-Bold", size)
        self._c.drawString(inch, self._y, str(text)[:_LINE_WIDTH])
        self._y -= gap

    def gap(self, amount: float = 10) -> None:
        self._y -= amount


def _pair(sheet: _Sheet, label: str, value: Any) -> None:
    shown = value if value not in (None, "") else "—"
    sheet.line(f"{label}: {shown}")


def build_package_certificate_of_completion(facts: dict[str, Any]) -> bytes:
    """Render the human-readable evidence PDF (not a cryptographic artifact)."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    _width, height = letter
    del _width
    sheet = _Sheet(c, height=height)

    c.setFont("Helvetica-Bold", 16)
    c.drawString(inch, height - inch, "Certificate of Completion")
    sheet.gap(28)
    sheet.line(
        "oNEST Hub — transaction document electronic signature evidence",
        size=11,
        gap=18,
    )
    sheet.line(f"Marker: {CERTIFICATE_MARKER}", size=8, gap=14)
    sheet.line("(Legal must approve this form before production use.)", size=9, gap=20)

    sheet.heading("Package")
    _pair(sheet, "Package public id", facts.get("packagePublicId"))
    _pair(sheet, "Package title", facts.get("packageTitle"))
    _pair(sheet, "Transaction public id", facts.get("transactionPublicId"))
    _pair(sheet, "Transaction reference", facts.get("transactionReference"))
    _pair(sheet, "Routing mode", facts.get("routingMode"))
    _pair(sheet, "Disclosure version", facts.get("disclosureVersion"))
    _pair(sheet, "Sent at (UTC)", facts.get("sentAt"))
    _pair(sheet, "Completed at (UTC)", facts.get("completedAt"))
    _pair(sheet, "Org seal subject", facts.get("sealCertSubject") or "(not sealed)")
    _pair(sheet, "Org seal fingerprint", facts.get("sealCertFingerprint") or "(none)")
    _pair(sheet, "Renderer version", facts.get("rendererVersion"))

    documents = facts.get("documents") or []
    if documents:
        sheet.gap()
        sheet.heading("Documents")
        for index, document in enumerate(documents, start=1):
            sheet.line(
                f"{index}. {document.get('displayName') or '(untitled)'}",
                size=10,
                gap=13,
            )
            _pair(sheet, "   Document public id", document.get("publicId"))
            _pair(sheet, "   Source version id", document.get("versionPublicId"))
            _pair(sheet, "   Page count", document.get("pageCount"))
            _pair(sheet, "   Source SHA-256", document.get("sourceChecksum"))
            _pair(sheet, "   Signed SHA-256", document.get("signedChecksum"))

    signers = facts.get("signers") or []
    if signers:
        sheet.gap()
        sheet.heading("Signers")
        for index, signer in enumerate(signers, start=1):
            sheet.line(
                f"{index}. {signer.get('displayName') or '(unnamed)'} "
                f"({signer.get('roleLabel') or 'signer'})",
                size=10,
                gap=13,
            )
            _pair(sheet, "   Email", signer.get("email"))
            _pair(sheet, "   Delivery method", signer.get("deliveryMethod"))
            _pair(sheet, "   Routing order", signer.get("routingOrder"))
            _pair(sheet, "   Signature record id", signer.get("signaturePublicId"))
            _pair(sheet, "   Signing intent id", signer.get("intentPublicId"))
            _pair(
                sheet, "   Consent accepted at (UTC)", signer.get("consentAcceptedAt")
            )
            _pair(sheet, "   Signed at (UTC)", signer.get("signedAt"))
            _pair(sheet, "   Signature method", signer.get("method"))
            _pair(sheet, "   Disclosure version", signer.get("disclosureVersion"))
            _pair(sheet, "   Appearance SHA-256", signer.get("appearanceChecksum"))
            _pair(sheet, "   Request IP hash", signer.get("requestIpHash"))
            _pair(sheet, "   Request UA hash", signer.get("requestUaHash"))

    sheet.gap()
    sheet.line(
        "This record associates each named party's electronic signature with the",
        size=9,
        gap=12,
    )
    sheet.line(
        "exact document bytes identified above, under the ESIGN Act and UETA, as",
        size=9,
        gap=12,
    )
    sheet.line(
        "disclosed and acknowledged during the oNEST Hub signing ceremony.",
        size=9,
        gap=12,
    )
    c.showPage()
    c.save()
    return buf.getvalue()


__all__ = [
    "CERTIFICATE_MARKER",
    "CERTIFICATE_RENDERER_VERSION",
    "build_package_certificate_of_completion",
]
