from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from kavach.mcp.authentication import McpAuthenticationContext
from kavach.mcp.runtime_context import get_runtime_context


RestTransport = Callable[
    [str, str, Mapping[str, Any] | None, Mapping[str, Any] | None],
    Any,
]
AuthProvider = Callable[[], str | None]


class RestClientError(Exception):
    """
    Raised when the REST control plane returns or causes a failed request.
    """

    def __init__(
        self,
        *,
        status_code: int,
        payload: Any | None = None,
    ) -> None:
        super().__init__(f"REST request failed with status {status_code}.")
        self.status_code = status_code
        self.payload = payload


@dataclass(frozen=True)
class RestClient:
    """
    Minimal REST client used by MCP handlers.

    The optional transport hook keeps handlers unit-testable without network
    calls while production uses the Python standard library HTTP client.
    """

    base_url: str
    timeout: float = 10.0
    retries: int = 0
    transport: RestTransport | None = None
    default_headers: Mapping[str, str] | None = None
    auth_provider: AuthProvider | None = None
    authentication_context: McpAuthenticationContext | None = None

    def with_tenant_context(
        self, organization_id: str, project_id: str | None = None
    ) -> RestClient:
        headers = dict(self.default_headers or {})
        headers["X-Kavach-Organization-Id"] = organization_id
        if project_id:
            headers["X-Kavach-Project-Id"] = project_id
        return replace(self, default_headers=headers)

    def get(
        self,
        path: str,
        *,
        query: Mapping[str, Any] | None = None,
    ) -> Any:
        return self.request("GET", path, query=query)

    def post(
        self,
        path: str,
        *,
        body: Mapping[str, Any] | None = None,
    ) -> Any:
        return self.request("POST", path, body=body)

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, Any] | None = None,
        body: Mapping[str, Any] | None = None,
    ) -> Any:
        if self.transport is not None:
            return self.transport(method, path, query, body)

        attempts = max(1, self.retries + 1)
        last_error: RestClientError | None = None

        for _attempt in range(attempts):
            try:
                return self._request_once(method, path, query=query, body=body)
            except RestClientError as exc:
                last_error = exc
                if exc.status_code < 500:
                    raise

        if last_error is not None:
            raise last_error

        raise RestClientError(status_code=500)

    def _request_once(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, Any] | None,
        body: Mapping[str, Any] | None,
    ) -> Any:
        url = self._url(path, query)
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        headers = self._headers()
        request = Request(
            url=url,
            data=payload,
            method=method,
            headers={
                "Content-Type": "application/json",
                **headers,
            },
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                return _decode_response(response.read())
        except HTTPError as exc:
            raise RestClientError(
                status_code=exc.code,
                payload=_decode_response(exc.read()),
            ) from exc
        except URLError as exc:
            raise RestClientError(
                status_code=503,
                payload={
                    "error": {
                        "code": "rest_unavailable",
                        "message": str(exc.reason),
                    }
                },
            ) from exc

    def _url(
        self,
        path: str,
        query: Mapping[str, Any] | None,
    ) -> str:
        base = self.base_url.rstrip("/") + "/"
        url = urljoin(base, path.lstrip("/"))
        filtered_query = {
            key: value for key, value in (query or {}).items() if value is not None
        }
        if filtered_query:
            return f"{url}?{urlencode(filtered_query, doseq=True)}"
        return url

    def _headers(self) -> dict[str, str]:
        """Build headers for this call without sharing request identity."""
        headers = dict(self.default_headers or {})
        runtime = get_runtime_context()
        context = runtime.authentication if runtime is not None else self.authentication_context
        if context is not None:
            authorization = context.authorization_header()
            if authorization:
                headers["Authorization"] = authorization
        elif self.auth_provider is not None:
            token = self.auth_provider()
            if token:
                headers["Authorization"] = f"Bearer {token}"

        if runtime is not None:
            if runtime.request_id:
                headers["X-Request-Id"] = runtime.request_id
            if runtime.correlation_id:
                headers["X-Correlation-Id"] = runtime.correlation_id
            if runtime.development_actor_id:
                headers["X-Kavach-Actor-Id"] = runtime.development_actor_id
        return headers


def _decode_response(raw: bytes) -> Any:
    if not raw:
        return None
    return json.loads(raw.decode("utf-8"))
