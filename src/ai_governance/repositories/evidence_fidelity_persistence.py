"""JSON persistence mapping for evidence-fidelity records."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ai_governance.domain.evidence_fidelity import (
    EvidenceCompleteness,
    EvidenceConclusion,
    EvidenceFidelityComparison,
    EvidenceFidelityStatus,
    EvidenceProjection,
)


def comparison_to_payload(value: EvidenceFidelityComparison) -> dict[str, Any]:
    return {
        "comparison_id": value.comparison_id,
        "organization_id": value.organization_id,
        "project_id": value.project_id,
        "source_execution_id": value.source_execution_id,
        "request_fingerprint": value.request_fingerprint,
        "created_by": value.created_by,
        "created_at": value.created_at.isoformat(),
        "status": value.status.value,
        "trajectory": _projection_to_payload(value.trajectory),
        "runtime_projection": _projection_to_payload(value.runtime_projection),
        "outcome_preserved": value.outcome_preserved,
        "score_preserved": value.score_preserved,
        "token_usage_preserved": value.token_usage_preserved,
        "duration_preserved": value.duration_preserved,
        "action_count_preserved": value.action_count_preserved,
        "ordering_preserved": value.ordering_preserved,
        "termination_reason_preserved": value.termination_reason_preserved,
        "recovery_sequence_preserved": value.recovery_sequence_preserved,
        "failure_classification_preserved": value.failure_classification_preserved,
        "causal_evidence_complete": value.causal_evidence_complete,
        "trajectory_classification": value.trajectory_classification.value,
        "runtime_projection_classification": value.runtime_projection_classification.value,
        "retained_evidence_types": list(value.retained_evidence_types),
        "missing_evidence_types": list(value.missing_evidence_types),
        "unsupported_conclusions": list(value.unsupported_conclusions),
        "failure_code": value.failure_code,
        "failure_reason": value.failure_reason,
        "provenance": dict(value.provenance),
    }


def comparison_from_payload(payload: dict[str, Any]) -> EvidenceFidelityComparison:
    return EvidenceFidelityComparison(
        comparison_id=payload["comparison_id"],
        organization_id=payload["organization_id"],
        project_id=payload.get("project_id"),
        source_execution_id=payload["source_execution_id"],
        request_fingerprint=payload["request_fingerprint"],
        created_by=payload["created_by"],
        created_at=datetime.fromisoformat(payload["created_at"]),
        status=EvidenceFidelityStatus(payload["status"]),
        trajectory=_projection_from_payload(payload.get("trajectory")),
        runtime_projection=_projection_from_payload(
            payload.get("runtime_projection", payload.get("trace"))
        ),
        outcome_preserved=payload.get("outcome_preserved"),
        score_preserved=payload.get("score_preserved"),
        token_usage_preserved=payload.get("token_usage_preserved"),
        duration_preserved=payload.get("duration_preserved"),
        action_count_preserved=payload.get("action_count_preserved"),
        ordering_preserved=payload.get("ordering_preserved"),
        termination_reason_preserved=payload.get("termination_reason_preserved"),
        recovery_sequence_preserved=payload.get("recovery_sequence_preserved"),
        failure_classification_preserved=payload.get("failure_classification_preserved"),
        causal_evidence_complete=payload.get("causal_evidence_complete"),
        trajectory_classification=EvidenceConclusion(payload["trajectory_classification"]),
        runtime_projection_classification=EvidenceConclusion(
            payload.get(
                "runtime_projection_classification",
                payload.get("trace_classification", "INSUFFICIENT_EVIDENCE"),
            )
        ),
        retained_evidence_types=tuple(payload.get("retained_evidence_types", ())),
        missing_evidence_types=tuple(payload.get("missing_evidence_types", ())),
        unsupported_conclusions=tuple(payload.get("unsupported_conclusions", ())),
        failure_code=payload.get("failure_code"),
        failure_reason=payload.get("failure_reason"),
        provenance=payload.get("provenance", {}),
    )


def _projection_to_payload(value: EvidenceProjection | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "source_execution_id": value.source_execution_id,
        "source_artifact_digest": value.source_artifact_digest,
        "projection_type": value.projection_type,
        "projection_version": value.projection_version,
        "projection_fingerprint": value.projection_fingerprint,
        "retained_evidence_types": list(value.retained_evidence_types),
        "missing_evidence_types": list(value.missing_evidence_types),
        "completeness": value.completeness.value,
        "event_count": value.event_count,
    }


def _projection_from_payload(value: dict[str, Any] | None) -> EvidenceProjection | None:
    if value is None:
        return None
    return EvidenceProjection(
        source_execution_id=value["source_execution_id"],
        source_artifact_digest=value["source_artifact_digest"],
        projection_type=value["projection_type"],
        projection_version=value["projection_version"],
        projection_fingerprint=value["projection_fingerprint"],
        retained_evidence_types=tuple(value.get("retained_evidence_types", ())),
        missing_evidence_types=tuple(value.get("missing_evidence_types", ())),
        completeness=EvidenceCompleteness(value["completeness"]),
        event_count=int(value["event_count"]),
    )
