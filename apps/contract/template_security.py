"""Validation for governed contract template uploads.

The goal here is structural safety, not best-effort sanitizing. Templates are
accepted only when they fit a narrow, documented feature set:

- DOCX files may use structured content controls identified by tag name.
- PDF files may use AcroForm field names.
- No macros, remote relationships, JavaScript, launch actions, or embedded-file
  behavior is accepted.
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from django.core.exceptions import ValidationError
from pypdf import PdfReader

WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
REL_NAMESPACE = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"w": WORD_NAMESPACE, "rel": REL_NAMESPACE}

ALLOWED_TEMPLATE_FORMATS = frozenset({"docx", "pdf"})
ALLOWED_DOCX_EXTENSIONS = frozenset({".docx"})
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

    if suffix in ALLOWED_DOCX_EXTENSIONS or normalized_type in {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    }:
        return "docx"
    if suffix in ALLOWED_PDF_EXTENSIONS or normalized_type == "application/pdf":
        return "pdf"
    raise ValidationError(
        {
            "source_document": (
                "Upload a .docx contract template or a PDF form template."
            )
        }
    )


def inspect_template(
    *,
    filename: str,
    media_type: str,
    data: bytes,
) -> TemplateInspection:
    template_format = infer_template_format(filename=filename, media_type=media_type)
    if template_format == "docx":
        placeholders = inspect_docx_template(data)
        normalized_type = (
            media_type
            or "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    else:
        placeholders = inspect_pdf_template(data)
        normalized_type = media_type or "application/pdf"
    return TemplateInspection(
        format=template_format,
        media_type=normalized_type,
        checksum=checksum_of(data),
        placeholder_keys=tuple(sorted(placeholders)),
    )


def inspect_docx_template(data: bytes) -> set[str]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValidationError(
            {"source_document": "The DOCX file could not be read."}
        ) from exc

    names = set(archive.namelist())
    if "word/vbaProject.bin" in names:
        raise ValidationError(
            {"source_document": "DOCX templates with macros are not allowed."}
        )

    for rel_name in [name for name in names if name.endswith(".rels")]:
        rel_root = ElementTree.fromstring(archive.read(rel_name))
        for rel in rel_root.findall("rel:Relationship", NS):
            if rel.attrib.get("TargetMode") == "External":
                raise ValidationError(
                    {
                        "source_document": (
                            "DOCX templates cannot reference external resources."
                        )
                    }
                )

    try:
        document_root = ElementTree.fromstring(archive.read("word/document.xml"))
    except KeyError as exc:
        raise ValidationError(
            {"source_document": "The DOCX file is missing its main document."}
        ) from exc

    placeholders: set[str] = set()
    for sdt in document_root.findall(".//w:sdt", NS):
        tag = sdt.find(".//w:tag", NS)
        if tag is None:
            continue
        key = (tag.attrib.get(f"{{{WORD_NAMESPACE}}}val") or "").strip()
        if key:
            placeholders.add(key)

    if not placeholders:
        raise ValidationError(
            {
                "source_document": (
                    "DOCX templates must declare at least one content-control tag."
                )
            }
        )
    return placeholders


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

    fields = reader.get_fields() or {}
    placeholders = {str(name).strip() for name in fields if str(name).strip()}
    if not placeholders:
        raise ValidationError(
            {
                "source_document": (
                    "PDF templates must expose at least one AcroForm field."
                )
            }
        )
    return placeholders


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
                "The uploaded template contains unknown placeholders: "
                + ", ".join(unknown_placeholders)
            ]
        if missing_placeholders:
            errors.setdefault("merge_schema", []).append(
                "The merge schema declares placeholders missing from the uploaded "
                "template: " + ", ".join(missing_placeholders)
            )
        raise ValidationError(errors)


def synthetic_preview_context(merge_schema: list[dict]) -> dict[str, str]:
    """Safe fake values for previews.

    The production render path is reused, but previews should not expose real
    people data by default. Values are deterministic so preview-related tests
    and checksums stay stable.
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
