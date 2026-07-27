"""Tests the request/response wiring for each provider via a mocked
httpx.post - no real API keys or network calls, since this is plumbing
correctness (right URL, right auth header, right response-parsing path),
not a check that any provider's API actually works."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PIPELINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))

from core import llm  # noqa: E402


def _fake_response(status_code=200, json_body=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body or {}
    resp.text = text
    return resp


def test_the_env_file_is_loaded_by_importing_llm_not_by_each_entry_point():
    """pipeline/.env used to be loaded only by the review app, so `wom run` and
    `python -m core.runner` saw no LLM_PROVIDER, fell through to the anthropic
    default, and asked for an ANTHROPIC_API_KEY on a Mistral-configured machine.
    The import side effect is the fix, so it is what gets pinned here."""
    import dotenv

    source = (PIPELINE_ROOT / "core" / "llm.py").read_text(encoding="utf-8")
    assert "load_dotenv(" in source, "core/llm.py must load pipeline/.env itself"
    assert "Path(__file__)" in source, "the .env path must not depend on the cwd - wom runs from anywhere"
    assert hasattr(dotenv, "load_dotenv")


def test_the_configured_provider_decides_which_key_is_demanded(monkeypatch):
    """The symptom of the bug above was an ANTHROPIC_API_KEY error while
    LLM_PROVIDER=mistral. Whatever the provider is, the key it asks for has to
    be that provider's."""
    monkeypatch.setenv("LLM_PROVIDER", "mistral")
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)

    with pytest.raises(llm.LlmError, match="MISTRAL_API_KEY"):
        llm.call_llm("hi")


def test_a_configured_provider_is_the_one_that_gets_called(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mistral")
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    body = {"choices": [{"message": {"content": "ok"}}]}

    with patch("httpx.post", return_value=_fake_response(json_body=body)) as post:
        llm.call_llm("hi")

    assert "api.mistral.ai" in post.call_args[0][0]


def test_unknown_provider_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "carrier-pigeon")
    with pytest.raises(llm.LlmError, match="Unknown LLM_PROVIDER"):
        llm.call_llm("hi")


def test_missing_anthropic_key_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(llm.LlmError, match="ANTHROPIC_API_KEY"):
        llm.call_llm("hi")


