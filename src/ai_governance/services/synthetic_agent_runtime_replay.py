"""External, isolated Replay adapter for the Synthetic Agent Runtime.

The adapter consumes only a frozen replay capability and controlled evidence
intervention.  The capability endpoint must exactly match worker configuration
before Core makes an outbound call, so an observed execution can never direct
the worker to an arbitrary host.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from ai_governance.domain.replay import ControlledEvidenceStrategy, ReplayConfiguration
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.oauth.client_credentials import access_token_from_environment
from ai_governance.services.agent_runtime_controlled_replay import (
    AgentRuntimeReplayNotAvailable,
)
from ai_governance.services.replay_execution import ReplayExecutionContext


class SyntheticAgentRuntimeReplayError(RuntimeError):
    """The external runtime cannot safely complete a controlled replay."""


@dataclass(frozen=True)
class SyntheticReplayHttpResponse:
    """Small transport result that keeps HTTP details out of the domain model."""

    status_code: int
    payload: Mapping[str, Any]


class SyntheticReplayTransport(Protocol):
    def post(
        self,
        endpoint: str,
        payload: Mapping[str, Any],
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> SyntheticReplayHttpResponse: ...


class UrlLibSyntheticReplayTransport:
    """Dependency-free HTTP transport used by the worker composition root."""

    def post(
        self,
        endpoint: str,
        payload: Mapping[str, Any],
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> SyntheticReplayHttpResponse:
        request = Request(
            endpoint,
            data=json.dumps(payload, separators=(",", ":")).encode(),
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                value = json.load(response)
                status_code = response.getcode()
        except HTTPError as error:
            # Preserve the status so the adapter can retry only eligible 5xx
            # responses.  In particular, authentication and validation 4xx
            # responses must fail once, not churn the external runtime.
            return SyntheticReplayHttpResponse(error.code, {})
        except URLError as error:
            raise SyntheticAgentRuntimeReplayError(
                "Synthetic runtime endpoint is unavailable."
            ) from error
        except (OSError, TimeoutError) as error:
            raise SyntheticAgentRuntimeReplayError(
                "Synthetic runtime replay request timed out or failed."
            ) from error
        if not isinstance(value, Mapping):
            raise SyntheticAgentRuntimeReplayError(
                "Synthetic runtime returned a malformed replay response."
            )
        return SyntheticReplayHttpResponse(int(status_code), value)


class SyntheticAgentRuntimeReplayAdapter:
    """Call the simulator's bounded ``/replay`` API for controlled Replay.

    ``approved_endpoint`` is a worker-owned configuration value.  It must
    exactly match the endpoint frozen from the observed runtime capability.
    Credentials are obtained only from the existing short-lived OAuth client
    credentials provider when it has been configured; no bearer token is
    persisted in a replay or capability.
    """

    name = "synthetic-agent-runtime/v1"
    _REFERENCE = re.compile(r"^synthetic://replays/[A-Za-z0-9_-]+$")
    _SHA256_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")

    def __init__(
        self,
        *,
        approved_endpoint: str | None = None,
        transport: SyntheticReplayTransport | None = None,
        token_provider: Callable[[], str | None] | None = None,
        timeout_seconds: float = 10,
        max_attempts: int = 3,
    ) -> None:
        self._approved_endpoint = _normalise_endpoint(
            approved_endpoint
            if approved_endpoint is not None
            else os.getenv("AI_GOVERNANCE_SYNTHETIC_RUNTIME_REPLAY_ENDPOINT")
        )
        self._transport = transport or UrlLibSyntheticReplayTransport()
        self._token_provider = token_provider or _runtime_replay_bearer_from_environment
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts

    def validate_configuration(
        self,
        source_execution: WorkflowExecution,
        configuration: ReplayConfiguration,
    ) -> None:
        capability = _capability(source_execution)
        if capability.get("adapter_id") != self.name:
            raise AgentRuntimeReplayNotAvailable(
                "Replay source does not declare the Synthetic Agent Runtime adapter."
            )
        if capability.get("runtime_type") != "synthetic-agent-runtime":
            raise AgentRuntimeReplayNotAvailable(
                "Replay source has an unsupported synthetic runtime type."
            )
        if capability.get("adapter_version") != "1":
            raise AgentRuntimeReplayNotAvailable(
                "Replay source has an unsupported synthetic adapter version."
            )
        if configuration.execution_adapter != self.name:
            raise AgentRuntimeReplayNotAvailable(
                "Frozen replay configuration selected a different adapter."
            )
        reference = capability.get("replay_reference")
        if not isinstance(reference, str) or not self._REFERENCE.fullmatch(reference):
            raise AgentRuntimeReplayNotAvailable(
                "Replay source has an invalid synthetic replay reference."
            )
        endpoint = _normalise_endpoint(capability.get("endpoint"))
        if self._approved_endpoint is None:
            raise AgentRuntimeReplayNotAvailable(
                "Synthetic runtime endpoint is not configured for this worker."
            )
        if endpoint is None or endpoint != self._approved_endpoint:
            raise AgentRuntimeReplayNotAvailable(
                "Replay capability endpoint is not approved for this worker."
            )
        supported = _supported_interventions(capability)
        if not supported:
            raise AgentRuntimeReplayNotAvailable(
                "Replay source has no valid synthetic interventions."
            )

    def replay(
        self,
        source_execution: WorkflowExecution,
        configuration: ReplayConfiguration,
        context: ReplayExecutionContext,
    ) -> WorkflowExecution:
        self.validate_configuration(source_execution, configuration)
        if context.cancellation_token.is_cancelled:
            raise SyntheticAgentRuntimeReplayError("Replay cancellation requested.")
        intervention = context.controlled_evidence_intervention
        if intervention is None or not intervention.target_event_id:
            raise AgentRuntimeReplayNotAvailable(
                "Synthetic controlled replay requires a target tool-call event."
            )
        target = next(
            (
                event
                for event in source_execution.events
                if event.get("event_id") == intervention.target_event_id
            ),
            None,
        )
        if target is None:
            raise AgentRuntimeReplayNotAvailable(
                "Synthetic controlled replay target tool-call is unavailable."
            )
        if intervention.policy_id is not None and (
            intervention.counterfactual_evidence_reference is None
            or intervention.counterfactual_evidence_digest is None
        ):
            raise AgentRuntimeReplayNotAvailable(
                "Governed controlled Replay requires counterfactual evidence provenance."
            )
        capability = _capability(source_execution)
        if intervention.strategy not in _supported_interventions(capability):
            raise AgentRuntimeReplayNotAvailable(
                f"Intervention {intervention.strategy.value} is unsupported by this runtime."
            )
        if (
            intervention.strategy is ControlledEvidenceStrategy.REPLACE
            and not intervention.counterfactual_evidence_digest
        ):
            raise AgentRuntimeReplayNotAvailable(
                "Synthetic REPLACE replay requires intervention provenance."
            )
        runtime_tool_call_id = target.get("runtime_tool_call_id")
        if not isinstance(runtime_tool_call_id, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9:_-]{0,255}", runtime_tool_call_id
        ):
            raise AgentRuntimeReplayNotAvailable(
                "Synthetic controlled Replay target lacks a safe runtime tool-call ID."
            )
        if (
            not isinstance(intervention.original_evidence_digest, str)
            or not intervention.original_evidence_digest.strip()
        ):
            raise AgentRuntimeReplayNotAvailable(
                "Synthetic controlled Replay requires the original evidence digest."
            )
        external_execution_id = source_execution.metadata.get("external_execution_id")
        if (
            not isinstance(external_execution_id, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9:_-]{0,255}", external_execution_id)
        ):
            raise AgentRuntimeReplayNotAvailable(
                "Synthetic controlled Replay source lacks a safe external execution ID."
            )

        response = self._call_runtime(
            {
                "replay_reference": capability["replay_reference"],
                "intervention": intervention.strategy.value,
                "external_execution_id": external_execution_id,
                "runtime_tool_call_id": runtime_tool_call_id,
                "source_evidence_digest": intervention.original_evidence_digest,
                "intervention_provenance_digest": intervention.counterfactual_evidence_digest,
            },
            context.replay_id,
        )
        return _workflow_execution(
            source_execution,
            context,
            capability,
            intervention,
            response,
            external_execution_id,
            runtime_tool_call_id,
        )

    def _call_runtime(
        self, payload: Mapping[str, Any], replay_id: str
    ) -> SyntheticReplayHttpResponse:
        headers: dict[str, str] = {"Idempotency-Key": replay_id}
        token = self._token_provider()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        last_error: Exception | None = None
        for attempt in range(self._max_attempts):
            try:
                response = self._transport.post(
                    self._approved_endpoint or "", payload, headers, self._timeout_seconds
                )
            except SyntheticAgentRuntimeReplayError as error:
                last_error = error
                if attempt + 1 < self._max_attempts:
                    continue
                raise
            if response.status_code >= 500 and attempt + 1 < self._max_attempts:
                last_error = SyntheticAgentRuntimeReplayError(
                    f"Synthetic runtime failed replay (HTTP {response.status_code})."
                )
                continue
            if response.status_code < 200 or response.status_code >= 300:
                raise SyntheticAgentRuntimeReplayError(
                    f"Synthetic runtime rejected replay (HTTP {response.status_code})."
                )
            return response
        raise last_error or SyntheticAgentRuntimeReplayError(
            "Synthetic runtime replay request failed."
        )


def _capability(source_execution: WorkflowExecution) -> Mapping[str, Any]:
    value = (source_execution.runtime_parameters or {}).get("agent_runtime_replay")
    if not isinstance(value, Mapping):
        raise AgentRuntimeReplayNotAvailable(
            "Replay source has no persisted Agent Runtime replay capability."
        )
    return value


def _normalise_endpoint(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    parsed = urlparse(value.strip())
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") != "/replay"
    ):
        return None
    return value.strip().rstrip("/")


def _supported_interventions(
    capability: Mapping[str, Any],
) -> set[ControlledEvidenceStrategy]:
    values = capability.get("supported_interventions")
    if not isinstance(values, list):
        return set()
    try:
        return {ControlledEvidenceStrategy(value) for value in values}
    except (TypeError, ValueError):
        return set()


def _synthetic_runtime_token_from_environment() -> str | None:
    """Use only credentials explicitly configured for the replay target.

    The worker's generic OAuth credentials belong to other local workloads
    (for example the walkthrough). They must never be sent to, or prevent
    access to, the independently configured external runtime endpoint.
    """
    return access_token_from_environment(
        {
            "AI_GOVERNANCE_OAUTH_TOKEN_URL": os.getenv(
                "AI_GOVERNANCE_SYNTHETIC_RUNTIME_REPLAY_OAUTH_TOKEN_URL"
            ),
            "AI_GOVERNANCE_OAUTH_CLIENT_ID": os.getenv(
                "AI_GOVERNANCE_SYNTHETIC_RUNTIME_REPLAY_OAUTH_CLIENT_ID"
            ),
            "AI_GOVERNANCE_OAUTH_CLIENT_SECRET": os.getenv(
                "AI_GOVERNANCE_SYNTHETIC_RUNTIME_REPLAY_OAUTH_CLIENT_SECRET"
            ),
        }
    )


def _runtime_replay_bearer_from_environment() -> str | None:
    """Prefer the explicit replay-boundary bearer secret when configured."""
    token = os.getenv("AI_GOVERNANCE_SYNTHETIC_RUNTIME_REPLAY_AUTH_TOKEN", "").strip()
    if token:
        return token
    return _synthetic_runtime_token_from_environment()


def _workflow_execution(
    source_execution: WorkflowExecution,
    context: ReplayExecutionContext,
    capability: Mapping[str, Any],
    intervention,
    response: SyntheticReplayHttpResponse,
    external_execution_id: str,
    runtime_tool_call_id: str,
) -> WorkflowExecution:
    payload = response.payload
    score = payload.get("outcome_score")
    counterfactual_evidence_digest = payload.get("counterfactual_evidence_digest")
    if (
        payload.get("execution_status") != "COMPLETED"
        or payload.get("isolated") is not True
        or payload.get("replay_reference") != capability["replay_reference"]
        or payload.get("intervention") != intervention.strategy.value
        or payload.get("external_execution_id") != external_execution_id
        or payload.get("runtime_tool_call_id") != runtime_tool_call_id
        or payload.get("source_evidence_digest")
        != intervention.original_evidence_digest
        or not isinstance(score, (int, float))
        or isinstance(score, bool)
        or not math.isfinite(float(score))
        or not isinstance(counterfactual_evidence_digest, str)
        or not SyntheticAgentRuntimeReplayAdapter._SHA256_DIGEST.fullmatch(
            counterfactual_evidence_digest
        )
    ):
        raise SyntheticAgentRuntimeReplayError(
            "Synthetic runtime returned an unsafe or malformed replay response."
        )
    outcome_ref = (
        f"{capability['replay_reference']}#{intervention.target_event_id}:"
        f"{intervention.intervention_digest}"
    )
    return WorkflowExecution(
        workflow_id=source_execution.workflow_id,
        execution_id=context.new_execution_id,
        workflow_name=source_execution.workflow_name,
        workflow_version=source_execution.workflow_version,
        execution_status="COMPLETED",
        input={},
        final_state={
            "causal_audit_outcome_score": float(score),
            "outcome_ref": outcome_ref,
            "counterfactual_evidence_digest": counterfactual_evidence_digest,
        },
        events=[
            {
                "type": "SYNTHETIC_RUNTIME_REPLAY_COMPLETED",
                "adapter_id": SyntheticAgentRuntimeReplayAdapter.name,
                "adapter_version": capability["adapter_version"],
                "intervention_digest": intervention.intervention_digest,
                "counterfactual_evidence_digest": counterfactual_evidence_digest,
            }
        ],
        organization_id=context.organization_id,
        project_id=context.project_id,
        execution_adapter=SyntheticAgentRuntimeReplayAdapter.name,
        artifact_refs=[intervention.source_evidence_reference],
        runtime_parameters={"isolated": True},
        metadata={
            "synthetic_runtime": {
                "adapter_version": capability["adapter_version"],
                "replay_reference": capability["replay_reference"],
                "outcome_ref": outcome_ref,
                "intervention_digest": intervention.intervention_digest,
                "counterfactual_evidence_digest": counterfactual_evidence_digest,
                "diagnostics": {"response_status": "COMPLETED"},
            }
        },
        created_at=datetime.now(UTC),
    )
