import io
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from django.core.exceptions import ValidationError
from django.test import override_settings
from mistralai.client.errors import SDKError
from pypdf import PdfWriter
from reportlab.pdfgen import canvas

from apps.contract.document_ocr import (
    extract_native_pdf_regions,
    extract_ocr_regions,
    map_fields_to_ocr_regions,
    ocr_configured,
    ocr_document,
    suggest_layout_from_ocr,
)


def _blank_pdf(*, width: float = 300, height: float = 200) -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=width, height=height)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _sdk_error(status: int) -> SDKError:
    request = httpx.Request("POST", "https://api.mistral.ai/v1/ocr")
    response = httpx.Response(status, request=request, text="{}")
    return SDKError("ocr failed", response)


@override_settings(MISTRAL_API_KEY="")
def test_ocr_configured_requires_key():
    assert ocr_configured() is False


@override_settings(MISTRAL_API_KEY="test-key")
def test_ocr_configured_when_key_set():
    assert ocr_configured() is True


@override_settings(MISTRAL_API_KEY="")
def test_ocr_document_requires_key():
    with pytest.raises(ValidationError) as excinfo:
        ocr_document(_blank_pdf())
    assert "MISTRAL_API_KEY" in excinfo.value.message_dict["form"][0]


@override_settings(MISTRAL_API_KEY="test-key", MISTRAL_OCR_MODEL="mistral-ocr-latest")
def test_ocr_document_calls_mistral_process():
    client = MagicMock()
    client.ocr.process.return_value = object()
    with patch("apps.contract.document_ocr.Mistral", return_value=client) as ctor:
        ocr_document(_blank_pdf())
    ctor.assert_called_once_with(api_key="test-key")
    kwargs = client.ocr.process.call_args.kwargs
    assert kwargs["model"] == "mistral-ocr-latest"
    assert kwargs["include_blocks"] is True
    document = kwargs["document"]
    assert document["type"] == "document_url"
    assert document["document_url"].startswith("data:application/pdf;base64,")
    assert kwargs["document_annotation_format"]["type"] == "json_schema"
    schema = kwargs["document_annotation_format"]["json_schema"]["schema"]
    field_props = schema["$defs"]["SuggestedField"]["properties"]
    assert "anchor" in field_props
    assert "x" not in field_props


@override_settings(MISTRAL_API_KEY="test-key")
def test_ocr_document_maps_http_404():
    client = MagicMock()
    client.ocr.process.side_effect = _sdk_error(404)
    with (
        patch("apps.contract.document_ocr.Mistral", return_value=client),
        pytest.raises(ValidationError) as excinfo,
    ):
        ocr_document(_blank_pdf())
    assert "model was not found" in excinfo.value.message_dict["form"][0]
    assert "gemini" not in excinfo.value.message_dict["form"][0].lower()


@override_settings(MISTRAL_API_KEY="test-key")
def test_ocr_document_maps_http_401():
    client = MagicMock()
    client.ocr.process.side_effect = _sdk_error(401)
    with (
        patch("apps.contract.document_ocr.Mistral", return_value=client),
        pytest.raises(ValidationError) as excinfo,
    ):
        ocr_document(_blank_pdf())
    assert "API key" in excinfo.value.message_dict["form"][0]


@override_settings(MISTRAL_API_KEY="test-key")
def test_ocr_document_maps_timeout():
    client = MagicMock()
    client.ocr.process.side_effect = httpx.TimeoutException("timed out")
    with (
        patch("apps.contract.document_ocr.Mistral", return_value=client),
        pytest.raises(ValidationError) as excinfo,
    ):
        ocr_document(_blank_pdf())
    assert "Try again later" in excinfo.value.message_dict["form"][0]


def test_extract_blank_and_signature_regions_in_pdf_points():
    response = SimpleNamespace(
        pages=[
            SimpleNamespace(
                index=0,
                dimensions=SimpleNamespace(width=600, height=400, dpi=200),
                blocks=[
                    SimpleNamespace(
                        type="text",
                        top_left_x=0,
                        top_left_y=0,
                        bottom_right_x=200,
                        bottom_right_y=40,
                        content="Contractor name ______________",
                    ),
                    SimpleNamespace(
                        type="signature",
                        top_left_x=100,
                        top_left_y=300,
                        bottom_right_x=400,
                        bottom_right_y=360,
                        content="",
                    ),
                ],
            )
        ]
    )
    # PDF is half the OCR pixel size → 0.5 scale.
    regions = extract_ocr_regions(response, page_sizes={1: (300.0, 200.0)})
    assert len(regions) == 2
    blank = next(region for region in regions if region.kind == "blank")
    signature = next(region for region in regions if region.kind == "signature")
    # Blank spans the underscore portion of the text block.
    assert blank.page == 1
    assert blank.x > 40  # starts after "Contractor name "
    assert blank.y == 0.0
    assert signature.x == 50.0
    assert signature.y == 150.0
    assert signature.w == 150.0
    assert signature.h == 30.0


