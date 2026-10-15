"""Small standard-library client for the public authorization endpoint."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ai_governance.runtime_authorization.contracts import (
    RuntimeActionAuthorizationDecision,
    RuntimeActionAuthorizationRequest,
    RuntimeActionResource,
)

_ALLOWED_SCOPE_HEADERS = frozenset(
    {
        "X-AI-Governance-Organization-Id",
        "X-AI-Governance-Project-Id",
        "X-AI-Governance-Actor-Id",
        "X-Correlation-Id",
        "X-Request-Id",
    }
)


class RuntimeActionAuthorizationTransportError(RuntimeError):
    """The control plane could not provide a trustworthy decision."""


class AIGPRuntimeActionAuthorizationClient:
    """HTTP client for AIGP's public runtime-action authorization contract.

    Credentials are transmitted only in the request-local Authorization header
    and are never retained in an authorization decision or log payload.
    """

    def __init__(
        self,
        base_url: str,
        *,
        bearer_token: str | None = None,
        scope_headers: Mapping[str, str] | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        normalized = base_url.rstrip("/")
        if not normalized.startswith(("https://", "http://")):
            raise ValueError("base_url must be an HTTP(S) URL.")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        self._url = f"{normalized}/api/v1/runtime-action-authorizations/authorize"
        self._bearer_token = bearer_token
        self._scope_headers = _validated_scope_headers(scope_headers)
        self._timeout_seconds = timeout_seconds

    def authorize(
        self,
        request: RuntimeActionAuthorizationRequest,
    ) -> RuntimeActionAuthorizationDecision:
        headers = {
            **self._scope_headers,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._bearer_token is not None:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        payload = json.dumps(_request_payload(request)).encode("utf-8")
        transport_request = Request(
            self._url,
            data=payload,
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(transport_request, timeout=self._timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            raise RuntimeActionAuthorizationTransportError(
                "Runtime authorization service is unavailable or returned an invalid response."
            ) from exc
        return _decision_from_payload(body)


def _request_payload(request: RuntimeActionAuthorizationRequest) -> dict[str, Any]:
    return {
        "schema_version": request.schema_version,
        "execution_id": request.execution_id,
        "correlation_id": request.correlation_id,
        "action_id": request.action_id,
        "resource": {
            "resource_type": request.resource.resource_type,
            "resource_reference": request.resource.resource_reference,
        },
        "delegation_id": request.delegation_id,
        "delegation_version": request.delegation_version,
        "delegation_digest": request.delegation_digest,
        "tool_arguments_digest": request.tool_arguments_digest,
        "context": dict(request.context),
        "idempotency_key": request.idempotency_key,
        "policy_id": request.policy_id,
        "expected_policy_version": request.expected_policy_version,
    }


def _decision_from_payload(value: object) -> RuntimeActionAuthorizationDecision:
    if not isinstance(value, Mapping):
        raise RuntimeActionAuthorizationTransportError(
            "Runtime authorization service returned a malformed response."
        )
    try:
        resource = value["resource"]
        if not isinstance(resource, Mapping):
            raise TypeError("resource must be an object")
        return RuntimeActionAuthorizationDecision(
            schema_version=str(value["schema_version"]),
            decision_id=str(value["decision_id"]),
            outcome=str(value["outcome"]),
            reason_code=str(value["reason_code"]),
            policy_id=_optional_string(value.get("policy_id")),
            policy_version=_optional_string(value.get("policy_version")),
            decided_at=datetime.fromisoformat(str(value["decision_at"])),
            expires_at=datetime.fromisoformat(str(value["expires_at"])),
            execution_id=str(value["execution_id"]),
            correlation_id=_optional_string(value.get("correlation_id")),
            action_id=str(value["action_id"]),
            resource=RuntimeActionResource(
                resource_type=str(resource["resource_type"]),
                resource_reference=str(resource["resource_reference"]),
            ),
            actor_id=str(value["actor_id"]),
            idempotency_key=str(value["idempotency_key"]),
            request_fingerprint=str(value["request_fingerprint"]),
            delegation_id=_optional_string(value.get("delegation_id")),
            delegation_version=_optional_string(value.get("delegation_version")),
            delegation_digest=_optional_string(value.get("delegation_digest")),
            tool_arguments_digest=_optional_string(value.get("tool_arguments_digest")),
            evaluated_policies=_evaluated_policies(value.get("evaluated_policies")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeActionAuthorizationTransportError(
            "Runtime authorization service returned a malformed response."
        ) from exc


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _evaluated_policies(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        return ()
    result: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise TypeError("evaluated_policies must be a list of policy bindings")
        policy_id = _optional_string(item.get("policy_id"))
        version = _optional_string(item.get("version"))
        if policy_id is None or version is None:
            raise ValueError("evaluated policy binding is malformed")
        result.append((policy_id, version))
    return tuple(result)


def _validated_scope_headers(
    headers: Mapping[str, str] | None,
) -> dict[str, str]:
    """Accept only scope headers required by the authenticated API boundary.

    The authorization payload intentionally contains neither tenant nor actor
    claims. Deployments that select scope through request headers can supply
    only the established tenancy, correlation, and request headers here;
    credentials remain in ``bearer_token``.
    """

    if headers is None:
        return {}
    invalid = set(headers).difference(_ALLOWED_SCOPE_HEADERS)
    if invalid:
        raise ValueError(
            "scope_headers may contain only established AIGP scope headers."
        )
    normalized: dict[str, str] = {}
    for name, value in headers.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"scope header {name!r} must be a non-blank string.")
        normalized[name] = value
    return normalized
