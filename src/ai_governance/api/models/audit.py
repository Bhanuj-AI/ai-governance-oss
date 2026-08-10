from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditMetricResponse(BaseModel):
    label: str
    value: int
    description: str | None = None


class AuditFilterOptionsResponse(BaseModel):
    statuses: list[str]
    tool_names: list[str]
    actor_ids: list[str]
    resource_types: list[str]
    operation_types: list[str]


class AuditListItemResponse(BaseModel):
    audit_id: str
    request_id: str
    correlation_id: str
    tool_name: str
    operation_type: str
    resource_type: str
    resource_id: str | None = None
    actor_id: str
    status: str
    dry_run: bool
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: float | None = None
    interrupted: bool
    interrupted_reason: str | None = None
    reason: str
    job_id: str | None = None
    job_status: str | None = None
    result_reference: str | None = None
    error_code: str | None = None


class AuditLinkedJobResponse(BaseModel):
    job_id: str
    job_type: str
    status: str
    submitted_by: str
    updated_at: datetime


class AuditPageResponse(BaseModel):
    summary: list[AuditMetricResponse]
    filters: AuditFilterOptionsResponse
    records: list[AuditListItemResponse]
    total: int
    limit: int
    offset: int


class AuditDetailResponse(BaseModel):
    audit_id: str
    request_id: str
    correlation_id: str
    tool_name: str
    tool_version: str
    actor_id: str
    actor_type: str
    agent_name: str | None = None
    agent_session_id: str | None = None
    client_name: str | None = None
    client_version: str | None = None
    idempotency_key: str
    operation_type: str
    resource_type: str
    resource_id: str | None = None
    request_hash: str
    request_summary: dict[str, Any]
    resolved_versions: dict[str, Any]
    reason: str
    dry_run: bool
    status: str
    job_id: str | None = None
    result_reference: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: float | None = None
    metadata: dict[str, Any]
    interrupted: bool
    interrupted_reason: str | None = None
    linked_job: AuditLinkedJobResponse | None = None
    related_records: list[AuditListItemResponse]


class InvocationAuditListItemResponse(BaseModel):
    invocation_id: str
    request_id: str
    correlation_id: str
    tool_name: str
    tool_version: str
    actor_id: str | None = None
    client_id: str | None = None
    status: str
    authorization_decision: str
    request_hash: str
    response_classification: str | None = None
    response_hash: str | None = None
    error_category: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: float | None = None


class InvocationAuditPageResponse(BaseModel):
    records: list[InvocationAuditListItemResponse]
    total: int
    limit: int
    offset: int
