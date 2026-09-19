"""Landscape training certificate of completion PDF (presentation, not crypto)."""

from __future__ import annotations

import io
import math
from datetime import date, datetime
from pathlib import Path

from django.conf import settings
from reportlab.lib.colors import Color, HexColor, white
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

# oNEST brand tokens (DESIGN.md) + deep ink for certificate hierarchy.
BRAND_GOLD = HexColor("#ddb52a")
BRAND_GOLD_DEEP = HexColor("#c39a15")
BRAND_GOLD_SOFT = HexColor("#fbf5df")
BRAND_INK = HexColor("#0d0d0d")
ACCENT_NAVY = HexColor("#1a2b4a")
MUTED = HexColor("#4a5568")
HAIRLINE = HexColor("#c5c9d1")

_LOGO_RELATIVE = (
    ("frontend", "images", "onest-logo.png"),
    ("frontend", "images", "onest.png"),
)


def _logo_path() -> Path | None:
    base = Path(settings.BASE_DIR)
    for parts in _LOGO_RELATIVE:
        path = base.joinpath(*parts)
        if path.is_file():
            return path
    return None


_SCRIPT_FONT = "Times-Italic"
_script_registered = False


def _ensure_script_font() -> str:
    """Prefer a local script TTF when present; otherwise Times-Italic."""
    global _script_registered, _SCRIPT_FONT
    if _script_registered:
        return _SCRIPT_FONT
    candidates = [
        Path("/usr/share/fonts/TTF/DejaVuSerif-Italic.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf"),
    ]
    for path in candidates:
        if path.is_file():
            try:
                pdfmetrics.registerFont(TTFont("CertificateScript", str(path)))
                _SCRIPT_FONT = "CertificateScript"
                break
            except Exception:
                continue
    _script_registered = True
    return _SCRIPT_FONT


def _format_completed_at(value: str | date | datetime) -> str:
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        try:
            return value.strftime("%B %-d, %Y")
        except ValueError:
            return value.strftime("%B %d, %Y").replace(" 0", " ")
    raw = (value or "").strip()
    if not raw:
        return timezone_today_label()
    try:
        parsed = date.fromisoformat(raw[:10])
    except ValueError:
        return raw
    try:
        return parsed.strftime("%B %-d, %Y")
    except ValueError:
        return parsed.strftime("%B %d, %Y").replace(" 0", " ")


def timezone_today_label() -> str:
    from django.utils import timezone

    today = timezone.localdate()
    try:
        return today.strftime("%B %-d, %Y")
    except ValueError:
        return today.strftime("%B %d, %Y").replace(" 0", " ")


def _draw_wave_band(c: canvas.Canvas, width: float, height: float) -> None:
    """Light gold mesh-like curves across the top (sample layout, oNEST palette)."""
    c.saveState()
    c.setFillColor(BRAND_GOLD_SOFT)
    c.setStrokeColor(Color(0.867, 0.71, 0.165, alpha=0.35))
    c.setLineWidth(1.2)
    for offset in (0, 14, 28, 42, 56):
        path = c.beginPath()
        path.moveTo(0, height * 0.62 + offset)
        path.curveTo(
            width * 0.28,
            height * 0.78 + offset,
            width * 0.55,
            height * 0.92 + offset,
            width + 20,
            height * 0.88 + offset,
        )
        path.lineTo(width + 20, height + 20)
        path.lineTo(-20, height + 20)
        path.close()
        c.drawPath(path, fill=1, stroke=0)
    for offset in (0, 18, 36):
        c.setStrokeColor(Color(0.867, 0.71, 0.165, alpha=0.45))
        path = c.beginPath()
        path.moveTo(width * 0.35, height * 0.55 + offset)
        path.curveTo(
            width * 0.55,
            height * 0.72 + offset,
            width * 0.75,
            height * 0.95 + offset,
            width + 10,
            height * 0.9 + offset,
        )
        c.drawPath(path, fill=0, stroke=1)
    c.restoreState()


