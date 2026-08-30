"""Validation for governed contract template uploads.

Structural safety for PDF templates that the Hub field placer annotates:

- PDF only (AcroForm / DOCX content-control merge paths are retired).
- No macros, remote relationships, JavaScript, launch actions, or embedded-file
  behavior is accepted.
- Fillable field names come from the Hub field layout — blank PDFs are OK.
"""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import Path

from django.core.exceptions import ValidationError
from pypdf import PdfReader

ALLOWED_TEMPLATE_FORMATS = frozenset({"pdf"})
ALLOWED_PDF_EXTENSIONS = frozenset({".pdf"})
UNSAFE_PDF_TOKENS = (
    b"/OpenAction",
    b"/AA",
    b"/JavaScript",
    b"/JS",
    b"/Launch",
    b"/SubmitForm",
    b"/ImportData",
    b"/RichMedia",
    b"/EmbeddedFiles",
)

# Hub commercial / party / office sources authors may map Prefill fields onto.
MERGE_SOURCE_OPTIONS: tuple[str, ...] = (
    "party.legalFirstName",
    "party.legalLastName",
    "party.displayName",
    "party.email",
    "party.licenseNumber",
    "party.licenseState",
    "party.agentIdentifier",
    "office.name",
    "office.state",
    "office.city",
    "office.streetAddress",
    "office.zipCode",
    "office.mainPhone",
    "office.publicEmail",
    "terms.agentSplitPercent",
    "terms.officeSplitPercent",
    "terms.transactionFeeAmount",
    "terms.transactionFeePercent",
    "terms.annualCapAmount",
    "terms.specialArrangements",
    "terms.mentor.percent",
    "terms.mentor.fixedAmount",
    "terms.mentor.capAmount",
    "terms.mentor.basis",
    "terms.referral.percent",
    "terms.referral.fixedAmount",
    "terms.referral.capAmount",
    "terms.referral.basis",
    "contract.effectiveOn",
    "contract.expiresOn",
    "contract.publicId",
    "contract.versionNumber",
    "contract.calculationRuleVersion",
    "template.versionLabel",
    "template.stableKey",
    "document.identifier",
    "document.rendererVersion",
)


@dataclass(frozen=True)
class TemplateInspection:
    format: str
    media_type: str
    checksum: str
    placeholder_keys: tuple[str, ...]


def checksum_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def infer_template_format(*, filename: str, media_type: str) -> str:
    suffix = Path(filename).suffix.lower()
    normalized_type = (media_type or "").strip().lower()

    if suffix in ALLOWED_PDF_EXTENSIONS or normalized_type == "application/pdf":
        return "pdf"
    raise ValidationError({"source_document": "Upload a PDF contract template."})


def inspect_template(
    *,
    filename: str,
    media_type: str,
    data: bytes,
) -> TemplateInspection:
    template_format = infer_template_format(filename=filename, media_type=media_type)
    inspect_pdf_template(data)
    return TemplateInspection(
        format=template_format,
        media_type=media_type or "application/pdf",
        checksum=checksum_of(data),
        # Field names are authored in the Hub field placer.
        placeholder_keys=(),
    )


def inspect_pdf_template(data: bytes) -> set[str]:
    if any(token in data for token in UNSAFE_PDF_TOKENS):
        raise ValidationError(
            {
                "source_document": (
                    "PDF templates cannot contain JavaScript, launch actions, or "
                    "embedded-file behavior."
                )
            }
        )

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001 - parser failure rejects the upload
        raise ValidationError(
            {"source_document": "The PDF template could not be read."}
        ) from exc

    if len(reader.pages) < 1:
        raise ValidationError(
            {"source_document": "PDF templates must contain at least one page."}
        )
    return set()


def seed_merge_schema_from_placeholders(
    placeholder_keys: list[str] | tuple[str, ...] | set[str],
) -> list[dict]:
    """Build a starter allowlist from Prefill field names."""
    return [
        {
            "key": key,
            "label": key,
            "type": "text",
            "source": key if key in MERGE_SOURCE_OPTIONS else "",
        }
        for key in sorted(
            {str(item).strip() for item in placeholder_keys if str(item).strip()}
        )
    ]


def validate_merge_schema(
    merge_schema: list[dict],
    *,
    placeholder_keys: list[str] | tuple[str, ...] | set[str],
) -> None:
    schema_keys = {
        str(item.get("key", "")).strip()
        for item in merge_schema
        if isinstance(item, dict) and str(item.get("key", "")).strip()
    }
    placeholder_set = {str(key).strip() for key in placeholder_keys if str(key).strip()}

    unknown_placeholders = sorted(placeholder_set - schema_keys)
    missing_placeholders = sorted(schema_keys - placeholder_set)
    if unknown_placeholders or missing_placeholders:
        errors = {}
        if unknown_placeholders:
            errors["source_document"] = [
                "The template field layout contains unmapped fields: "
                + ", ".join(unknown_placeholders)
            ]
        if missing_placeholders:
            errors.setdefault("merge_schema", []).append(
                "The merge schema declares fields missing from the template "
                "field layout: " + ", ".join(missing_placeholders)
            )
        raise ValidationError(errors)

    for item in merge_schema:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip()
        source = str(item.get("source", "")).strip()
        if source and source not in MERGE_SOURCE_OPTIONS:
            raise ValidationError(
                {
                    "merge_schema": [
                        f"Merge field {key or '?'} uses unknown source {source}."
                    ]
                }
            )


def synthetic_preview_context(merge_schema: list[dict]) -> dict[str, str]:
    """Safe fake values for previews.

    Values are deterministic so preview-related tests and checksums stay stable.
    """

    values: dict[str, str] = {}
    for item in merge_schema:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip()
        label = str(item.get("label", "")).strip() or key
        var_type = str(item.get("type", "")).strip()
        if not key:
            continue
        if var_type in {"date", "local_date"}:
            values[key] = "2026-08-24"
        elif var_type in {"currency", "money"}:
            values[key] = "$12,345.67"
        elif var_type in {"percent", "percentage"}:
            values[key] = "12.500%"
        elif var_type in {"boolean", "bool"}:
            values[key] = "Yes"
        elif re.search(r"email", key, re.I):
            values[key] = "preview@example.com"
        elif re.search(r"phone", key, re.I):
            values[key] = "(555) 010-0199"
        else:
            values[key] = f"Preview {label}"
    return values
