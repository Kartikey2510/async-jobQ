"""Typed errors for inference / worker processing."""

from __future__ import annotations

from typing import Any, Dict, Optional


class InferenceError(Exception):
    """Base error for job inference failures."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "inference_error",
        retryable: bool = False,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.retryable = retryable
        self.details = details or {}

    def to_result(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "error": self.message,
            "code": self.code,
            "retryable": self.retryable,
        }
        if self.details:
            payload["details"] = self.details
        return payload


class PayloadValidationError(InferenceError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            code=kwargs.pop("code", "invalid_payload"),
            retryable=False,
            **kwargs,
        )


class ConfigurationError(InferenceError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            code=kwargs.pop("code", "configuration_error"),
            retryable=False,
            **kwargs,
        )


class ProviderAuthError(InferenceError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            code=kwargs.pop("code", "provider_auth_error"),
            retryable=False,
            **kwargs,
        )


class ProviderRateLimitError(InferenceError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            code=kwargs.pop("code", "provider_rate_limit"),
            retryable=True,
            **kwargs,
        )


class ProviderAPIError(InferenceError):
    def __init__(
        self,
        message: str,
        *,
        retryable: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            message,
            code=kwargs.pop("code", "provider_api_error"),
            retryable=retryable,
            **kwargs,
        )
