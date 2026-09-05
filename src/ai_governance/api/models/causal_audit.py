from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CausalAuditInterventionRequest(BaseModel):
    strategy: str = Field("REPLACE", description="NULLIFY, REPLACE, or PERTURB.")
    counterfactual_samples: int = Field(3, ge=1, le=10)
    seed: int | None = None
    configuration: dict[str, Any] = Field(default_factory=dict)
    intervention_policy_id: str | None = Field(None, min_length=1, max_length=256)
    intervention_policy_version: int | None = Field(None, ge=1)


class CausalAuditCreateRequest(BaseModel):
    execution_id: str = Field(min_length=1, max_length=256)
    evaluator_ref: str = Field("recorded-outcome/v1", min_length=1, max_length=256)
    intervention: CausalAuditInterventionRequest = Field(
        default_factory=CausalAuditInterventionRequest
    )


class CausalAuditEligibilityResponse(BaseModel):
    code: str
    reason: str
    auditable_tool_call_count: int


class OutcomeScoreResponse(BaseModel):
    value: float
    method: str
    provider: str
    evaluator_version: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CounterfactualReplayLineageResponse(BaseModel):
    replay_id: str
    replay_execution_id: str
    replay_status: str
    policy_id: str
    policy_version: int
    provider_id: str
    provider_version: str
    original_evidence_digest: str
    counterfactual_evidence_reference: str
    counterfactual_evidence_digest: str
    intervention_digest: str
    evaluator_score: OutcomeScoreResponse


class ToolEvidenceInfluenceResponse(BaseModel):
    tool_call_id: str
    tool_name: str
    position: int
    intervention_strategy: str
    intervention_strategy_version: str
    intervention_seed: int | None = None
    counterfactual_count: int
    baseline_score: OutcomeScoreResponse
    counterfactual_score: OutcomeScoreResponse
    influence_score: float
    useful: bool
    harmful: bool
    post_saturation: bool
    counterfactual_replay_ids: list[str] = Field(default_factory=list)
    counterfactual_execution_ids: list[str] = Field(default_factory=list)
    evidence_references: list[str] = Field(default_factory=list)
    intervention_provenance: dict[str, Any] = Field(default_factory=dict)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    counterfactual_lineage: list[CounterfactualReplayLineageResponse] = Field(
        default_factory=list
    )


class CausalAuditResponse(BaseModel):
    audit_id: str
    execution_id: str
    agent_id: str
    status: str
    methodology_version: str
    evaluator_ref: str
    intervention_strategy: str
    counterfactual_samples: int
    intervention_policy_id: str | None = None
    intervention_policy_version: int | None = None
    classification: str | None = None
    failure_code: str | None = None
    failure_reason: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    tool_call_results: list[ToolEvidenceInfluenceResponse] = Field(default_factory=list)


class CausalAuditListResponse(BaseModel):
    items: list[CausalAuditResponse]
    next_offset: int | None = None