def _draw_corner_shapes(c: canvas.Canvas, width: float, height: float) -> None:
    c.saveState()
    # Bottom-left solid navy curve.
    c.setFillColor(ACCENT_NAVY)
    path = c.beginPath()
    path.moveTo(0, 0)
    path.lineTo(0, height * 0.38)
    path.curveTo(
        width * 0.12,
        height * 0.22,
        width * 0.22,
        height * 0.08,
        width * 0.42,
        0,
    )
    path.close()
    c.drawPath(path, fill=1, stroke=0)

    # Bottom-right soft gold band.
    c.setFillColor(BRAND_GOLD)
    path = c.beginPath()
    path.moveTo(width, 0)
    path.lineTo(width, height * 0.22)
    path.curveTo(
        width * 0.88,
        height * 0.12,
        width * 0.78,
        height * 0.04,
        width * 0.62,
        0,
    )
    path.close()
    c.drawPath(path, fill=1, stroke=0)
    c.restoreState()


def _draw_seal(c: canvas.Canvas, cx: float, cy: float, radius: float = 38) -> None:
    """Decorative gold scalloped seal with navy ribbons (not a legal seal)."""
    c.saveState()
    # Ribbons
    c.setFillColor(ACCENT_NAVY)
    c.saveState()
    c.translate(cx - 10, cy - radius + 4)
    c.rotate(18)
    c.rect(-6, -52, 12, 52, fill=1, stroke=0)
    c.restoreState()
    c.saveState()
    c.translate(cx + 10, cy - radius + 4)
    c.rotate(-18)
    c.rect(-6, -52, 12, 52, fill=1, stroke=0)
    c.restoreState()

    # Scalloped outer ring
    teeth = 28
    outer = radius + 6
    path = c.beginPath()
    for i in range(teeth + 1):
        angle = (2 * math.pi * i) / teeth
        r = outer if i % 2 == 0 else radius
        x = cx + r * math.cos(angle - math.pi / 2)
        y = cy + r * math.sin(angle - math.pi / 2)
        if i == 0:
            path.moveTo(x, y)
        else:
            path.lineTo(x, y)
    path.close()
    c.setFillColor(BRAND_GOLD)
    c.drawPath(path, fill=1, stroke=0)

    c.setFillColor(BRAND_GOLD_DEEP)
    c.circle(cx, cy, radius - 4, fill=1, stroke=0)
    c.setFillColor(BRAND_GOLD_SOFT)
    c.circle(cx, cy, radius - 12, fill=1, stroke=0)
    c.setFillColor(ACCENT_NAVY)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(cx, cy + 2, "oNEST")
    c.setFont("Helvetica", 6)
    c.drawCentredString(cx, cy - 8, "HUB")
    c.restoreState()


def _draw_qr(c: canvas.Canvas, *, url: str, x: float, y: float, size: float) -> None:
    import qrcode
    from reportlab.lib.utils import ImageReader

    qr = qrcode.QRCode(version=None, box_size=8, border=1)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    c.drawImage(ImageReader(buf), x, y, width=size, height=size, mask="auto")


