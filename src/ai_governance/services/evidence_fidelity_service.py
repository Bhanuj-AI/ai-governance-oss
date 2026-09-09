"""Compare the authoritative Agent Runtime event stream with its graph view."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from ai_governance.domain.agent_execution import AgentExecutionEvent, EventType
from ai_governance.domain.evidence_fidelity import (
    EvidenceCompleteness,
    EvidenceConclusion,
    EvidenceFidelityComparison,
    EvidenceFidelityStatus,
    EvidenceProjection,
)
from ai_governance.repositories.agent_execution_repository import (
    AgentExecutionEventRepository,
    AgentExecutionRepository,
)
from ai_governance.repositories.evidence_fidelity_repository import (
    EvidenceFidelityComparisonRepository,
)
from ai_governance.tenancy.domain import TenantContext


class EvidenceFidelityError(ValueError):
    """Fail-closed error with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class EvidenceFidelityNotFound(EvidenceFidelityError):
    def __init__(self, comparison_id: str) -> None:
        super().__init__("NOT_FOUND", f"Evidence-fidelity comparison '{comparison_id}' was not found.")


_ALL_TRAJECTORY_TYPES = {
    "execution_identity", "sample_identity", "ordered_events", "actor_identity",
    "observation_evidence", "tool_action", "tool_arguments_reference",
    "tool_response_reference", "error_timeout", "retry_recovery", "termination",
    "timestamps_duration", "token_usage", "runner_model_scaffold_provenance",
    "source_artifact_digest", "schema_version", "score",
}
_TRACE_RETAINED = {
    "execution_identity", "actor_identity", "tool_action", "termination",
    "timestamps_duration", "runner_model_scaffold_provenance",
}


class EvidenceFidelityService:
    """Build deterministic views without copying or reinterpreting source events.

    The second view deliberately models the currently deployed runtime ontology
    projection: it aggregates model/tool/resource relationships and does not
    preserve an ordered span/event timeline.
    """

    TRAJECTORY_VERSION = "observable-trajectory/v1"
    RUNTIME_PROJECTION_VERSION = "runtime-ontology-projection/v1"

    def __init__(
        self,
        comparison_repository: EvidenceFidelityComparisonRepository,
        execution_repository: AgentExecutionRepository,
        event_repository: AgentExecutionEventRepository,
        *,
        clock: Any | None = None,
    ) -> None:
        self._comparisons = comparison_repository
        self._executions = execution_repository
        self._events = event_repository
        self._clock = clock or (lambda: datetime.now(UTC))

    def request(
        self,
        execution_id: str,
        context: TenantContext,
        *,
        expected_source_digest: str | None = None,
    ) -> EvidenceFidelityComparison:
        execution, events = self._source(execution_id, context)
        source_digest = _source_digest(execution, events)
        fingerprint = _digest({
            "execution_id": execution_id,
            "source_digest": source_digest,
            "expected_source_digest": expected_source_digest,
            "trajectory_version": self.TRAJECTORY_VERSION,
            "runtime_projection_version": self.RUNTIME_PROJECTION_VERSION,
        })
        existing = self._comparisons.find_by_fingerprint(
            fingerprint, context.organization_id, context.project_id
        )
        if existing is not None:
            return existing
        if expected_source_digest and expected_source_digest != source_digest:
            return self._save_failure(
                execution_id, context, fingerprint, "SOURCE_DIGEST_MISMATCH",
                "The supplied source artifact digest does not match persisted execution evidence.",
            )
        try:
            self._validate_source(execution, events)
            trajectory = _trajectory_projection(execution, events, source_digest)
            runtime_projection = _runtime_projection(execution, events, source_digest)
            comparison = _comparison(
                comparison_id=str(uuid4()), context=context, execution_id=execution_id,
                fingerprint=fingerprint, trajectory=trajectory,
                runtime_projection=runtime_projection,
            )
        except EvidenceFidelityError as error:
            comparison = self._failure(
                execution_id, context, fingerprint, error.code, str(error)
            )
        return self._comparisons.save(comparison)

    def get(self, comparison_id: str, context: TenantContext) -> EvidenceFidelityComparison:
        value = self._comparisons.get(
            comparison_id, context.organization_id, context.project_id
        )
        if value is None:
            raise EvidenceFidelityNotFound(comparison_id)
        return value

    def list_for_execution(
        self, execution_id: str, context: TenantContext
    ) -> list[EvidenceFidelityComparison]:
        return self._comparisons.list_for_execution(
            execution_id, context.organization_id, context.project_id
        )

    def _source(self, execution_id: str, context: TenantContext):
        execution = self._executions.get(
            execution_id, context.organization_id, context.project_id
        )
        if execution is None:
            raise EvidenceFidelityError("SOURCE_EXECUTION_UNAVAILABLE", "Source execution is unavailable in the current tenant scope.")
        events = self._events.list_by_execution(
            execution_id, context.organization_id, context.project_id
        )
        return execution, events

    def _validate_source(self, execution: Any, events: list[AgentExecutionEvent]) -> None:
        if not events:
            raise EvidenceFidelityError("SOURCE_ARTIFACT_MISSING", "Source execution has no durable event evidence.")
        expected = list(range(len(events)))
        if [event.sequence_number for event in events] != expected:
            raise EvidenceFidelityError("EVENT_ORDER_UNAVAILABLE", "Persisted event sequence is not contiguous and cannot support a deterministic trajectory.")
        if any(event.event_schema_version != "1" for event in events):
            raise EvidenceFidelityError("EVENT_SCHEMA_UNSUPPORTED", "The source event schema version is unsupported for fidelity analysis.")
        if events[0].event_type is not EventType.EXECUTION_STARTED or events[-1].event_type is not EventType.EXECUTION_COMPLETED:
            raise EvidenceFidelityError("SOURCE_EVIDENCE_INCOMPLETE", "A trajectory requires durable start and terminal execution events.")
        if not execution.is_terminal:
            raise EvidenceFidelityError("SOURCE_EVIDENCE_INCOMPLETE", "A trajectory cannot be compared before the execution is terminal.")

    def _save_failure(self, execution_id: str, context: TenantContext, fingerprint: str, code: str, reason: str) -> EvidenceFidelityComparison:
        existing = self._comparisons.find_by_fingerprint(fingerprint, context.organization_id, context.project_id)
        if existing is not None:
            return existing
        return self._comparisons.save(self._failure(execution_id, context, fingerprint, code, reason))

    def _failure(self, execution_id: str, context: TenantContext, fingerprint: str, code: str, reason: str) -> EvidenceFidelityComparison:
        return EvidenceFidelityComparison(
            comparison_id=str(uuid4()), organization_id=context.organization_id,
            project_id=context.project_id, source_execution_id=execution_id,
            request_fingerprint=fingerprint, created_by=context.actor_id,
            created_at=self._clock(), status=EvidenceFidelityStatus.FAILED,
            failure_code=code, failure_reason=reason,
            unsupported_conclusions=("ALL_CONCLUSIONS_INSUFFICIENT_EVIDENCE",),
            provenance={"analysis_version": self.TRAJECTORY_VERSION},
        )


