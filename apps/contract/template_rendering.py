"""Legacy local template rendering (retired).

Contract templates are authored and filled through DocuSeal. This module remains
only so historical imports fail loudly instead of silently using AcroForms.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError


def render_preview_pdf(**_kwargs) -> tuple[bytes, tuple[str, ...]]:
    raise ValidationError(
        {
            "form": [
                "Local AcroForm/DOCX rendering is retired. Use the DocuSeal "
                "template builder and submission pipeline."
            ]
        }
    )


def render_pdf_template(*_args, **_kwargs) -> bytes:
    raise ValidationError(
        {"form": ["Local AcroForm fill is retired. Use DocuSeal submissions."]}
    )


def render_docx_template(*_args, **_kwargs) -> bytes:
    raise ValidationError(
        {
            "form": [
                "DOCX content-control rendering is retired. Upload a PDF for DocuSeal."
            ]
        }
    )


def convert_docx_to_pdf(*_args, **_kwargs) -> bytes:
    raise ValidationError(
        {"form": ["DOCX conversion is retired. Upload a PDF for DocuSeal."]}
    )
