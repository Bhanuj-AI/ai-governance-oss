from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ai_governance.domain.replay import (
    ControlledEvidenceIntervention,
    ControlledEvidenceStrategy,
    ReplayConfiguration,
)
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.services.agent_runtime_controlled_replay import (
    AgentRuntimeReplayNotAvailable,
)
from ai_governance.services.replay_execution import (
    ReplayExecutionAdapterRegistry,
    ReplayExecutionContext,
)
from ai_governance.services.synthetic_agent_runtime_replay import (
    SyntheticAgentRuntimeReplayAdapter,
    SyntheticAgentRuntimeReplayError,
    SyntheticReplayHttpResponse,
    _synthetic_runtime_token_from_environment,
)

NOW = datetime(2026, 8, 26, tzinfo=UTC)
ENDPOINT = "https://synthetic-runtime.example.test/replay"


class _Transport:
    def __init__(self, responses) -> None:
        self.responses = list(responses)
        self.requests: list[tuple[str, dict[str, object], dict[str, str]]] = []

    def post(self, endpoint, payload, headers, timeout_seconds):
        self.requests.append((endpoint, dict(payload), dict(headers)))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class _NotCancelled:
    is_cancelled = False


@pytest.mark.parametrize(
    "strategy",
    [
        ControlledEvidenceStrategy.NULLIFY,
        ControlledEvidenceStrategy.REPLACE,
        ControlledEvidenceStrategy.PERTURB,
    ],
)
def test_synthetic_adapter_replays_each_supported_intervention(strategy):
    transport = _Transport([_response(strategy)])
    adapter = _adapter(transport)

    replay = adapter.replay(_source(), _configuration(), _context(strategy))

    assert replay.execution_adapter == "synthetic-agent-runtime/v1"
    assert replay.final_state["causal_audit_outcome_score"] == 0.35
    assert replay.final_state["outcome_ref"].startswith("synthetic://replays/run-123#")
    request = transport.requests[0][1]
    assert request["intervention"] == strategy.value
    assert request["replay_reference"] == "synthetic://replays/run-123"
    if strategy is ControlledEvidenceStrategy.REPLACE:
        assert request["replacement_evidence_digest"] == "sha256:replacement"


def test_adapter_rejects_unsupported_intervention_before_calling_runtime():
    transport = _Transport([_response(ControlledEvidenceStrategy.REPLACE)])
    adapter = _adapter(transport)
    source = _source(supported=["REPLACE"])

    with pytest.raises(AgentRuntimeReplayNotAvailable, match="unsupported"):
        adapter.replay(
            source,
            _configuration(),
            _context(ControlledEvidenceStrategy.NULLIFY),
        )

    assert transport.requests == []


@pytest.mark.parametrize(
    "reference",
    ["", "artifact://unsafe", "synthetic://replays/run/123", "synthetic://other/run-123"],
)
def test_adapter_rejects_malformed_opaque_replay_reference(reference):
    adapter = _adapter(_Transport([]))

    with pytest.raises(AgentRuntimeReplayNotAvailable, match="invalid synthetic replay"):
        adapter.validate_configuration(_source(reference=reference), _configuration())


def test_adapter_requires_capability_endpoint_to_match_approved_worker_endpoint():
    adapter = _adapter(_Transport([]))

    with pytest.raises(AgentRuntimeReplayNotAvailable, match="not approved"):
        adapter.validate_configuration(
            _source(endpoint="https://unapproved.example.test/replay"), _configuration()
        )


def test_adapter_retries_transient_server_failure_with_stable_idempotency_key():
    transport = _Transport(
        [
            SyntheticReplayHttpResponse(503, {}),
            _response(ControlledEvidenceStrategy.REPLACE),
        ]
    )
    adapter = _adapter(transport)

    adapter.replay(_source(), _configuration(), _context(ControlledEvidenceStrategy.REPLACE))

    assert len(transport.requests) == 2
    assert transport.requests[0][2]["Idempotency-Key"] == transport.requests[1][2]["Idempotency-Key"]


def test_adapter_does_not_retry_an_authentication_or_validation_response():
    transport = _Transport([SyntheticReplayHttpResponse(401, {})])
    adapter = _adapter(transport)

    with pytest.raises(SyntheticAgentRuntimeReplayError, match="HTTP 401"):
        adapter.replay(
            _source(), _configuration(), _context(ControlledEvidenceStrategy.REPLACE)
        )

    assert len(transport.requests) == 1


def test_adapter_fails_closed_for_runtime_error_or_malformed_response():
    unavailable = _adapter(
        _Transport(
            [
                SyntheticAgentRuntimeReplayError("timeout"),
                SyntheticAgentRuntimeReplayError("timeout"),
            ]
        )
    )
    with pytest.raises(SyntheticAgentRuntimeReplayError, match="timeout"):
        unavailable.replay(
            _source(), _configuration(), _context(ControlledEvidenceStrategy.REPLACE)
        )

    malformed = _adapter(
        _Transport(
            [
                SyntheticReplayHttpResponse(
                    200,
                    {
                        "execution_status": "COMPLETED",
                        "isolated": False,
                        "replay_reference": "synthetic://replays/run-123",
                        "intervention": "REPLACE",
                        "outcome_score": 0.35,
                    },
                )
            ]
        )
    )
    with pytest.raises(SyntheticAgentRuntimeReplayError, match="unsafe or malformed"):
        malformed.replay(
            _source(), _configuration(), _context(ControlledEvidenceStrategy.REPLACE)
        )


