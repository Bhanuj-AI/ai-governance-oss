"""Bridge explicit Agents Runtime replay capability into the Replay Plane."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from ai_governance.domain.agent_execution import (
    AgentExecution,
    AgentExecutionEvent,
    AgentRuntimeReplayCapability,
    EventType,
)
from ai_governance.domain.replay import ControlledEvidenceStrategy
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.services.replay_execution import ReplayExecutionContext
from ai_governance.tenancy.domain import TenantContext


class AgentRuntimeReplayNotAvailable(ValueError):
    """The observed execution lacks an explicit, safe replay capability."""


class AgentRuntimeReplayAdapter(Protocol):
    """Existing Replay adapter shape specialized for an Agent Runtime source."""

    @property
    def name(self) -> str: ...

    def validate_configuration(self, source_execution, configuration) -> None: ...

    def replay(
        self, source_execution, configuration, context: ReplayExecutionContext
    ) -> WorkflowExecution: ...


@dataclass(frozen=True)
class PreparedAgentRuntimeReplay:
    source_execution: WorkflowExecution
    capability: AgentRuntimeReplayCapability
    auditable_tool_call_ids: tuple[str, ...]


class AgentRuntimeReplaySourceBridge:
    """Prepare a reference-only Replay source from an observed execution.

    The bridge persists no prompt, response, credential, or tool payload. It
    transfers only the runtime-declared opaque replay reference, bounded
    tool-call context, and durable evidence references.
    """

    def __init__(self, source_store) -> None:
        self._source_store = source_store

    def prepare(
        self,
        execution: AgentExecution,
        events: list[AgentExecutionEvent],
        context: TenantContext,
    ) -> PreparedAgentRuntimeReplay:
        capability, tool_calls = self.validate(execution, events, context)
        source = WorkflowExecution(
            workflow_id=f"agent-runtime:{execution.agent_id}",
            execution_id=f"agent-runtime-source:{execution.execution_id}",
            workflow_name=execution.agent_name,
            workflow_version=execution.agent_version,
            execution_status="COMPLETED",
            input={},
            final_state={},
            events=[_safe_event(event) for event in tool_calls],
            organization_id=context.organization_id,
            project_id=context.project_id or "",
            execution_adapter=capability.adapter_id,
            input_snapshot_ref=f"agent-runtime:{execution.execution_id}:input",
            state_snapshot_ref=f"agent-runtime:{execution.execution_id}:state",
            artifact_refs=[capability.replay_reference],
            runtime_parameters={
                "agent_runtime_replay": {
                    "runtime_type": capability.runtime_type,
                    "adapter_id": capability.adapter_id,
                    "adapter_version": capability.adapter_version,
                    "replay_reference": capability.replay_reference,
                    "supported_interventions": [
                        strategy.value
                        for strategy in capability.supported_interventions
                    ],
                    # Adapter-specific capability metadata is deliberately not
                    # copied wholesale.  The synthetic adapter needs only its
                    # declared endpoint, which is frozen with the replay
                    # configuration and matched against worker configuration
                    # before any outbound request is made.
                    "endpoint": _capability_endpoint(capability),
                }
            },
            metadata={
                "source_agent_execution_id": execution.execution_id,
                "external_execution_id": execution.external_execution_id,
            },
            created_at=datetime.now(UTC),
        )
        self._source_store.save(source)
        return PreparedAgentRuntimeReplay(
            source, capability, tuple(event.event_id for event in tool_calls)
        )

    def validate(
        self,
        execution: AgentExecution,
        events: list[AgentExecutionEvent],
        context: TenantContext,
    ) -> tuple[AgentRuntimeReplayCapability, list[AgentExecutionEvent]]:
        """Verify capability and evidence without persisting a Replay source."""
        if (
            execution.organization_id != context.organization_id
            or execution.project_id != context.project_id
        ):
            raise AgentRuntimeReplayNotAvailable(
                "Observed execution is outside the current tenant scope."
            )
        capability = _capability_from_metadata(execution.metadata)
        all_tool_calls = [
            event for event in events if event.event_type is EventType.TOOL_CALL
        ]
        if any(
            event.evidence_references and event.tool_call_context is None
            for event in all_tool_calls
        ):
            raise AgentRuntimeReplayNotAvailable(
                "A replay-relevant tool call lacks a runtime_tool_call_id."
            )
        tool_calls = [
            event for event in all_tool_calls if event.tool_call_context is not None
        ]
        if not tool_calls:
            raise AgentRuntimeReplayNotAvailable(
                "Observed execution has no replay-identifiable tool calls."
            )
        if any(event.execution_id != execution.execution_id for event in tool_calls):
            raise AgentRuntimeReplayNotAvailable(
                "Tool-call context references an event outside the observed execution."
            )
        if any(not event.evidence_references for event in tool_calls):
            raise AgentRuntimeReplayNotAvailable(
                "A tool call is missing a durable evidence reference."
            )
        _validate_tool_call_graph(tool_calls)
        return capability, tool_calls


class DeterministicAgentRuntimeReplayAdapter:
    """Isolated reference adapter proving controlled Replay architecture.

    An injected deterministic scorer is a test seam; it is not copied from
    the observed source event. The adapter performs no network or tool I/O and
    therefore cannot create a production side effect. Runtime integrations
    replace this adapter through the normal Replay adapter registry.
    """

    name = "deterministic-agent-runtime/v1"

    def __init__(
        self,
        outcome_scorer: Callable[[Mapping[str, Any], Any], float] | None = None,
    ) -> None:
        self._outcome_scorer = outcome_scorer or (lambda _event, _intervention: 0.0)

    def validate_configuration(self, source_execution, configuration) -> None:
        capability = (source_execution.runtime_parameters or {}).get(
            "agent_runtime_replay"
        )
        if (
            not isinstance(capability, Mapping)
            or capability.get("adapter_id") != self.name
        ):
            raise AgentRuntimeReplayNotAvailable(
                "Replay source does not declare the deterministic adapter."
            )

    def replay(
        self, source_execution, configuration, context: ReplayExecutionContext
    ) -> WorkflowExecution:
        intervention = context.controlled_evidence_intervention
        if intervention is None or intervention.target_event_id is None:
            raise AgentRuntimeReplayNotAvailable(
                "Controlled Agent Runtime replay requires a target tool-call event."
            )
        if intervention.policy_id is not None and (
            intervention.counterfactual_evidence_reference is None
            or intervention.counterfactual_evidence_digest is None
        ):
            raise AgentRuntimeReplayNotAvailable(
                "Governed controlled Replay requires complete counterfactual evidence provenance."
            )
        capability = (source_execution.runtime_parameters or {}).get(
            "agent_runtime_replay", {}
        )
        supported = {
            ControlledEvidenceStrategy(value)
            for value in capability.get("supported_interventions", [])
        }
        if intervention.strategy not in supported:
            raise AgentRuntimeReplayNotAvailable(
                f"Intervention {intervention.strategy.value} is unsupported by this adapter."
            )
        event = next(
            (
                candidate
                for candidate in source_execution.events
                if candidate.get("event_id") == intervention.target_event_id
            ),
            None,
        )
        if event is None:
            raise AgentRuntimeReplayNotAvailable(
                "Target tool-call event is unavailable."
            )
        runtime_tool_call_id = event.get("runtime_tool_call_id")
        if (
            not isinstance(runtime_tool_call_id, str)
            or not runtime_tool_call_id.strip()
        ):
            raise AgentRuntimeReplayNotAvailable(
                "Target tool-call lacks a runtime_tool_call_id."
            )
        score = self._outcome_scorer(event, intervention)
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            raise AgentRuntimeReplayNotAvailable(
                "Controlled replay outcome score is invalid."
            )
        sample_index = int(intervention.configuration.get("sample_index", 0))
        return WorkflowExecution(
            workflow_id=source_execution.workflow_id,
            execution_id=context.new_execution_id,
            workflow_name=source_execution.workflow_name,
            workflow_version=source_execution.workflow_version,
            execution_status="COMPLETED",
            input={},
            final_state={
                "causal_audit_outcome_score": float(score),
                "outcome_ref": f"{capability.get('replay_reference', 'replay')}#{intervention.target_event_id}:{sample_index}",
            },
            events=[{"type": "CONTROLLED_REPLAY_COMPLETED"}],
            organization_id=context.organization_id,
            project_id=context.project_id,
            execution_adapter=self.name,
            artifact_refs=[intervention.source_evidence_reference],
            runtime_parameters={"isolated": True},
            metadata={
                "controlled_replay": True,
                "controlled_evidence_intervention": {
                    "target_event_id": intervention.target_event_id,
                    "intervention_digest": intervention.intervention_digest,
                    "policy_id": intervention.policy_id,
                    "policy_version": intervention.policy_version,
                    "provider_id": intervention.provider_id,
                    "provider_version": intervention.provider_version,
                    "counterfactual_evidence_reference": intervention.counterfactual_evidence_reference,
                    "counterfactual_evidence_digest": intervention.counterfactual_evidence_digest,
                },
            },
            created_at=datetime.now(UTC),
        )


def _capability_from_metadata(
    metadata: Mapping[str, Any],
) -> AgentRuntimeReplayCapability:
    raw = metadata.get("replay_capability")
    if not isinstance(raw, Mapping):
        raise AgentRuntimeReplayNotAvailable(
            "Observed execution has no explicit replay capability."
        )
    try:
        supported = tuple(
            ControlledEvidenceStrategy(value)
            for value in raw.get("supported_interventions", ())
        )
        return AgentRuntimeReplayCapability(
            runtime_type=str(raw["runtime_type"]),
            adapter_id=str(raw["adapter_id"]),
            adapter_version=str(raw["adapter_version"]),
            replay_reference=str(raw["replay_reference"]),
            supported_interventions=supported,
            metadata=raw.get("metadata", {}),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise AgentRuntimeReplayNotAvailable(
            "Observed execution replay capability is invalid."
        ) from error


def _safe_event(event: AgentExecutionEvent) -> dict[str, Any]:
    replay = event.attributes.get("causal_replay")
    descriptor = (
        replay.get("evidence_descriptor") if isinstance(replay, Mapping) else None
    )
    context = event.tool_call_context
    if context is None:
        raise AgentRuntimeReplayNotAvailable(
            "Replay-relevant tool call lacks a runtime_tool_call_id."
        )
    return {
        "event_id": event.event_id,
        "runtime_tool_call_id": context.runtime_tool_call_id,
        "tool_call_group_id": context.tool_call_group_id,
        "depends_on_tool_call_ids": list(context.depends_on_tool_call_ids),
        "evidence_references": list(event.evidence_references),
        "evidence_digest": (
            descriptor.get("evidence_digest")
            if isinstance(descriptor, Mapping)
            and isinstance(descriptor.get("evidence_digest"), str)
            else None
        ),
    }


def _validate_tool_call_graph(tool_calls: list[AgentExecutionEvent]) -> None:
    """Fail closed only when preparing a replay-capable source graph."""

    contexts = [event.tool_call_context for event in tool_calls]
    assert all(context is not None for context in contexts)
    context_by_id = {
        context.runtime_tool_call_id: context
        for context in contexts
        if context is not None
    }
    if len(context_by_id) != len(tool_calls):
        raise AgentRuntimeReplayNotAvailable(
            "Runtime tool-call IDs must be unique within an execution."
        )
    for context in contexts:
        assert context is not None
        missing = [
            dependency_id
            for dependency_id in context.depends_on_tool_call_ids
            if dependency_id not in context_by_id
        ]
        if missing:
            raise AgentRuntimeReplayNotAvailable(
                "Tool-call dependency references a tool call outside the observed execution."
            )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(runtime_tool_call_id: str) -> None:
        if runtime_tool_call_id in visiting:
            raise AgentRuntimeReplayNotAvailable(
                "Tool-call dependency graph contains a cycle."
            )
        if runtime_tool_call_id in visited:
            return
        visiting.add(runtime_tool_call_id)
        for dependency_id in context_by_id[
            runtime_tool_call_id
        ].depends_on_tool_call_ids:
            visit(dependency_id)
        visiting.remove(runtime_tool_call_id)
        visited.add(runtime_tool_call_id)

    for runtime_tool_call_id in context_by_id:
        visit(runtime_tool_call_id)


def _capability_endpoint(capability: AgentRuntimeReplayCapability) -> str | None:
    """Return the one safe, adapter-relevant endpoint metadata field.

    Runtime capability metadata is otherwise opaque and may not be used as an
    executable configuration channel.  Concrete adapters still validate this
    persisted value against their administrator-approved endpoint.
    """

    endpoint = capability.metadata.get("endpoint")
    return endpoint.strip() if isinstance(endpoint, str) and endpoint.strip() else None
