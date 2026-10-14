"""Transport-bound client tests for runtime action authorization."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest

from ai_governance.runtime_authorization import (
    AIGPRuntimeActionAuthorizationClient,
    RuntimeActionAuthorizationRequest,
    RuntimeActionResource,
)


@contextmanager
def _response(payload: dict[str, object]) -> Iterator[object]:
    class Response:
        def read(self) -> bytes:
            return json.dumps(payload).encode("utf-8")

    yield Response()


def _request() -> RuntimeActionAuthorizationRequest:
    return RuntimeActionAuthorizationRequest(
        execution_id="execution-1",
        action_id="operations.update_status",
        resource=RuntimeActionResource("sqlite.row", "operational-record:OPS-001"),
        context={"intent": "WRITE"},
        idempotency_key="authorization-1",
        correlation_id="run-1",
    )


def test_client_sends_only_allowlisted_scope_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}
    now = datetime(2026, 10, 14, tzinfo=UTC)

    def fake_urlopen(request, timeout):
        captured["headers"] = dict(request.header_items())
        captured["timeout"] = timeout
        return _response(
            {
                "schema_version": "runtime-action-authorization/v1",
                "decision_id": "decision-1",
                "outcome": "ALLOW",
                "reason_code": "ALLOW_POLICY_MATCHED",
                "decision_at": now.isoformat(),
                "expires_at": (now + timedelta(minutes=5)).isoformat(),
                "execution_id": "execution-1",
                "correlation_id": "run-1",
                "action_id": "operations.update_status",
                "resource": {
                    "resource_type": "sqlite.row",
                    "resource_reference": "operational-record:OPS-001",
                },
                "actor_id": "runtime-service",
                "idempotency_key": "authorization-1",
                "request_fingerprint": _request().fingerprint(),
            }
        )

    monkeypatch.setattr(
        "ai_governance.runtime_authorization.http_client.urlopen", fake_urlopen
    )
    client = AIGPRuntimeActionAuthorizationClient(
        "https://aigp.example",
        bearer_token="test-token",
        scope_headers={
            "X-AI-Governance-Organization-Id": "org-a",
            "X-AI-Governance-Project-Id": "project-a",
            "X-Correlation-Id": "run-1",
            "X-Request-Id": "run-1:authorize",
        },
    )

    decision = client.authorize(_request())

    assert decision.decision_id == "decision-1"
    assert captured["timeout"] == 5.0
    assert captured["headers"] == {
        "X-ai-governance-organization-id": "org-a",
        "X-ai-governance-project-id": "project-a",
        "X-correlation-id": "run-1",
        "X-request-id": "run-1:authorize",
        "Content-type": "application/json",
        "Accept": "application/json",
        "Authorization": "Bearer test-token",
    }


def test_client_rejects_non_scope_headers() -> None:
    with pytest.raises(ValueError, match="scope_headers"):
        AIGPRuntimeActionAuthorizationClient(
            "https://aigp.example",
            scope_headers={"Authorization": "Bearer caller-controlled"},
        )
