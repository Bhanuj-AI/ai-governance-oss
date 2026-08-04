from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ReplayCreateRequest(BaseModel):
    source_execution_id: str = Field(min_length=1)
    mode: str = "FULL"
    configuration_source: str = "ORIGINAL"
    idempotency_key: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None
    dry_run: bool = False


class ReplayArchiveRequest(BaseModel):
    reason: str = Field(min_length=1)


class ReplayFailureResponse(BaseModel):
    code: str
    message: str
    stage: str
    details: dict[str, Any]
    occurred_at: datetime


class ReplayConfigurationResponse(BaseModel):
    workflow_id: str
    workflow_version: str
    execution_adapter: str
    input_snapshot_ref: str
    state_snapshot_ref: str
    artifact_refs: list[str]
    prompt_refs: list[str]
    model_refs: list[str]
    dataset_refs: list[str]
    policy_refs: list[str]
    runtime_parameters: dict[str, Any]
    configuration_source: str
    resolved_at: datetime | None
    configuration_hash: str


class ReplayExecutionSearchItemResponse(BaseModel):
    """Safe discovery projection of a historical execution."""

    execution_id: str
    workflow_id: str
    workflow_name: str
    workflow_version: str
    execution_status: str
    created_at: datetime | None
    replayable: bool
    replayability_reason: str | None


class ReplayExecutionSearchPageResponse(BaseModel):
    """Cursor page used by the Studio execution picker."""

    items: list[ReplayExecutionSearchItemResponse]
    next_cursor: str | None


class ReplayResponse(BaseModel):
    replay_id: str
    source_execution_id: str
    status: str
    mode: str
    configuration: ReplayConfigurationResponse | None
    requested_by: str
    organization_id: str
    project_id: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    failure: ReplayFailureResponse | None
    metadata: dict[str, Any]
    job_id: str | None
    replay_execution_id: str | None
    queued_at: datetime | None
    started_at: datetime | None
    execution_completed_at: datetime | None
    cancel_requested_at: datetime | None
    cancelled_at: datetime | None
    attempt_count: int
    evaluation_job_id: str | None
    baseline_evaluation_id: str | None
    replay_evaluation_id: str | None
    comparison_id: str | None
    drift_id: str | None
    result_id: str | None
    evaluation_started_at: datetime | None
    evaluation_completed_at: datetime | None
    comparison_started_at: datetime | None
    comparison_completed_at: datetime | None
    completed_at: datetime | None


class ReplaySubmitResponse(BaseModel):
    replay: ReplayResponse
    job_id: str
    job_status: str


class ReplayMutationDryRunResponse(BaseModel):
    dry_run: bool = True
    operation: str
    replay: ReplayResponse


class ReplayMutationRequest(BaseModel):
    reason: str = Field(min_length=1)
    dry_run: bool = False


class ReplayEvaluateRequest(ReplayMutationRequest):
    baseline_strategy: str = "LATEST_COMPATIBLE"
    baseline_evaluation_id: str | None = None
    evaluation_provider: str | None = None
    provider_installation_id: str | None = None


class ReplayResultResponse(BaseModel):
    result_id: str
    replay_id: str
    source_execution_id: str
    replay_execution_id: str
    baseline_evaluation_id: str
    replay_evaluation_id: str
    comparison_id: str
    drift_id: str
    baseline_strategy: str
    comparison_summary: dict[str, Any]
    drift_summary: dict[str, Any]
    created_at: datetime
    metadata: dict[str, Any]


class ReplayAuditRecordResponse(BaseModel):
    """One replay-scoped audit timeline entry for Studio."""

    event_id: str
    operation_type: str
    status: str
    occurred_at: datetime
    resource_type: str
    resource_id: str
    detail: str
    job_id: str | None
    result_reference: str | None
