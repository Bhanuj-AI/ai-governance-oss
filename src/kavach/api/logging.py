from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import Request, Response

RequestHandler = Callable[[Request], Awaitable[Response]]

LOGGER_NAME = "kavach.api"
REQUEST_ID_HEADER = "X-Request-ID"


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
            "request_id=%s organization_id=%s project_id=%s actor_id=%s "
            "correlation_id=%s method=%s path=%s status_code=%s latency_ms=%.2f",
            request_id,
            request.headers.get("X-Kavach-Organization-Id"),
            request.headers.get("X-Kavach-Project-Id"),
            request.headers.get("X-Kavach-Actor-Id"),
            request.headers.get("X-Correlation-Id"),
            request.method,
            request.url.path,
            status_code,
            latency_ms,
        )
        if "response" in locals():
            response.headers[REQUEST_ID_HEADER] = request_id
