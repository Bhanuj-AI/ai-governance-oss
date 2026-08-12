from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from shlex import split as shell_split
from uuid import uuid4

from fastapi import Request, Response

RequestHandler = Callable[[Request], Awaitable[Response]]

LOGGER_NAME = "ai_governance.api"
REQUEST_ID_HEADER = "X-Request-ID"
_TRULENS_RAW_RESPONSE_WARNING = "Multiple valid rating values found in the string"


class _TruLensResponseRedactionFilter(logging.Filter):
    """Prevent a third-party score parser from emitting raw provider responses."""

    def filter(self, record: logging.LogRecord) -> bool:
        if (
            record.name == "trulens.feedback.generated"
            and _TRULENS_RAW_RESPONSE_WARNING in str(record.msg)
        ):
            record.msg = "trulens_ambiguous_score_response response_body=redacted"
            record.args = ()
        return True


def configure_sensitive_third_party_logging() -> None:
    """Redact known third-party templates that include provider response bodies."""
    logger = logging.getLogger("trulens.feedback.generated")
    if not any(
        isinstance(candidate, _TruLensResponseRedactionFilter)
        for candidate in logger.filters
    ):
        logger.addFilter(_TruLensResponseRedactionFilter())


class ControlPlaneJsonFormatter(logging.Formatter):
    """Render safe control-plane events as compact, queryable JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        event, fields, has_unstructured_text = _event_and_fields(message)
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "component": record.name.removeprefix("ai_governance.") or record.name,
            "event": event,
        }
        if fields:
            payload["fields"] = fields
        if has_unstructured_text or (not fields and message != event):
            payload["message"] = message
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def formatter_for(log_format: str) -> logging.Formatter:
    """Return the configured human or structured application log formatter."""

    if log_format.strip().lower() == "text":
        return logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    return ControlPlaneJsonFormatter()


def _event_and_fields(message: str) -> tuple[str, dict[str, str], bool]:
    """Extract the established event-name/key-value log convention safely."""

    try:
        tokens = shell_split(message)
    except ValueError:
        tokens = message.split()
    if not tokens:
        return "log_message", {}, False
    field_tokens = [token for token in tokens[1:] if "=" in token]
    fields = {
        key: value
        for token in field_tokens
        for key, value in (token.split("=", 1),)
    }
    return tokens[0], fields, len(field_tokens) != len(tokens[1:])


async def request_logging_middleware(
    request: Request,
    call_next: RequestHandler,
) -> Response:
    """
    Log request metadata without reading bodies or sensitive values.
    """

    request_id = request.headers.get(REQUEST_ID_HEADER, str(uuid4()))
    started_at = time.perf_counter()
    status_code = 500

    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        latency_ms = (time.perf_counter() - started_at) * 1000
        logging.getLogger(LOGGER_NAME).info(
            "http_request_completed request_id=%s organization_id=%s project_id=%s actor_id=%s "
            "correlation_id=%s method=%s path=%s status_code=%s latency_ms=%.2f",
            request_id,
            request.headers.get("X-AI-Governance-Organization-Id"),
            request.headers.get("X-AI-Governance-Project-Id"),
            request.headers.get("X-AI-Governance-Actor-Id"),
            request.headers.get("X-Correlation-Id"),
            request.method,
            request.url.path,
            status_code,
            latency_ms,
        )
        if "response" in locals():
            response.headers[REQUEST_ID_HEADER] = request_id
