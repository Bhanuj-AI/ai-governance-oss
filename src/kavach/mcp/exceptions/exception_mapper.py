from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from kavach.mcp.clients.rest_client import RestClientError


class MCPToolError(Exception):
    """
    Protocol-neutral MCP tool error.
    """

    def __init__(
        self,
        *,
        code: str,
        message: str,
        details: Any | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
        self.status_code = status_code

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.details is not None:
            payload["details"] = self.details
        if self.status_code is not None:
            payload["status_code"] = self.status_code
        return payload


def map_exception(exc: Exception) -> MCPToolError:
    """
    Translate validation and REST failures into MCP-facing tool errors.
    """

    if isinstance(exc, MCPToolError):
        return exc

    if isinstance(exc, ValidationError):
        return MCPToolError(
            code="validation_error",
            message="Tool input validation failed.",
            details=exc.errors(),
        )

    if isinstance(exc, KeyError):
        return MCPToolError(
            code="tool_not_found",
            message=str(exc),
        )

    if isinstance(exc, RestClientError):
        rest_error = _rest_error_payload(exc.payload)
        code = rest_error.get("code") or _code_for_status(exc.status_code)
        message = rest_error.get("message") or _message_for_status(exc.status_code)
        return MCPToolError(
            code=str(code),
            message=str(message),
            details=rest_error.get("details"),
            status_code=exc.status_code,
        )

    return MCPToolError(
        code="internal_error",
        message="Internal MCP tool error.",
    )


def _rest_error_payload(payload: Any | None) -> dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
        return dict(payload["error"])
    return {}


def _code_for_status(status_code: int) -> str:
    if status_code == 404:
        return "not_found"
    if status_code in {400, 422}:
        return "validation_error"
    return "internal_error"


def _message_for_status(status_code: int) -> str:
    if status_code == 404:
        return "Resource not found."
    if status_code in {400, 422}:
        return "Request validation failed."
    return "REST control plane request failed."
