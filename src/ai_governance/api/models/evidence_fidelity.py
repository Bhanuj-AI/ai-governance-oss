from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class EvidenceFidelityRequest(BaseModel):
    execution_id: str = Field(min_length=1, max_length=256)
    expected_source_digest: str | None = Field(None, min_length=64, max_length=64)


class EvidenceProjectionResponse(BaseModel):
    source_execution_id: str
    source_artifact_digest: str
    projection_type: str
    projection_version: str
    projection_fingerprint: str
    retained_evidence_types: list[str]
    missing_evidence_types: list[str]
    completeness: str
    event_count: int


class EvidenceFidelityComparisonResponse(BaseModel):
    comparison_id: str
    source_execution_id: str
    request_fingerprint: str
    created_at: datetime
    status: str
    trajectory: EvidenceProjectionResponse | None = None
    runtime_projection: EvidenceProjectionResponse | None = None
    outcome_preserved: bool | None = None
    score_preserved: bool | None = None
    token_usage_preserved: bool | None = None
    duration_preserved: bool | None = None
    action_count_preserved: bool | None = None
    ordering_preserved: bool | None = None
    termination_reason_preserved: bool | None = None
    recovery_sequence_preserved: bool | None = None
    failure_classification_preserved: bool | None = None
    causal_evidence_complete: bool | None = None
    trajectory_classification: str
    runtime_projection_classification: str
    retained_evidence_types: list[str]
    missing_evidence_types: list[str]
    unsupported_conclusions: list[str]
    failure_code: str | None = None
    failure_reason: str | None = None
    provenance: dict[str, str]
