"""Deterministic rendering for governed contract templates."""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from django.core.exceptions import ValidationError
from pypdf import PdfReader, PdfWriter

from apps.contract.template_security import (
    NS,
    WORD_NAMESPACE,
    inspect_template,
)


def render_preview_pdf(
    *,
    filename: str,
    media_type: str,
    source_bytes: bytes,
    merge_values: dict[str, str],
) -> tuple[bytes, tuple[str, ...]]:
    inspection = inspect_template(
        filename=filename,
        media_type=media_type,
        data=source_bytes,
    )
    if inspection.format == "pdf":
        return (
            render_pdf_template(source_bytes, merge_values),
            inspection.placeholder_keys,
        )

    rendered_docx = render_docx_template(source_bytes, merge_values)
    return convert_docx_to_pdf(rendered_docx), inspection.placeholder_keys


def render_pdf_template(source_bytes: bytes, merge_values: dict[str, str]) -> bytes:
    try:
        reader = PdfReader(io.BytesIO(source_bytes))
    except Exception as exc:  # noqa: BLE001 - reject malformed templates
        raise ValidationError(
            {"source_document": "The PDF template could not be rendered."}
        ) from exc

    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    for page in writer.pages:
        writer.update_page_form_field_values(
            page, {key: str(value) for key, value in merge_values.items()}
        )
    writer.set_need_appearances_writer(True)

    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def render_docx_template(source_bytes: bytes, merge_values: dict[str, str]) -> bytes:
    with zipfile.ZipFile(io.BytesIO(source_bytes), "r") as source_zip:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as target_zip:
            for info in source_zip.infolist():
                data = source_zip.read(info.filename)
                if info.filename.endswith(".xml") and info.filename.startswith("word/"):
                    data = _replace_content_controls(data, merge_values)
                target_zip.writestr(info, data)
    return output.getvalue()


def _replace_content_controls(xml_bytes: bytes, merge_values: dict[str, str]) -> bytes:
    root = ElementTree.fromstring(xml_bytes)
    for sdt in root.findall(".//w:sdt", NS):
        tag = sdt.find(".//w:tag", NS)
        if tag is None:
            continue
        key = (tag.attrib.get(f"{{{WORD_NAMESPACE}}}val") or "").strip()
        if not key or key not in merge_values:
            continue
        replacement = str(merge_values[key])
        text_nodes = sdt.findall(".//w:sdtContent//w:t", NS)
        if text_nodes:
            text_nodes[0].text = replacement
            for node in text_nodes[1:]:
                node.text = ""
            continue
        content = sdt.find(".//w:sdtContent", NS)
        if content is not None:
            run = ElementTree.SubElement(content, f"{{{WORD_NAMESPACE}}}r")
            text = ElementTree.SubElement(run, f"{{{WORD_NAMESPACE}}}t")
            text.text = replacement
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)


def convert_docx_to_pdf(docx_bytes: bytes) -> bytes:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice is None:
        raise ValidationError(
            {
                "source_document": (
                    "DOCX preview rendering requires LibreOffice on the worker host."
                )
            }
        )

    with tempfile.TemporaryDirectory(prefix="contract-template-render-") as temp_dir:
        temp_path = Path(temp_dir)
        docx_path = temp_path / "template.docx"
        pdf_path = temp_path / "template.pdf"
        docx_path.write_bytes(docx_bytes)

        result = subprocess.run(
            [
                soffice,
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(temp_path),
                str(docx_path),
            ],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "HOME": temp_dir},
        )
        if result.returncode != 0 or not pdf_path.exists():
            raise ValidationError(
                {
                    "source_document": (
                        "DOCX preview rendering failed during PDF conversion."
                    )
                }
            )
        return pdf_path.read_bytes()
