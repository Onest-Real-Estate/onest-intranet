from apps.contract.field_ai import _chat_completions_target


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
    assert model == "gemini-2.5-flash"


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
