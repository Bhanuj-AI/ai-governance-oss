"""Fail-closed adapter helpers for tool runtimes, including LangGraph."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from ai_governance.runtime_authorization.contracts import (
    RuntimeActionAuthorizationDecision,
    RuntimeActionAuthorizationRequest,
)


class RuntimeActionAuthorizationClient(Protocol):
    """A client of the public AIGP runtime-action authorization endpoint."""

    def authorize(
        self, request: RuntimeActionAuthorizationRequest
    ) -> RuntimeActionAuthorizationDecision: ...


class ProtectedOperationBlocked(PermissionError):
    """Raised before a protected operation when no valid ALLOW exists."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(f"Protected operation blocked: {reason_code}.")
        self.reason_code = reason_code


class LangGraphOperationAuthorizer:
    """Fail-closed authorization boundary for a LangGraph tool wrapper.

    The class has no LangGraph dependency: an adapter calls
    :meth:`require_allow` immediately before invoking a protected tool. This
    preserves LangGraph's execution ownership while requiring an actual AIGP
    decision for each consequential operation.
    """

    def __init__(
        self,
        client: RuntimeActionAuthorizationClient,
        *,
        actor_id: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._client = client
        self._actor_id = actor_id
        self._clock = clock or (lambda: datetime.now(UTC))

    def require_allow(
        self,
        request: RuntimeActionAuthorizationRequest,
        *,
        actual_tool_arguments_digest: str,
    ) -> RuntimeActionAuthorizationDecision:
        """Return only a still-valid, operation-bound ALLOW or raise.

        A timeout, malformed response, denied result, actor mismatch, resource
        mismatch, and expiry all take the same safe path: the tool is not run.
        """

        try:
            decision = self._client.authorize(request)
        except Exception as exc:
            raise ProtectedOperationBlocked("AUTHORIZATION_UNAVAILABLE") from exc
        if not isinstance(decision, RuntimeActionAuthorizationDecision):
            raise ProtectedOperationBlocked("MALFORMED_AUTHORIZATION_RESPONSE")
        if not decision.is_valid_for(
            request,
            actor_id=self._actor_id,
            now=self._clock(),
        ):
            raise ProtectedOperationBlocked(
                decision.reason_code
                if decision.outcome.value == "DENY"
                else "INVALID_AUTHORIZATION_DECISION"
            )
        if (
            request.tool_arguments_digest != actual_tool_arguments_digest
            or decision.tool_arguments_digest != actual_tool_arguments_digest
        ):
            raise ProtectedOperationBlocked("TOOL_ARGUMENTS_MISMATCH")
        return decision
