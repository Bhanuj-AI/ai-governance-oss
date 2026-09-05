"""REST DTOs for governed counterfactual intervention policies."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class EvidenceInterventionPolicyCreateRequest(BaseModel):
    tool_name: str = Field(min_length=1, max_length=256)
    schema_id: str = Field(min_length=1, max_length=256)
    schema_version: str = Field(min_length=1, max_length=128)
    provider_id: str = Field("structured-json", min_length=1, max_length=128)
    provider_version: str = Field("v1", min_length=1, max_length=128)
    allowed_strategies: list[str] = Field(min_length=1)
    strategy_configuration: dict[str, Any] = Field(default_factory=dict)


class EvidenceInterventionPolicyEditRequest(BaseModel):
    strategy_configuration: dict[str, Any] = Field(default_factory=dict)


class EvidenceInterventionPolicyResponse(BaseModel):
    policy_id: str
    version: int
    status: str
    tool_name: str
    schema_id: str
    schema_version: str
    provider_id: str
    provider_version: str
    allowed_strategies: list[str]
    strategy_configuration: dict[str, Any]
    policy_digest: str
    created_at: datetime
    created_by: str
    activated_at: datetime | None = None
    activated_by: str | None = None
    retired_at: datetime | None = None


class EvidenceInterventionPolicyListResponse(BaseModel):
    items: list[EvidenceInterventionPolicyResponse]


class EvidenceInterventionPolicyPreviewRequest(BaseModel):
    execution_id: str = Field(min_length=1, max_length=256)
    tool_call_id: str = Field(min_length=1, max_length=256)
    strategy: str = Field("REPLACE", min_length=1, max_length=32)
    seed: int = 0


class EvidenceInterventionPolicyPreviewResponse(BaseModel):
    strategy: str
    policy_id: str
    policy_version: int
    provider_id: str
    provider_version: str
    seed: int
    original_evidence_digest: str
    counterfactual_evidence_ref: str
    counterfactual_evidence_digest: str
    schema_valid: bool
    semantic_valid: bool
    material_difference: bool
    generation_metadata: dict[str, Any] = Field(default_factory=dict)
