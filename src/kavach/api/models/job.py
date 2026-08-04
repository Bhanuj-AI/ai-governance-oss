from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from kavach.domain.jobs import JobStatus, JobType


class JobSubmitRequest(BaseModel):
    """
    REST request body for submitting an asynchronous governance job.
    """

    job_type: JobType
    input_refs: dict[str, Any]
    idempotency_key: str = Field(min_length=1)
    submitted_by: str = Field(min_length=1)
    max_attempts: int = Field(default=3, ge=1, le=10)

    @field_validator("idempotency_key", "submitted_by")
    @classmethod
    def required_string_must_not_be_blank(
        cls,
        value: str,
    ) -> str:
        if not value.strip():
            raise ValueError("Value must not be blank.")
        return value


class JobResponse(BaseModel):
    """
    REST response shape for a governance job.
    """

    job_id: str
    job_type: JobType
    status: JobStatus
    input_refs: dict[str, Any]
    input_hash: str
    idempotency_key: str
    submitted_by: str
    attempt_count: int
    max_attempts: int
    result_ref: str | None = None
    failure_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class JobListResponse(BaseModel):
    """
    REST response shape for a filtered job list.
    """

    jobs: list[JobResponse]


class JobResultResponse(BaseModel):
    """
    REST response shape for job result reference lookup.
    """

    job_id: str
    status: JobStatus
    result_ref: str | None = None
    failure_reason: str | None = None