def _trajectory_projection(execution: Any, events: list[AgentExecutionEvent], source_digest: str) -> EvidenceProjection:
    available = _available_types(execution, events)
    missing = sorted(_ALL_TRAJECTORY_TYPES - available)
    return EvidenceProjection(
        source_execution_id=execution.execution_id, source_artifact_digest=source_digest,
        projection_type="full_observable_trajectory", projection_version="1",
        projection_fingerprint=_digest({"kind": "trajectory", "source": source_digest, "events": [_event_payload(event) for event in events]}),
        retained_evidence_types=tuple(sorted(available)), missing_evidence_types=tuple(missing),
        completeness=EvidenceCompleteness.COMPLETE if not missing else EvidenceCompleteness.INCOMPLETE,
        event_count=len(events),
    )


def _runtime_projection(execution: Any, events: list[AgentExecutionEvent], source_digest: str) -> EvidenceProjection:
    available = _available_types(execution, events)
    retained = available & _TRACE_RETAINED
    missing = sorted(_ALL_TRAJECTORY_TYPES - retained)
    # Match the real Neo4j projection's relationship-level aggregation.  In
    # particular, event order, causation and evidence references are not nodes
    # or relationship properties in that projection.
    graph_events = [
        {"type": event.event_type.value, "model": event.attributes.get("model") or event.attributes.get("model_reference"), "tool": event.attributes.get("tool") or event.attributes.get("tool_id") or event.attributes.get("tool_identity"), "resources": list(event.resource_references)}
        for event in events
        if event.event_type in {EventType.MODEL_CALL, EventType.TOOL_CALL, EventType.GOVERNANCE_DECISION, EventType.EVALUATION}
    ]
    return EvidenceProjection(
        source_execution_id=execution.execution_id, source_artifact_digest=source_digest,
        projection_type="runtime_ontology_projection", projection_version="1",
        projection_fingerprint=_digest({"kind": "runtime-ontology", "source": source_digest, "execution": {"status": execution.status.value, "agent": execution.agent_id}, "relationships": graph_events}),
        retained_evidence_types=tuple(sorted(retained)), missing_evidence_types=tuple(missing),
        completeness=EvidenceCompleteness.INCOMPLETE, event_count=len(graph_events),
    )


