"""Unit tests for DigitalOcean inference helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from openai import AuthenticationError, RateLimitError

from app.workers.errors import PayloadValidationError, ProviderAuthError, ProviderRateLimitError
from app.workers.inference import _messages_from_payload, run_inference


def test_messages_from_prompt():
    assert _messages_from_payload({"prompt": "  hi there  "}) == [
        {"role": "user", "content": "hi there"}
    ]


def test_messages_from_message_alias():
    assert _messages_from_payload({"message": "hello"}) == [
        {"role": "user", "content": "hello"}
    ]


def test_messages_from_explicit_messages():
    messages = [
        {"role": "system", "content": "Be brief"},
        {"role": "user", "content": "Hi"},
    ]
    assert _messages_from_payload({"messages": messages}) == messages


def test_messages_rejects_empty_payload():
    with pytest.raises(PayloadValidationError, match="prompt"):
        _messages_from_payload({})


def test_messages_rejects_blank_prompt():
    with pytest.raises(PayloadValidationError, match="prompt"):
        _messages_from_payload({"prompt": "   "})


@patch("app.workers.inference._client")
def test_run_inference_returns_normalized_result(mock_client):
    mock_response = SimpleNamespace(
        model="llama3.3-70b-instruct",
        choices=[SimpleNamespace(message=SimpleNamespace(content="Hello!"))],
        usage=SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=3,
            total_tokens=13,
        ),
    )
    mock_client.return_value.chat.completions.create.return_value = mock_response

    result = run_inference({"prompt": "Say hello", "model": "llama3.3-70b-instruct"})

    assert result == {
        "provider": "digitalocean",
        "model": "llama3.3-70b-instruct",
        "content": "Hello!",
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 3,
            "total_tokens": 13,
        },
    }
    mock_client.return_value.chat.completions.create.assert_called_once()
    kwargs = mock_client.return_value.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "llama3.3-70b-instruct"
    assert kwargs["messages"] == [{"role": "user", "content": "Say hello"}]


@patch("app.workers.inference._client")
def test_run_inference_uses_default_model_when_missing(mock_client, monkeypatch):
    monkeypatch.setenv("DO_INFERENCE_MODEL", "alibaba-qwen3-32b")
    mock_response = SimpleNamespace(
        model=None,
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
        usage=None,
    )
    mock_client.return_value.chat.completions.create.return_value = mock_response

    result = run_inference({"prompt": "hi"})

    assert result["model"] == "alibaba-qwen3-32b"
    assert result["usage"] is None
    kwargs = mock_client.return_value.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "alibaba-qwen3-32b"


@patch("app.workers.inference._client")
def test_run_inference_maps_auth_error(mock_client):
    request = httpx.Request("POST", "https://inference.do-ai.run/v1/chat/completions")
    response = httpx.Response(401, request=request)
    mock_client.return_value.chat.completions.create.side_effect = AuthenticationError(
        message="bad auth",
        response=response,
        body={"message": "Unauthorized"},
    )
    with pytest.raises(ProviderAuthError) as exc_info:
        run_inference({"prompt": "hi"})
    assert exc_info.value.retryable is False
    assert exc_info.value.code == "provider_auth_error"


@patch("app.workers.inference._client")
def test_run_inference_maps_rate_limit(mock_client):
    request = httpx.Request("POST", "https://inference.do-ai.run/v1/chat/completions")
    response = httpx.Response(429, request=request)
    mock_client.return_value.chat.completions.create.side_effect = RateLimitError(
        message="slow down",
        response=response,
        body={"message": "rate limit"},
    )
    with pytest.raises(ProviderRateLimitError) as exc_info:
        run_inference({"prompt": "hi"})
    assert exc_info.value.retryable is True


@patch("app.workers.inference._client")
def test_run_inference_rejects_empty_choices(mock_client):
    mock_client.return_value.chat.completions.create.return_value = SimpleNamespace(
        model="llama3.3-70b-instruct",
        choices=[],
        usage=None,
    )
    with pytest.raises(Exception, match="no choices"):
        run_inference({"prompt": "hi"})