def test_registry_resolves_synthetic_adapter_and_unknown_adapter_fails_closed():
    registry = ReplayExecutionAdapterRegistry()
    adapter = _adapter(_Transport([]))
    registry.register(adapter)

    assert registry.resolve("synthetic-agent-runtime/v1") is adapter
    with pytest.raises(Exception, match="unavailable"):
        registry.resolve("unknown-runtime/v1")


def _adapter(transport):
    return SyntheticAgentRuntimeReplayAdapter(
        approved_endpoint=ENDPOINT,
        transport=transport,
        token_provider=lambda: None,
        max_attempts=2,
    )


def test_external_runtime_replay_does_not_inherit_generic_workload_oauth(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AI_GOVERNANCE_OAUTH_TOKEN_URL", "https://issuer.example/token")
    monkeypatch.setenv("AI_GOVERNANCE_OAUTH_CLIENT_ID", "unrelated-workload")
    monkeypatch.setenv("AI_GOVERNANCE_OAUTH_CLIENT_SECRET", "unrelated-secret")
    monkeypatch.delenv("AI_GOVERNANCE_SYNTHETIC_RUNTIME_REPLAY_OAUTH_TOKEN_URL", raising=False)
    monkeypatch.delenv("AI_GOVERNANCE_SYNTHETIC_RUNTIME_REPLAY_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("AI_GOVERNANCE_SYNTHETIC_RUNTIME_REPLAY_OAUTH_CLIENT_SECRET", raising=False)

    assert _synthetic_runtime_token_from_environment() is None


def _source(
    *,
    reference: str = "synthetic://replays/run-123",
    endpoint: str = ENDPOINT,
    supported: list[str] | None = None,
) -> WorkflowExecution:
    return WorkflowExecution(
        workflow_id="agent-runtime:claims-agent",
        execution_id="agent-runtime-source:execution-1",
        workflow_name="Claims Agent",
        workflow_version="v1",
        execution_status="COMPLETED",
        input={},
        final_state={},
        events=[
            {
                "event_id": "tool-call-1",
                "evidence_references": ["artifact://claim/1"],
                "external_tool_call_id": "run-123:tool:1",
            }
        ],
        organization_id="org-a",
        project_id="project-a",
        execution_adapter="synthetic-agent-runtime/v1",
        input_snapshot_ref="agent-runtime:execution-1:input",
        state_snapshot_ref="agent-runtime:execution-1:state",
        artifact_refs=[reference],
        runtime_parameters={
            "agent_runtime_replay": {
                "runtime_type": "synthetic-agent-runtime",
                "adapter_id": "synthetic-agent-runtime/v1",
                "adapter_version": "1",
                "replay_reference": reference,
                "endpoint": endpoint,
                "supported_interventions": supported
                or ["NULLIFY", "REPLACE", "PERTURB"],
            }
        },
        metadata={"external_execution_id": "run-123"},
        created_at=NOW,
    )


def _configuration() -> ReplayConfiguration:
    return ReplayConfiguration(
        workflow_id="agent-runtime:claims-agent",
        workflow_version="v1",
        execution_adapter="synthetic-agent-runtime/v1",
        input_snapshot_ref="agent-runtime:execution-1:input",
        state_snapshot_ref="agent-runtime:execution-1:state",
        configuration_hash="configuration-hash",
    )


def _context(strategy: ControlledEvidenceStrategy) -> ReplayExecutionContext:
    return ReplayExecutionContext(
        replay_id="replay-1",
        source_execution_id="agent-runtime-source:execution-1",
        new_execution_id="replay-execution-1",
        organization_id="org-a",
        project_id="project-a",
        actor_id="auditor",
        request_id="request-1",
        correlation_id="correlation-1",
        attempt=1,
        cancellation_token=_NotCancelled(),
        metadata={},
        controlled_evidence_intervention=ControlledEvidenceIntervention(
            strategy,
            "v1",
            "artifact://claim/1",
            target_event_id="tool-call-1",
            counterfactual_evidence_reference="artifact://claim/1/replacement",
            counterfactual_evidence_digest="sha256:replacement",
            policy_id="policy-1",
            policy_version=1,
            provider_id="structured-json",
            provider_version="v1",
            original_evidence_digest="sha256:original",
        ),
    )


def _response(strategy: ControlledEvidenceStrategy) -> SyntheticReplayHttpResponse:
    return SyntheticReplayHttpResponse(
        200,
        {
            "execution_status": "COMPLETED",
            "isolated": True,
            "replay_reference": "synthetic://replays/run-123",
            "intervention": strategy.value,
            "external_execution_id": "run-123",
            "external_tool_call_id": "run-123:tool:1",
            "source_evidence_digest": "sha256:original",
            "outcome_score": 0.35,
        },
    )