def test_anthropic_request_shape_and_response_parsing(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with patch("httpx.post") as mock_post:
        mock_post.return_value = _fake_response(
            json_body={"content": [{"type": "text", "text": "hello back"}]}
        )
        result = llm.call_llm("hi", system="be terse")

    assert result == "hello back"
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.anthropic.com/v1/messages"
    assert kwargs["headers"]["x-api-key"] == "test-key"
    assert kwargs["json"]["system"] == "be terse"
    assert kwargs["json"]["messages"] == [{"role": "user", "content": "hi"}]
    assert kwargs["json"]["temperature"] == 0


def test_openai_request_shape_and_response_parsing(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch("httpx.post") as mock_post:
        mock_post.return_value = _fake_response(
            json_body={"choices": [{"message": {"content": "hello back"}}]}
        )
        result = llm.call_llm("hi", system="be terse")

    assert result == "hello back"
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.openai.com/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert kwargs["json"]["messages"][0] == {"role": "system", "content": "be terse"}
    assert kwargs["json"]["temperature"] == 0


def test_mistral_request_shape_and_response_parsing(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mistral")
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    with patch("httpx.post") as mock_post:
        mock_post.return_value = _fake_response(
            json_body={"choices": [{"message": {"content": "hello back"}}]}
        )
        result = llm.call_llm("hi", system="be terse")

    assert result == "hello back"
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.mistral.ai/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert kwargs["json"]["messages"][0] == {"role": "system", "content": "be terse"}
    assert kwargs["json"]["temperature"] == 0


def test_openrouter_request_shape_and_response_parsing(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    with patch("httpx.post") as mock_post:
        mock_post.return_value = _fake_response(
            json_body={"choices": [{"message": {"content": "hello back"}}]}
        )
        result = llm.call_llm("hi", system="be terse")

    assert result == "hello back"
    args, kwargs = mock_post.call_args
    assert args[0] == "https://openrouter.ai/api/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert kwargs["json"]["messages"][0] == {"role": "system", "content": "be terse"}
    assert kwargs["json"]["temperature"] == 0


def test_google_request_shape_and_response_parsing(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "google")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    with patch("httpx.post") as mock_post:
        mock_post.return_value = _fake_response(
            json_body={"candidates": [{"content": {"parts": [{"text": "hello back"}]}}]}
        )
        result = llm.call_llm("hi")

    assert result == "hello back"
    args, kwargs = mock_post.call_args
    assert "generativelanguage.googleapis.com" in args[0]
    assert kwargs["params"]["key"] == "test-key"
    assert kwargs["json"]["generationConfig"]["temperature"] == 0


def test_api_error_status_raises_with_body_excerpt(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with patch("httpx.post") as mock_post:
        mock_post.return_value = _fake_response(status_code=429, text="rate limited")
        with pytest.raises(llm.LlmError, match="429"):
            llm.call_llm("hi")


def test_unknown_provider_raises_for_vision(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "carrier-pigeon")
    with pytest.raises(llm.LlmError, match="Unknown LLM_PROVIDER"):
        llm.call_llm_vision(b"\xff\xd8\xff", "image/jpeg", "describe this")


def test_anthropic_vision_request_shape_and_response_parsing(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with patch("httpx.post") as mock_post:
        mock_post.return_value = _fake_response(
            json_body={"content": [{"type": "text", "text": "a map"}]}
        )
        result = llm.call_llm_vision(b"gifbytes", "image/gif", "describe this")

    assert result == "a map"
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.anthropic.com/v1/messages"
    content = kwargs["json"]["messages"][0]["content"]
    assert content[0]["type"] == "image"
    assert content[0]["source"]["media_type"] == "image/gif"
    assert content[1] == {"type": "text", "text": "describe this"}


def test_openai_vision_request_shape_and_response_parsing(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch("httpx.post") as mock_post:
        mock_post.return_value = _fake_response(
            json_body={"choices": [{"message": {"content": "a map"}}]}
        )
        result = llm.call_llm_vision(b"gifbytes", "image/gif", "describe this")

    assert result == "a map"
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.openai.com/v1/chat/completions"
    content = kwargs["json"]["messages"][0]["content"]
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/gif;base64,")


def test_google_vision_request_shape_and_response_parsing(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "google")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    with patch("httpx.post") as mock_post:
        mock_post.return_value = _fake_response(
            json_body={"candidates": [{"content": {"parts": [{"text": "a map"}]}}]}
        )
        result = llm.call_llm_vision(b"gifbytes", "image/gif", "describe this")

    assert result == "a map"
    args, kwargs = mock_post.call_args
    assert "generativelanguage.googleapis.com" in args[0]
    parts = kwargs["json"]["contents"][0]["parts"]
    assert parts[0]["inline_data"]["mime_type"] == "image/gif"


def test_mistral_vision_request_shape_and_response_parsing(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mistral")
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    with patch("httpx.post") as mock_post:
        mock_post.return_value = _fake_response(
            json_body={"choices": [{"message": {"content": "a map"}}]}
        )
        result = llm.call_llm_vision(b"gifbytes", "image/gif", "describe this")

    assert result == "a map"
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.mistral.ai/v1/chat/completions"
    content = kwargs["json"]["messages"][0]["content"]
    assert content[1]["image_url"]["url"].startswith("data:image/gif;base64,")


def test_openrouter_vision_request_shape_and_response_parsing(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    with patch("httpx.post") as mock_post:
        mock_post.return_value = _fake_response(
            json_body={"choices": [{"message": {"content": "a map"}}]}
        )
        result = llm.call_llm_vision(b"gifbytes", "image/gif", "describe this")

    assert result == "a map"
    args, kwargs = mock_post.call_args
    assert args[0] == "https://openrouter.ai/api/v1/chat/completions"
    content = kwargs["json"]["messages"][0]["content"]
    assert content[1]["image_url"]["url"].startswith("data:image/gif;base64,")


def test_missing_openrouter_key_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(llm.LlmError, match="OPENROUTER_API_KEY"):
        llm.call_llm("hi")
