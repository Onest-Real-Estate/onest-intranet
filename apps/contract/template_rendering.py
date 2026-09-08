"""Legacy local template rendering (retired).

Agent contract templates are authored in the Hub field placer and filled /
signed by Hub-native PDF services. This module remains only so historical
imports fail loudly instead of silently using AcroForms.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError


def render_preview_pdf(**_kwargs) -> tuple[bytes, tuple[str, ...]]:
    raise ValidationError(
        {
            "form": [
                "Local AcroForm/DOCX rendering is retired. Use Hub PDF "
                "templates with field_layout."
            ]
        }
    )


def render_pdf_template(*_args, **_kwargs) -> bytes:
    raise ValidationError(
        {"form": ["Local AcroForm fill is retired. Use Hub Prefill fill."]}
    )


def render_docx_template(*_args, **_kwargs) -> bytes:
    raise ValidationError(
        {"form": ["DOCX content-control rendering is retired. Upload a PDF template."]}
    )


def convert_docx_to_pdf(*_args, **_kwargs) -> bytes:
    raise ValidationError(
        {"form": ["DOCX conversion is retired. Upload a PDF template."]}
    )
