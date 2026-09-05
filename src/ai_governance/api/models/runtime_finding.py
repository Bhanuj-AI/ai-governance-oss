"""Pydantic models for runtime findings API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MetricSnapshotResponse(BaseModel):
    name: str
    value: float
    sample_size: int


class EvidenceReferenceResponse(BaseModel):
    kind: str
    value: str


class ReconciliationWindowResponse(BaseModel):
    observed_start: datetime
    observed_end: datetime
    baseline_start: datetime
    baseline_end: datetime
    finalization_cutoff_at: datetime | None = None
    lateness_policy_hours: int | None = None


class ReconciliationRecordResponse(BaseModel):
    window: ReconciliationWindowResponse
    outcome: str
    reconciled_at: datetime
    detail: str | None = None


class FindingReviewResponse(BaseModel):
    action: str
    actor_id: str
    reviewed_at: datetime
    note: str | None = None


class RuntimeFindingReviewRequest(BaseModel):
    action: str
    note: str | None = Field(default=None, max_length=2_000)


class RuntimeFindingResponse(BaseModel):
    finding_id: str
    organization_id: str
    project_id: str | None = None
    finding_type: str
    subject_type: str
    subject_id: str
    severity: str
    status: str
    lifecycle: str
    baseline_window: str
    observation_window: str
    baseline_metrics: list[MetricSnapshotResponse] = []
    observed_metrics: list[MetricSnapshotResponse] = []
    observation_count: int = 0
    consecutive_normal_windows: int = 0
    healthy_reconciliation_windows: list[ReconciliationWindowResponse] = []
    last_reconciliation: ReconciliationRecordResponse | None = None
    reviews: list[FindingReviewResponse] = []
    evidence_references: list[EvidenceReferenceResponse] = []
    related_execution_ids: list[str] = []
    detector_id: str
    detector_version: str
    first_detected_at: datetime | None = None
    last_detected_at: datetime | None = None
    resolved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class RuntimeFindingListResponse(BaseModel):
    items: list[RuntimeFindingResponse]
    next_cursor: str | None = None


class RuntimeFindingReconcileResponse(BaseModel):
    reconciled: int
    resolved: int
    processed: int = 0
    outcomes: dict[str, int] = {}
    findings: list[ReconciliationFindingResponse] = []


class ReconciliationFindingResponse(BaseModel):
    finding_id: str
    outcome: str
    consecutive_normal_windows: int
    required_normal_windows: int
    window: ReconciliationWindowResponse | None = None
    detail: str | None = None