def test_map_annotation_uses_block_geometry_not_freeform_xy():
    response = SimpleNamespace(
        document_annotation={
            "fields": [
                {
                    "name": "ContractorName",
                    "type": "text",
                    "role": "Prefill",
                    "page": 1,
                    "anchor": "Contractor name",
                    # Deliberately wrong freeform coords — must be ignored.
                    "x": 0.9,
                    "y": 0.9,
                    "w": 0.1,
                    "h": 0.1,
                },
                {
                    "name": "AgentSignature",
                    "type": "signature",
                    "role": "Agent",
                    "page": 1,
                    "anchor": "Signature",
                },
            ]
        },
        pages=[
            SimpleNamespace(
                index=0,
                dimensions=SimpleNamespace(width=300, height=200, dpi=72),
                blocks=[
                    SimpleNamespace(
                        type="text",
                        top_left_x=10,
                        top_left_y=20,
                        bottom_right_x=200,
                        bottom_right_y=40,
                        content="Contractor name ________",
                    ),
                    SimpleNamespace(
                        type="signature",
                        top_left_x=40,
                        top_left_y=140,
                        bottom_right_x=220,
                        bottom_right_y=180,
                        content="",
                    ),
                ],
            )
        ],
    )
    fields = suggest_layout_from_ocr(response, page_sizes={1: (300.0, 200.0)})
    by_name = {field["name"]: field for field in fields}
    assert by_name["ContractorName"]["y"] == pytest.approx(20.0)
    assert by_name["ContractorName"]["y"] != pytest.approx(180.0)
    assert by_name["AgentSignature"]["type"] == "signature"
    assert by_name["AgentSignature"]["x"] == pytest.approx(40.0)
    assert by_name["AgentSignature"]["y"] == pytest.approx(140.0)


def test_annotation_normalizes_ocr_display_labels_to_valid_field_names():
    response = SimpleNamespace(
        document_annotation={
            "fields": [
                {
                    "name": "Contractor Name (legal)",
                    "type": "text",
                    "role": "Prefill",
                    "page": 1,
                    "anchor": "Contractor name",
                }
            ]
        },
        pages=[
            SimpleNamespace(
                index=0,
                dimensions=SimpleNamespace(width=300, height=200, dpi=72),
                blocks=[
                    SimpleNamespace(
                        type="text",
                        top_left_x=10,
                        top_left_y=20,
                        bottom_right_x=200,
                        bottom_right_y=40,
                        content="Contractor name ________",
                    )
                ],
            )
        ],
    )

    fields = suggest_layout_from_ocr(response, page_sizes={1: (300.0, 200.0)})

    assert fields[0]["name"] == "ContractorNameLegal"


def test_map_fields_falls_back_to_regions_without_annotation():
    regions = extract_ocr_regions(
        SimpleNamespace(
            pages=[
                SimpleNamespace(
                    index=0,
                    dimensions=SimpleNamespace(width=100, height=100, dpi=72),
                    blocks=[
                        SimpleNamespace(
                            type="signature",
                            top_left_x=10,
                            top_left_y=50,
                            bottom_right_x=80,
                            bottom_right_y=80,
                            content="",
                        )
                    ],
                )
            ]
        ),
        page_sizes={1: (100.0, 100.0)},
    )
    fields = map_fields_to_ocr_regions([], regions, page_sizes={1: (100.0, 100.0)})
    assert len(fields) == 1
    assert fields[0]["type"] == "signature"
    assert fields[0]["role"] == "Agent"


def test_native_pdf_regions_use_underline_glyph_geometry():
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=(300, 200))
    pdf.drawString(30, 150, "Contractor name __________")
    pdf.save()

    regions = extract_native_pdf_regions(buf.getvalue())

    assert len(regions) == 1
    region = regions[0]
    assert region.kind == "blank"
    assert region.content == "Contractor name __________"
    assert region.x > 100
    assert 35 < region.y < 60


def test_native_geometry_beats_paragraph_ocr_box_for_multiline_form():
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=(300, 200))
    pdf.drawString(30, 150, "Contractor name __________")
    pdf.drawString(30, 120, "Effective date __________")
    pdf.save()
    source = buf.getvalue()
    response = SimpleNamespace(
        document_annotation={
            "fields": [
                {
                    "name": "EffectiveDate",
                    "type": "date",
                    "role": "Prefill",
                    "page": 1,
                    "anchor": "Effective date",
                }
            ]
        },
        pages=[
            SimpleNamespace(
                index=0,
                dimensions=SimpleNamespace(width=300, height=200, dpi=72),
                blocks=[
                    SimpleNamespace(
                        type="text",
                        top_left_x=30,
                        top_left_y=30,
                        bottom_right_x=280,
                        bottom_right_y=90,
                        content=(
                            "Contractor name __________\\nEffective date __________"
                        ),
                    )
                ],
            )
        ],
    )

    fields = suggest_layout_from_ocr(
        response,
        page_sizes={1: (300.0, 200.0)},
        pdf_bytes=source,
    )

    assert len(fields) == 1
    assert fields[0]["name"] == "EffectiveDate"
    # The second native line is at y=80 from the top, rather than the OCR
    # paragraph box's y=30.
    assert fields[0]["y"] > 65
