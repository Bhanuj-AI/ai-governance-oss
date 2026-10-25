from dataclasses import replace
from datetime import UTC, datetime

import pytest

from ai_governance.domain.agent_execution import (
    ActorType,
    AgentExecution,
    AgentExecutionEvent,
    AgentExecutionStatus,
    EventType,
    ToolCallContext,
)
from ai_governance.domain.replay import (
    ControlledEvidenceIntervention,
    ControlledEvidenceStrategy,
    ReplayManifestEligibility,
    ReplayManifestReasonCode,
)
from ai_governance.services.agent_runtime_controlled_replay import (
    AgentRuntimeReplayNotAvailable,
    AgentRuntimeReplaySourceBridge,
    DeterministicAgentRuntimeReplayAdapter,
)
from ai_governance.services.replay_execution import ReplayExecutionContext
from ai_governance.services.replay_execution_discovery import (
    InMemoryReplaySourceResolver,
)
from ai_governance.tenancy.domain import TenantContext

NOW = datetime(2026, 1, 1, tzinfo=UTC)
CONTEXT = TenantContext("org-a", "project-a", "auditor", "request-a")


def test_bridge_prepares_reference_only_source_and_adapter_replays_intervention():
    bridge = AgentRuntimeReplaySourceBridge(InMemoryReplaySourceResolver())
    prepared = bridge.prepare(_execution(), [_tool_event()], CONTEXT)
    intervention = ControlledEvidenceIntervention(
        ControlledEvidenceStrategy.REPLACE,
        "v1",
        "artifact://claims/history",
        target_event_id="tool-call-1",
        counterfactual_evidence_reference="artifact://claims/history-clean",
        configuration={"sample_index": 0},
        policy_id="claims-policy",
        policy_version=1,
        provider_id="structured-json",
        provider_version="v1",
        original_evidence_digest="sha256:original",
        counterfactual_evidence_digest="sha256:clean",
    )
    adapter = DeterministicAgentRuntimeReplayAdapter(lambda _event, _intervention: 0.28)
    adapter.validate_configuration(prepared.source_execution, object())
    replay = adapter.replay(
        prepared.source_execution,
        object(),
        ReplayExecutionContext(
            replay_id="replay-1",
            source_execution_id=prepared.source_execution.execution_id,
            new_execution_id="counterfactual-1",
            organization_id="org-a",
            project_id="project-a",
            actor_id="auditor",
            request_id="request-a",
            correlation_id=None,
            attempt=1,
            cancellation_token=_NotCancelled(),
            metadata={},
            controlled_evidence_intervention=intervention,
        ),
    )

    assert prepared.capability.adapter_id == adapter.name
    assert prepared.source_execution.input == {}
    assert set(prepared.source_execution.events[0]) == {
        "event_id",
        "runtime_tool_call_id",
        "tool_call_group_id",
        "depends_on_tool_call_ids",
        "evidence_references",
        "evidence_digest",
    }
    assert replay.final_state["causal_audit_outcome_score"] == 0.28
    assert replay.runtime_parameters == {"isolated": True}


def test_bridge_freezes_only_the_runtime_endpoint_from_capability_metadata():
    execution = _execution(
        metadata={
            "replay_capability": {
                "runtime_type": "synthetic-agent-runtime",
                "adapter_id": "synthetic-agent-runtime/v1",
                "adapter_version": "1",
                "replay_reference": "synthetic://replays/run-123",
                "isolation_guarantee": "runtime-isolated/v1",
                "supported_interventions": ["REPLACE"],
                "metadata": {
                    "endpoint": "https://synthetic.example.test/replay",
                    "unsafe_unrelated_value": "must-not-cross-the-bridge",
                },
            }
        }
    )

    prepared = AgentRuntimeReplaySourceBridge(InMemoryReplaySourceResolver()).prepare(
        execution, [_tool_event()], CONTEXT
    )

    capability = prepared.source_execution.runtime_parameters["agent_runtime_replay"]
    assert capability["endpoint"] == "https://synthetic.example.test/replay"
    assert "unsafe_unrelated_value" not in capability


def test_bridge_fails_closed_without_explicit_capability():
    execution = _execution(metadata={})
    with pytest.raises(AgentRuntimeReplayNotAvailable, match="explicit replay"):
        AgentRuntimeReplaySourceBridge(InMemoryReplaySourceResolver()).prepare(
            execution, [_tool_event()], CONTEXT
        )


