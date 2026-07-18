"""DigitalOcean Serverless Inference client."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)

from app.workers.errors import (
    ConfigurationError,
    InferenceError,
    PayloadValidationError,
    ProviderAPIError,
    ProviderAuthError,
    ProviderRateLimitError,
)

logger = logging.getLogger(__name__)

BASE_URL = os.getenv("DO_INFERENCE_BASE_URL", "https://inference.do-ai.run/v1/")


def _default_model() -> str:
    return os.getenv("DO_INFERENCE_MODEL", "llama3.3-70b-instruct")


def _client() -> OpenAI:
    api_key = os.getenv("DO_MODEL_ACCESS_KEY")
    if not api_key or api_key == "replace_me":
        raise ConfigurationError(
            "DO_MODEL_ACCESS_KEY is not set. Put your DigitalOcean model access key in .env"
        )
    return OpenAI(base_url=BASE_URL, api_key=api_key, timeout=120.0)


def _messages_from_payload(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    if isinstance(payload.get("messages"), list) and payload["messages"]:
        return payload["messages"]

    prompt = payload.get("prompt") or payload.get("message") or payload.get("input")
    if isinstance(prompt, str) and prompt.strip():
        return [{"role": "user", "content": prompt.strip()}]

    raise PayloadValidationError(
        "payload must include 'prompt' (string) or non-empty 'messages' (list)"
    )


def _map_provider_error(exc: Exception) -> InferenceError:
    if isinstance(exc, InferenceError):
        return exc
    if isinstance(exc, AuthenticationError):
        return ProviderAuthError(
            "DigitalOcean authentication failed; check DO_MODEL_ACCESS_KEY",
            details={"provider_status": getattr(exc, "status_code", 401)},
        )
    if isinstance(exc, RateLimitError):
        return ProviderRateLimitError(
            "DigitalOcean rate limit exceeded",
            details={"provider_status": getattr(exc, "status_code", 429)},
        )
    if isinstance(exc, APITimeoutError):
        return ProviderAPIError(
            "DigitalOcean request timed out",
            retryable=True,
            details={"reason": "timeout"},
        )
    if isinstance(exc, APIConnectionError):
        return ProviderAPIError(
            "Could not connect to DigitalOcean inference API",
            retryable=True,
            details={"reason": "connection_error"},
        )
    if isinstance(exc, APIStatusError):
        status = getattr(exc, "status_code", None)
        retryable = status is not None and status >= 500
        return ProviderAPIError(
            f"DigitalOcean API error (status={status})",
            retryable=retryable,
            details={"provider_status": status, "body": str(exc)[:500]},
        )
    return ProviderAPIError(str(exc), retryable=False)


def run_inference(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Call DigitalOcean chat completions and return a JSON-serializable result."""
    model = payload.get("model") or _default_model()
    messages = _messages_from_payload(payload)

    logger.info(
        "DigitalOcean inference triggered model=%s messages=%s",
        model,
        messages,
    )

    try:
        response = _client().chat.completions.create(
            model=model,
            messages=messages,
        )
    except Exception as exc:  # noqa: BLE001 — mapped to typed InferenceError
        mapped = _map_provider_error(exc)
        logger.error(
            "DigitalOcean inference failed code=%s retryable=%s error=%s",
            mapped.code,
            mapped.retryable,
            mapped.message,
        )
        raise mapped from exc

    if not response.choices:
        raise ProviderAPIError(
            "DigitalOcean returned no choices",
            retryable=True,
            details={"model": model},
        )

    choice = response.choices[0].message
    content = choice.content
    if content is None or (isinstance(content, str) and not content.strip()):
        raise ProviderAPIError(
            "DigitalOcean returned an empty completion",
            retryable=True,
            details={"model": response.model or model},
        )

    usage = response.usage
    result = {
        "provider": "digitalocean",
        "model": response.model or model,
        "content": content,
        "usage": None
        if usage is None
        else {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
        },
    }

    logger.info(
        "DigitalOcean inference response model=%s content=%r usage=%s",
        result["model"],
        result["content"],
        result["usage"],
    )
    return result