def _comparison(*, comparison_id: str, context: TenantContext, execution_id: str, fingerprint: str, trajectory: EvidenceProjection, runtime_projection: EvidenceProjection) -> EvidenceFidelityComparison:
    trajectory_types, runtime_types = set(trajectory.retained_evidence_types), set(runtime_projection.retained_evidence_types)

    def runtime_has(name: str) -> bool:
        return name in runtime_types
    required_for_causal = {"ordered_events", "observation_evidence", "tool_response_reference", "retry_recovery", "source_artifact_digest"}
    unsupported = [
        label for label, required in {
            "score": "score", "token_usage": "token_usage", "event_ordering": "ordered_events",
            "evidence_before_action": "observation_evidence", "retry_recovery": "retry_recovery",
            "failure_classification": "error_timeout", "causal_evidence": "tool_response_reference",
        }.items() if required not in runtime_types
    ]
    return EvidenceFidelityComparison(
        comparison_id=comparison_id, organization_id=context.organization_id,
        project_id=context.project_id, source_execution_id=execution_id,
        request_fingerprint=fingerprint, created_by=context.actor_id,
        created_at=datetime.now(UTC), status=EvidenceFidelityStatus.SUCCEEDED,
        trajectory=trajectory, runtime_projection=runtime_projection,
        outcome_preserved=runtime_has("termination"),
        score_preserved=runtime_has("score"),
        token_usage_preserved=runtime_has("token_usage"),
        duration_preserved=runtime_has("timestamps_duration"),
        action_count_preserved=runtime_has("tool_action"),
        ordering_preserved=runtime_has("ordered_events"),
        termination_reason_preserved=runtime_has("termination"),
        recovery_sequence_preserved=runtime_has("retry_recovery"),
        failure_classification_preserved=runtime_has("error_timeout"),
        causal_evidence_complete=required_for_causal <= runtime_types,
        trajectory_classification=EvidenceConclusion.SUPPORTED if trajectory.completeness is EvidenceCompleteness.COMPLETE else EvidenceConclusion.INSUFFICIENT_EVIDENCE,
        runtime_projection_classification=EvidenceConclusion.SUPPORTED if required_for_causal <= runtime_types else EvidenceConclusion.INSUFFICIENT_EVIDENCE,
        retained_evidence_types=tuple(sorted(trajectory_types & runtime_types)),
        missing_evidence_types=tuple(sorted(trajectory_types - runtime_types)),
        unsupported_conclusions=tuple(unsupported),
        provenance={"trajectory_projection": trajectory.projection_type, "runtime_projection": runtime_projection.projection_type, "analysis_version": "evidence-fidelity/v1"},
    )


def _available_types(execution: Any, events: list[AgentExecutionEvent]) -> set[str]:
    available = {"execution_identity", "ordered_events", "actor_identity", "timestamps_duration", "termination", "source_artifact_digest", "schema_version"}
    if execution.metadata.get("sample_id") is not None:
        available.add("sample_identity")
    if execution.metadata.get("runner_provenance"):
        available.add("runner_model_scaffold_provenance")
    for event in events:
        attributes = event.attributes
        if event.evidence_references:
            available.update({"observation_evidence", "tool_response_reference"})
        if event.event_type is EventType.TOOL_CALL:
            available.add("tool_action")
            if attributes.get("arguments_digest") or attributes.get("arguments_reference"):
                available.add("tool_arguments_reference")
        if event.event_type is EventType.ERROR or attributes.get("timeout"):
            available.add("error_timeout")
        if attributes.get("retry_of") or attributes.get("recovery_of"):
            available.add("retry_recovery")
        if any(key in attributes for key in ("input_tokens", "output_tokens", "total_tokens")):
            available.add("token_usage")
        if "score" in attributes:
            available.add("score")
    return available


def _source_digest(execution: Any, events: list[AgentExecutionEvent]) -> str:
    return _digest({"execution": {"id": execution.execution_id, "status": execution.status.value, "started_at": execution.started_at.isoformat(), "completed_at": execution.completed_at.isoformat() if execution.completed_at else None, "metadata": _safe_metadata(execution.metadata)}, "events": [_event_payload(event) for event in events]})


def _event_payload(event: AgentExecutionEvent) -> dict[str, Any]:
    return {"event_id": event.event_id, "type": event.event_type.value, "sequence": event.sequence_number, "occurred_at": event.occurred_at.isoformat(), "received_at": event.received_at.isoformat(), "actor_id": event.actor_id, "actor_type": event.actor_type.value if event.actor_type else None, "correlation_id": event.correlation_id, "causation_id": event.causation_id, "resource_references": list(event.resource_references), "evidence_references": list(event.evidence_references), "attributes": _safe_metadata(event.attributes), "schema": event.event_schema_version}


def _safe_metadata(value: Any) -> Any:
    prohibited = {"prompt", "response", "message", "reasoning", "chain_of_thought", "tool_payload", "tool_output", "tool_arguments", "token", "api_key", "credential"}
    if isinstance(value, dict) or hasattr(value, "items"):
        return {str(key): _safe_metadata(item) for key, item in value.items() if str(key).lower() not in prohibited}
    if isinstance(value, (list, tuple)):
        return [_safe_metadata(item) for item in value]
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
