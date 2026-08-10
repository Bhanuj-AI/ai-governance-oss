from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from ai_governance.api.models.ontology_graph import GraphSubgraphResponse


class DecisionEvaluateRequest(BaseModel):
    """
    REST request body for evaluating a governance decision.
    """

    target_type: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    decision_type: str = Field(min_length=1)
    policy_ids: list[str] = Field(default_factory=list)
    correlation_id: str | None = None
    request_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "target_type",
        "target_id",
        "decision_type",
        "correlation_id",
        "request_id",
    )
    @classmethod
    def string_must_not_be_blank(
        cls,
        value: str | None,
    ) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Decision request string fields must not be blank.")
        return value

    @field_validator("policy_ids")
    @classmethod
    def policy_ids_must_not_be_blank(
        cls,
        value: list[str],
    ) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("Decision policy_ids must not contain blanks.")
        return value


class DecisionTargetResponse(BaseModel):
    target_type: str
    target_id: str


class DecisionEvidenceReferenceResponse(BaseModel):
    evidence_type: str
    evidence_id: str
    relationship_type: str | None = None
    source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DecisionPolicyReferenceResponse(BaseModel):
    policy_id: str
    policy_version: str
    policy_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DecisionProvenanceResponse(BaseModel):
    producer_type: str
    producer_id: str
    actor_id: str | None = None
    correlation_id: str | None = None
    request_id: str | None = None
    created_at: datetime


class DecisionSupersessionResponse(BaseModel):
    supersedes_decision_id: str | None = None
    superseded_by_decision_id: str | None = None
    supersession_reason: str | None = None


class DecisionAuditRecordResponse(BaseModel):
    audit_id: str
    decision_id: str
    action: str
    producer_id: str
    reason: str
    actor_id: str | None = None
    correlation_id: str | None = None
    request_id: str | None = None
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class DecisionResponse(BaseModel):
    decision_id: str
    decision_type: str
    status: str
    target: DecisionTargetResponse
    reason: str
    confidence: str
    evidence: list[DecisionEvidenceReferenceResponse]
    policies: list[DecisionPolicyReferenceResponse]
    provenance: DecisionProvenanceResponse
    supersession: DecisionSupersessionResponse
    metadata: dict[str, Any] = Field(default_factory=dict)
    finalized_at: datetime | None = None
    archived_at: datetime | None = None


class MissingEvidenceResponse(BaseModel):
    evidence_type: str
    reason: str
    severity: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceNodeResponse(BaseModel):
    entity_type: str
    entity_id: str
    label: str | None = None
    lifecycle: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceEdgeResponse(BaseModel):
    relationship_type: str
    source_type: str
    source_id: str
    target_type: str
    target_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class DecisionEvidenceGraphResponse(BaseModel):
    target_type: str
    target_id: str
    nodes: list[EvidenceNodeResponse]
    edges: list[EvidenceEdgeResponse]
    missing: list[MissingEvidenceResponse]
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReasoningEvidenceSummaryResponse(BaseModel):
    target_type: str
    target_id: str
    metric_scores: dict[str, float] = Field(default_factory=dict)
    metric_failures: list[str] = Field(default_factory=list)
    threshold_breaches: list[str] = Field(default_factory=list)
    drift_severity: str | None = None
    latest_job_status: str | None = None
    latest_audit_status: str | None = None
    evaluation_result_ids: list[str] = Field(default_factory=list)
    metric_ids: list[str] = Field(default_factory=list)
    drift_analysis_ids: list[str] = Field(default_factory=list)
    leaderboard_ids: list[str] = Field(default_factory=list)
    job_ids: list[str] = Field(default_factory=list)
    mcp_audit_ids: list[str] = Field(default_factory=list)
    policy_ids: list[str] = Field(default_factory=list)
    missing_evidence: list[MissingEvidenceResponse] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolicyOutcomeResponse(BaseModel):
    policy_id: str
    policy_version: str
    matched_rule_id: str | None = None
    effect: str
    reason: str
    matched: bool
    metadata: dict[str, Any] = Field(default_factory=dict)


class DecisionExplanationResponse(BaseModel):
    decision_id: str
    summary: str
    reasons: list[str]
    evidence_references: list[DecisionEvidenceReferenceResponse]
    policy_references: list[DecisionPolicyReferenceResponse]
    missing_evidence: list[MissingEvidenceResponse]
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReasoningOutcomeResponse(BaseModel):
    decision: DecisionResponse
    explanation: DecisionExplanationResponse
    evidence_summary: ReasoningEvidenceSummaryResponse
    policy_outcomes: list[PolicyOutcomeResponse]


class DecisionDetailResponse(BaseModel):
    decision: DecisionResponse
    evidence_summary: ReasoningEvidenceSummaryResponse
    policy_outcomes: list[PolicyOutcomeResponse]
    audit_records: list[DecisionAuditRecordResponse]


class DecisionListResponse(BaseModel):
    decisions: list[DecisionResponse]


class DecisionEvidenceResponse(BaseModel):
    decision_id: str
    evidence_references: list[DecisionEvidenceReferenceResponse]
    evidence_graph: DecisionEvidenceGraphResponse


class DecisionLineageResponse(BaseModel):
    decision: DecisionResponse
    subgraph: GraphSubgraphResponse