def build_training_certificate_pdf(
    *,
    title: str,
    learner_name: str,
    completed_at: str | date | datetime,
    public_id: str,
    verify_url: str,
    signature: str,
    signature_algorithm: str,
) -> bytes:
    """One landscape page certificate of completion for training."""
    from apps.training.certificate_crypto import signature_fingerprint

    buf = io.BytesIO()
    page = landscape(letter)
    width, height = page
    c = canvas.Canvas(buf, pagesize=page)
    script = _ensure_script_font()

    c.setFillColor(white)
    c.rect(0, 0, width, height, fill=1, stroke=0)
    _draw_wave_band(c, width, height)
    _draw_corner_shapes(c, width, height)

    cx = width / 2
    logo = _logo_path()
    header_y = height - 0.85 * inch
    if logo is not None:
        logo_w = 1.35 * inch
        logo_h = 0.85 * inch
        c.drawImage(
            str(logo),
            cx - logo_w / 2,
            header_y - logo_h / 2,
            width=logo_w,
            height=logo_h,
            mask="auto",
            preserveAspectRatio=True,
        )
    else:
        c.setFillColor(ACCENT_NAVY)
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(cx, header_y, "oNEST")
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(cx, header_y - 0.28 * inch, "REAL ESTATE")

    c.setFillColor(ACCENT_NAVY)
    c.setFont("Helvetica-Bold", 36)
    c.drawCentredString(cx, height - 2.05 * inch, "CERTIFICATE")
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(ACCENT_NAVY)
    subtitle = "OF COMPLETION"
    gap = 4
    total = sum(c.stringWidth(ch, "Helvetica-Bold", 16) for ch in subtitle) + gap * (
        len(subtitle) - 1
    )
    x = cx - total / 2
    for ch in subtitle:
        c.drawString(x, height - 2.4 * inch, ch)
        x += c.stringWidth(ch, "Helvetica-Bold", 16) + gap

    c.setFillColor(MUTED)
    c.setFont("Helvetica", 11)
    c.drawCentredString(
        cx, height - 2.95 * inch, "This certificate is proudly presented to"
    )

    display_name = (learner_name or "Learner").strip()[:80]
    c.setFillColor(ACCENT_NAVY)
    c.setFont(script, 34)
    c.drawCentredString(cx, height - 3.55 * inch, display_name)

    c.setStrokeColor(HAIRLINE)
    c.setLineWidth(1)
    name_width = min(
        4.5 * inch, max(2.5 * inch, c.stringWidth(display_name, script, 34))
    )
    c.line(
        cx - name_width / 2,
        height - 3.7 * inch,
        cx + name_width / 2,
        height - 3.7 * inch,
    )

    completed_label = _format_completed_at(completed_at)
    course = (title or "training").strip()[:90]
    c.setFillColor(BRAND_INK)
    c.setFont("Helvetica", 11)
    line = f"for successfully completing the {course} on {completed_label}"
    max_w = width - 2.4 * inch
    if c.stringWidth(line, "Helvetica", 11) <= max_w:
        c.drawCentredString(cx, height - 4.1 * inch, line)
    else:
        prefix = "for successfully completing"
        c.drawCentredString(cx, height - 4.0 * inch, prefix)
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(cx, height - 4.2 * inch, course)
        c.setFont("Helvetica", 11)
        c.drawCentredString(cx, height - 4.4 * inch, f"on {completed_label}")

    # Verification strip: QR (left) · seal (center) · crypto signature (right).
    qr_size = 1.15 * inch
    qr_x = 1.2 * inch
    qr_y = 0.85 * inch
    _draw_qr(c, url=verify_url, x=qr_x, y=qr_y, size=qr_size)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 7)
    c.drawCentredString(qr_x + qr_size / 2, qr_y - 0.18 * inch, "Scan to verify")

    _draw_seal(c, cx, 1.45 * inch, radius=32)

    right_x = width - 3.4 * inch
    right_y = 1.85 * inch
    c.setFillColor(ACCENT_NAVY)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(right_x, right_y, "Cryptographic signature")
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 7)
    c.drawString(right_x, right_y - 12, (signature_algorithm or "hmac-sha256-v1")[:40])
    c.setFillColor(BRAND_INK)
    c.setFont("Courier-Bold", 9)
    c.drawString(right_x, right_y - 28, signature_fingerprint(signature))
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 7)
    c.drawString(right_x, right_y - 44, "Verification ID")
    c.setFillColor(BRAND_INK)
    c.setFont("Courier", 7)
    c.drawString(right_x, right_y - 56, str(public_id))

    c.setFillColor(MUTED)
    c.setFont("Helvetica", 7)
    c.drawCentredString(
        cx,
        0.28 * inch,
        "Verify at the QR URL or with the verification ID. Signature is HMAC-SHA256.",
    )

    c.showPage()
    c.save()
    return buf.getvalue()