def test_bridge_fails_closed_for_missing_or_cyclic_tool_dependencies():
    bridge = AgentRuntimeReplaySourceBridge(InMemoryReplaySourceResolver())
    with pytest.raises(AgentRuntimeReplayNotAvailable, match="runtime_tool_call_id"):
        bridge.prepare(
            _execution(), [replace(_tool_event(), tool_call_context=None)], CONTEXT
        )
    missing_dependency = replace(
        _tool_event(),
        tool_call_context=ToolCallContext(
            "1", "call-risk", "risk-decision", ("call-missing",)
        ),
    )
    with pytest.raises(AgentRuntimeReplayNotAvailable, match="outside"):
        bridge.prepare(_execution(), [missing_dependency], CONTEXT)

    first = replace(
        _tool_event(),
        event_id="tool-call-a",
        tool_call_context=ToolCallContext("1", "call-a", "risk-inputs", ("call-b",)),
    )
    second = replace(
        _tool_event(),
        event_id="tool-call-b",
        tool_call_context=ToolCallContext("1", "call-b", "risk-inputs", ("call-a",)),
    )
    with pytest.raises(AgentRuntimeReplayNotAvailable, match="cycle"):
        bridge.prepare(_execution(), [first, second], CONTEXT)


def test_failed_execution_with_complete_evidence_is_replay_manifest_eligible():
    execution = replace(_execution(), status=AgentExecutionStatus.FAILED)
    bridge = AgentRuntimeReplaySourceBridge(InMemoryReplaySourceResolver())

    manifest = bridge.manifest(execution, [_tool_event()], CONTEXT)
    prepared = bridge.prepare(execution, [_tool_event()], CONTEXT)

    assert manifest.eligibility is ReplayManifestEligibility.ELIGIBLE
    assert manifest.source_execution_status == AgentExecutionStatus.FAILED.value
    assert manifest.reasons == ()
    assert prepared.replay_manifest == manifest
    assert prepared.source_execution.metadata["replay_manifest"] == manifest.to_dict()


def test_succeeded_receipt_does_not_make_missing_replay_evidence_eligible():
    receipt = AgentExecutionEvent(
        event_id="receipt-1",
        execution_id="agent-execution-1",
        organization_id="org-a",
        project_id="project-a",
        event_type=EventType.RUNTIME_ACTION_EXECUTION_RECEIPT,
        sequence_number=2,
        occurred_at=NOW,
        received_at=NOW,
        correlation_id=None,
        causation_id="decision-1",
        actor_id="runtime-a",
        actor_type=ActorType.SYSTEM,
        attributes={"runtime_action_execution_receipt": {"status": "SUCCEEDED"}},
    )

    manifest = AgentRuntimeReplaySourceBridge(
        InMemoryReplaySourceResolver()
    ).manifest(_execution(metadata={}), [receipt], CONTEXT)

    assert manifest.eligibility is ReplayManifestEligibility.INELIGIBLE
    assert manifest.reasons[0].code is ReplayManifestReasonCode.MISSING_REPLAY_CAPABILITY


class _NotCancelled:
    is_cancelled = False


def _execution(metadata=None):
    return AgentExecution(
        execution_id="agent-execution-1",
        organization_id="org-a",
        project_id="project-a",
        agent_id="claims-agent",
        agent_name="Claims Review Agent",
        agent_version="1",
        external_execution_id="external-1",
        runtime_provider="deterministic",
        status=AgentExecutionStatus.SUCCEEDED,
        started_at=NOW,
        completed_at=NOW,
        correlation_id=None,
        parent_execution_id=None,
        created_at=NOW,
        updated_at=NOW,
        metadata=(
            {
                "replay_capability": {
                    "runtime_type": "deterministic",
                    "adapter_id": "deterministic-agent-runtime/v1",
                    "adapter_version": "1",
                    "replay_reference": "artifact://claims/claim-001",
                    "isolation_guarantee": "runtime-isolated/v1",
                    "supported_interventions": ["NULLIFY", "REPLACE", "PERTURB"],
                }
            }
            if metadata is None
            else metadata
        ),
    )


def _tool_event():
    return AgentExecutionEvent(
        event_id="tool-call-1",
        execution_id="agent-execution-1",
        organization_id="org-a",
        project_id="project-a",
        event_type=EventType.TOOL_CALL,
        sequence_number=1,
        occurred_at=NOW,
        received_at=NOW,
        correlation_id=None,
        causation_id=None,
        actor_id="claim_history.lookup",
        actor_type=ActorType.TOOL,
        tool_call_context=ToolCallContext(
            schema_version="1",
            runtime_tool_call_id="claim-history-call",
            tool_call_group_id="claim-inputs",
        ),
        evidence_references=["artifact://claims/history"],
        attributes={
            "causal_replay": {
                "counterfactual_outcomes_by_digest": {"sha256:clean": [0.28]}
            }
        },
        event_schema_version="1",
    )
