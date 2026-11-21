"""Bridge explicit Agents Runtime replay capability into the Replay Plane."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from ai_governance.domain.agent_execution import (
    AgentExecution,
    AgentExecutionEvent,
    AgentExecutionStatus,
    AgentRuntimeReplayCapability,
    EventType,
    EvidenceOnlyReplayCapability,
)
from ai_governance.domain.replay import (
    ControlledEvidenceStrategy,
    ReplayManifest,
    ReplayManifestEligibility,
    ReplayManifestReason,
    ReplayManifestReasonCode,
)
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.services.replay_execution import ReplayExecutionContext
from ai_governance.spi.replay import (
    RUNTIME_REPLAY_SOURCE_SCHEMA_VERSION,
    EvidenceResolutionPlan,
    ExecutionReplayCapability,
    ReplayEvidenceBinding,
    ReplayToolCall,
    ReplayToolCallKind,
    RuntimeReplaySource,
    ToolArgumentDigest,
)
from ai_governance.tenancy.domain import TenantContext


class AgentRuntimeReplayNotAvailable(ValueError):
    """The observed execution lacks an explicit, safe replay capability."""


class InvalidEvidenceOnlyReplayCapability(AgentRuntimeReplayNotAvailable):
    """The runtime supplied an unsupported evidence-only capability."""


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
    replay_manifest: ReplayManifest | None = None
    runtime_replay_source: RuntimeReplaySource | None = None
    execution_replay_plan: EvidenceResolutionPlan | None = None


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
        replay_manifest = self.manifest(execution, events, context)
        if not replay_manifest.is_eligible:
            raise AgentRuntimeReplayNotAvailable(replay_manifest.reasons[0].message)
        capability, tool_calls = self.validate(execution, events, context)
        runtime_replay_source = RuntimeReplaySource(
            source_agent_execution_id=execution.execution_id,
            external_execution_id=execution.external_execution_id,
            runtime_type=capability.runtime_type,
            adapter_id=capability.adapter_id,
            adapter_version=capability.adapter_version,
            replay_reference=capability.replay_reference,
            isolation_guarantee=capability.isolation_guarantee or "",
            manifest_hash=replay_manifest.manifest_hash,
        )
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
                "evidence_only_replay_capability": (
                    capability.evidence_only_replay_capability.to_metadata()
                    if capability.evidence_only_replay_capability is not None
                    else None
                ),
                },
                "runtime_replay_source": runtime_replay_source.to_payload(),
            },
            metadata={
                "source_agent_execution_id": execution.execution_id,
                "external_execution_id": execution.external_execution_id,
                "replay_manifest": replay_manifest.to_dict(),
                "runtime_replay_source_schema_version": (
                    RUNTIME_REPLAY_SOURCE_SCHEMA_VERSION
                ),
            },
            created_at=datetime.now(UTC),
        )
        self._source_store.save(source)
        return PreparedAgentRuntimeReplay(
            source,
            capability,
            tuple(event.event_id for event in tool_calls),
            replay_manifest,
            runtime_replay_source,
            _execution_replay_plan(
                capability, tool_calls, replay_manifest, context
            ),
        )

    def manifest(
        self,
        execution: AgentExecution,
        events: list[AgentExecutionEvent],
        context: TenantContext,
    ) -> ReplayManifest:
        """Classify immutable runtime evidence without creating a replay.

        A terminal FAILED execution is intentionally assessed like a succeeded
        one. The decision is based on frozen capability, isolation, and
        evidence bindings, never on a receipt claiming success.
        """

        reasons: list[ReplayManifestReason] = []
        if (
            execution.organization_id != context.organization_id
            or execution.project_id != context.project_id
        ):
            reasons.append(
                ReplayManifestReason(
                    ReplayManifestReasonCode.TENANT_SCOPE_MISMATCH,
                    "Observed execution is outside the current tenant scope.",
                )
            )
        if execution.status not in {
            AgentExecutionStatus.SUCCEEDED,
            AgentExecutionStatus.FAILED,
        }:
            reasons.append(
                ReplayManifestReason(
                    ReplayManifestReasonCode.EXECUTION_NOT_TERMINAL,
                    "Only succeeded or failed executions can provide a stable replay manifest.",
                )
            )

        raw_capability = execution.metadata.get("replay_capability")
        capability: AgentRuntimeReplayCapability | None = None
        if raw_capability is None:
            reasons.append(
                ReplayManifestReason(
                    ReplayManifestReasonCode.MISSING_REPLAY_CAPABILITY,
                    "Observed execution has no explicit replay capability.",
                )
            )
        elif not isinstance(raw_capability, Mapping):
            reasons.append(
                ReplayManifestReason(
                    ReplayManifestReasonCode.INVALID_REPLAY_CAPABILITY,
                    "Observed execution replay capability is invalid.",
                )
            )
        else:
            try:
                capability = _capability_from_metadata(execution.metadata)
            except InvalidEvidenceOnlyReplayCapability:
                reasons.append(
                    ReplayManifestReason(
                        ReplayManifestReasonCode.INVALID_EVIDENCE_ONLY_REPLAY_CAPABILITY,
                        "Observed execution evidence-only replay capability is invalid.",
                    )
                )
            except (TypeError, ValueError):
                reasons.append(
                    ReplayManifestReason(
                        ReplayManifestReasonCode.INVALID_REPLAY_CAPABILITY,
                        "Observed execution replay capability is invalid.",
                    )
                )

        if capability is not None and capability.isolation_guarantee is None:
            reasons.append(
                ReplayManifestReason(
                    ReplayManifestReasonCode.MISSING_ISOLATION_GUARANTEE,
                    "Replay capability does not declare a versioned isolation guarantee.",
                )
            )
        if capability is not None and capability.evidence_only_replay_capability is None:
            reasons.append(
                ReplayManifestReason(
                    ReplayManifestReasonCode.MISSING_EVIDENCE_ONLY_REPLAY_CAPABILITY,
                    "Replay capability does not declare evidence-only replay safety.",
                )
            )

        tool_calls = [event for event in events if event.event_type is EventType.TOOL_CALL]
        evidence_reference_count = sum(
            len(event.evidence_references) for event in tool_calls
        )
        if any(event.execution_id != execution.execution_id for event in events):
            reasons.append(
                ReplayManifestReason(
                    ReplayManifestReasonCode.TOOL_CALL_GRAPH_INVALID,
                    "Replay evidence contains an event outside the observed execution.",
                )
            )
        if any(event.tool_call_context is None for event in tool_calls):
            reasons.append(
                ReplayManifestReason(
                    ReplayManifestReasonCode.TOOL_CALL_IDENTITY_MISSING,
                    "A replay-relevant tool call lacks a runtime_tool_call_id.",
                )
            )
        if any(not event.evidence_references for event in tool_calls):
            reasons.append(
                ReplayManifestReason(
                    ReplayManifestReasonCode.EVIDENCE_REFERENCE_MISSING,
                    "A tool call is missing a durable evidence reference.",
                )
            )
        identified_calls = [
            event for event in tool_calls if event.tool_call_context is not None
        ]
        if identified_calls:
            try:
                _validate_tool_call_graph(identified_calls)
            except AgentRuntimeReplayNotAvailable as error:
                reasons.append(
                    ReplayManifestReason(
                        ReplayManifestReasonCode.TOOL_CALL_GRAPH_INVALID,
                        str(error),
                    )
                )

        return ReplayManifest(
            source_execution_id=execution.execution_id,
            source_execution_status=execution.status.value,
            eligibility=(
                ReplayManifestEligibility.ELIGIBLE
                if not reasons
                else ReplayManifestEligibility.INELIGIBLE
            ),
            tool_call_count=len(tool_calls),
            evidence_reference_count=evidence_reference_count,
            reasons=tuple(reasons),
            runtime_type=capability.runtime_type if capability else None,
            adapter_id=capability.adapter_id if capability else None,
            adapter_version=capability.adapter_version if capability else None,
            replay_reference=capability.replay_reference if capability else None,
            isolation_guarantee=(
                capability.isolation_guarantee if capability else None
            ),
        )

    def validate(
        self,
        execution: AgentExecution,
        events: list[AgentExecutionEvent],
        context: TenantContext,
    ) -> tuple[AgentRuntimeReplayCapability, list[AgentExecutionEvent]]:
        """Verify capability and evidence without persisting a Replay source."""
        replay_manifest = self.manifest(execution, events, context)
        if not replay_manifest.is_eligible:
            raise AgentRuntimeReplayNotAvailable(replay_manifest.reasons[0].message)
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
        _validate_runtime_replay_source(context, self.name)
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
        safety_metadata = {}
        if context.runtime_replay_source is not None:
            safety_metadata = {
                "evidence_only_replay_safety": {
                    "schema_version": "evidence-only-replay-safety/v1",
                    "capability_schema_version": "evidence-only-replay-capability/v1",
                    "replay_manifest_hash": context.runtime_replay_source.manifest_hash,
                    "isolation_guarantee": context.runtime_replay_source.isolation_guarantee,
                    "intervention_digest": intervention.intervention_digest,
                    "runtime_tool_call_id": runtime_tool_call_id,
                    "private_snapshot_integrity_verified": True,
                    "unobserved_tool_call_count": 0,
                    "external_side_effects_performed": False,
                }
            }
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
                **safety_metadata,
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
            isolation_guarantee=_optional_string(raw.get("isolation_guarantee")),
            evidence_only_replay_capability=(
                _evidence_only_replay_capability(
                    raw.get("evidence_only_replay_capability")
                )
                if raw.get("evidence_only_replay_capability") is not None
                else None
            ),
            metadata=raw.get("metadata", {}),
        )
    except InvalidEvidenceOnlyReplayCapability:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise AgentRuntimeReplayNotAvailable(
            "Observed execution replay capability is invalid."
        ) from error


def _evidence_only_replay_capability(value: object) -> EvidenceOnlyReplayCapability:
    try:
        return EvidenceOnlyReplayCapability.from_metadata(value)
    except (TypeError, ValueError) as error:
        raise InvalidEvidenceOnlyReplayCapability(
            "Observed execution lacks a valid evidence-only replay capability."
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


def _execution_replay_plan(
    capability: AgentRuntimeReplayCapability,
    tool_calls: list[AgentExecutionEvent],
    replay_manifest: ReplayManifest,
    context: TenantContext,
) -> EvidenceResolutionPlan | None:
    """Build an opt-in Phase 2 plan from bounded observed tool identities.

    A runtime advertises the public ``ExecutionReplayCapability`` under its
    replay-capability metadata. Each replay-relevant tool event then supplies
    only its canonical identity and argument *digest* in the evidence
    descriptor metadata. Raw arguments and private evidence values never enter
    the control plane. Runtimes that do not opt in retain the existing
    reference-replay path unchanged.
    """

    raw_capability = capability.metadata.get("execution_replay_capability")
    if raw_capability is None:
        return None
    if not isinstance(raw_capability, Mapping):
        raise AgentRuntimeReplayNotAvailable(
            "Execution replay capability must be a bounded object."
        )
    try:
        execution_capability = ExecutionReplayCapability.from_payload(raw_capability)
    except (TypeError, ValueError) as error:
        raise AgentRuntimeReplayNotAvailable(
            "Execution replay capability is invalid."
        ) from error

    event_by_runtime_id = {
        event.tool_call_context.runtime_tool_call_id: event
        for event in tool_calls
        if event.tool_call_context is not None
    }
    planned_calls: list[ReplayToolCall] = []
    evidence_bindings: list[ReplayEvidenceBinding] = []
    for event in tool_calls:
        context_data = event.tool_call_context
        if context_data is None:
            raise AgentRuntimeReplayNotAvailable(
                "Execution replay tool call lacks a runtime identity."
            )
        descriptor = _evidence_descriptor(event)
        metadata = descriptor.get("metadata")
        identity = (
            metadata.get("execution_replay_tool_identity")
            if isinstance(metadata, Mapping)
            else None
        )
        if not isinstance(identity, Mapping):
            raise AgentRuntimeReplayNotAvailable(
                "Execution replay tool call lacks a canonical tool identity."
            )
        retry_runtime_id = identity.get("retry_of_runtime_tool_call_id")
        try:
            argument_digest = ToolArgumentDigest.from_payload(
                _mapping(identity, "argument_digest")
            )
            tool_symbol = _string(identity, "tool_symbol")
            if tool_symbol != _string(descriptor, "tool_name"):
                raise ValueError("Tool identity does not match evidence descriptor.")
            dependencies = tuple(
                event_by_runtime_id[dependency].event_id
                for dependency in context_data.depends_on_tool_call_ids
            )
            retry_of_call_id = (
                event_by_runtime_id[retry_runtime_id].event_id
                if isinstance(retry_runtime_id, str)
                else None
            )
            planned = ReplayToolCall(
                call_id=event.event_id,
                kind=ReplayToolCallKind.PLANNED,
                scope_id=_string(identity, "scope_id"),
                tool_symbol=tool_symbol,
                tool_schema_version=_string(identity, "tool_schema_version"),
                argument_digest=argument_digest,
                occurrence=_integer(identity, "occurrence"),
                dependency_call_ids=dependencies,
                retry_of_call_id=retry_of_call_id,
                evidence_reference=_string(descriptor, "evidence_ref"),
                response_digest=_string(descriptor, "evidence_digest"),
            )
            if planned.evidence_reference not in event.evidence_references:
                raise ValueError("Evidence descriptor is not bound to the tool event.")
            binding = ReplayEvidenceBinding(
                planned.call_id,
                planned.evidence_reference,
                planned.response_digest,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise AgentRuntimeReplayNotAvailable(
                "Execution replay tool identity is invalid."
            ) from error
        planned_calls.append(planned)
        evidence_bindings.append(binding)

    try:
        return EvidenceResolutionPlan(
            organization_id=context.organization_id,
            project_id=context.project_id or "",
            source_execution_id=replay_manifest.source_execution_id,
            replay_manifest_hash=replay_manifest.manifest_hash,
            capability=execution_capability,
            planned_calls=tuple(planned_calls),
            evidence_bindings=tuple(evidence_bindings),
        )
    except (TypeError, ValueError) as error:
        raise AgentRuntimeReplayNotAvailable(
            "Execution replay plan is invalid."
        ) from error


def _evidence_descriptor(event: AgentExecutionEvent) -> Mapping[str, object]:
    replay = event.attributes.get("causal_replay")
    descriptor = (
        replay.get("evidence_descriptor") if isinstance(replay, Mapping) else None
    )
    if not isinstance(descriptor, Mapping):
        raise AgentRuntimeReplayNotAvailable(
            "Execution replay tool call lacks an evidence descriptor."
        )
    return descriptor


def _mapping(value: Mapping[str, object], name: str) -> Mapping[str, object]:
    raw = value.get(name)
    if not isinstance(raw, Mapping):
        raise TypeError(f"{name} must be an object.")
    return raw


def _string(value: Mapping[str, object], name: str) -> str:
    raw = value.get(name)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{name} must be a non-blank string.")
    return raw


def _integer(value: Mapping[str, object], name: str) -> int:
    raw = value.get(name)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise TypeError(f"{name} must be an integer.")
    return raw


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


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _validate_runtime_replay_source(
    context: ReplayExecutionContext, adapter_name: str
) -> RuntimeReplaySource | None:
    """Validate a typed source when the host is executing a v1 runtime replay.

    Older generic and Agent Runtime sources do not carry this additive context
    and remain compatible. The replay handler rejects a missing envelope for
    new bridge-produced sources before reaching an adapter.
    """

    source = context.runtime_replay_source
    if source is None:
        return None
    if source.adapter_id != adapter_name:
        raise AgentRuntimeReplayNotAvailable(
            "Runtime replay source adapter identity does not match this adapter."
        )
    if not source.manifest_hash:
        raise AgentRuntimeReplayNotAvailable(
            "Runtime replay source is missing its manifest binding."
        )
    return source
