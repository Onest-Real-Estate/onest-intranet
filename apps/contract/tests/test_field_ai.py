import io
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.test import override_settings
from pypdf import PdfWriter

from apps.contract.field_ai import (
    _chat_completions_target,
    _field_ai_http_message,
    suggest_fields_for_pdf,
)


def test_chat_completions_target_uses_gemini_openai_compat_path():
    url, headers, model = _chat_completions_target(
        endpoint="https://generativelanguage.googleapis.com",
        api_key="test-key",
        model="gpt-4o",
    )
    assert url == (
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    )
    assert headers["Authorization"] == "Bearer test-key"
    assert model == "gemini-3.6-flash"


def test_chat_completions_target_remaps_retired_gemini_flash():
    _url, _headers, model = _chat_completions_target(
        endpoint="https://generativelanguage.googleapis.com",
        api_key="test-key",
        model="gemini-2.5-flash",
    )
    assert model == "gemini-3.6-flash"


def test_chat_completions_target_keeps_explicit_gemini_model():
    url, headers, model = _chat_completions_target(
        endpoint="https://generativelanguage.googleapis.com/v1beta/openai",
        api_key="test-key",
        model="gemini-2.0-flash",
    )
    assert url == (
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    )
    assert headers["Authorization"] == "Bearer test-key"
    assert model == "gemini-2.0-flash"


def test_chat_completions_target_keeps_openai_and_azure_paths():
    openai_url, openai_headers, openai_model = _chat_completions_target(
        endpoint="https://api.openai.com",
        api_key="sk-test",
    )
    assert openai_url == "https://api.openai.com/v1/chat/completions"
    assert openai_headers["Authorization"] == "Bearer sk-test"
    assert openai_model == "gpt-4o"

    azure_url, azure_headers, azure_model = _chat_completions_target(
        endpoint="https://example.openai.azure.com",
        api_key="azure-key",
        deployment="hub-gpt-4o",
        api_version="2024-08-01-preview",
    )
    assert azure_url == (
        "https://example.openai.azure.com/openai/deployments/hub-gpt-4o/"
        "chat/completions?api-version=2024-08-01-preview"
    )
    assert azure_headers["api-key"] == "azure-key"
    assert azure_model == "hub-gpt-4o"


def test_field_ai_http_message_explains_missing_model():
    assert "gemini-3.6-flash" in _field_ai_http_message(404)
    assert "API key" in _field_ai_http_message(401)


def _blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


@override_settings(MISTRAL_API_KEY="")
def test_suggest_fields_requires_mistral_key():
    with pytest.raises(ValidationError) as excinfo:
        suggest_fields_for_pdf(_blank_pdf())
    assert "MISTRAL_API_KEY" in excinfo.value.message_dict["form"][0]


@override_settings(MISTRAL_API_KEY="test-key")
def test_suggest_fields_maps_labels_onto_ocr_blocks():
    response = SimpleNamespace(
        document_annotation={
            "fields": [
                {
                    "name": "AgentSignature",
                    "type": "signature",
                    "role": "Agent",
                    "page": 1,
                    "anchor": "Signature",
                }
            ]
        },
        pages=[
            SimpleNamespace(
                index=0,
                dimensions=SimpleNamespace(width=300, height=200, dpi=72),
                blocks=[
                    SimpleNamespace(
                        type="signature",
                        top_left_x=30,
                        top_left_y=120,
                        bottom_right_x=180,
                        bottom_right_y=160,
                        content="",
                    )
                ],
            )
        ],
    )
    with patch("apps.contract.field_ai.ocr_document", return_value=response):
        fields = suggest_fields_for_pdf(_blank_pdf())
    assert fields[0]["type"] == "signature"
    assert fields[0]["role"] == "Agent"
    assert fields[0]["page"] == 1
    assert fields[0]["x"] == pytest.approx(30.0)
    assert fields[0]["y"] == pytest.approx(120.0)
