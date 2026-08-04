from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class JobType(str, Enum):
    """
    Governance operation that can be submitted to the job control plane.
    """

    EVALUATION = "EVALUATION"
    EXPERIMENT = "EXPERIMENT"
    REPLAY = "REPLAY"
    REPLAY_EXECUTION = "REPLAY_EXECUTION"
    REPLAY_EVALUATION = "REPLAY_EVALUATION"
    DRIFT_ANALYSIS = "DRIFT_ANALYSIS"
    # Plugin-owned operations use this stable envelope and declare their
    # operation in ``input_refs["_kavach_extension"]``. Core deliberately
    # does not enumerate those operations.
    EXTENSION = "EXTENSION"


class JobStatus(str, Enum):
    """
    Lifecycle state for an asynchronous governance job.
    """

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class WorkerHeartbeat:
    worker_id: str
    worker_type: str
    heartbeat_at: datetime
    status: str = "RUNNING"


class IdempotencyConflictError(Exception):
    """
    Raised when an idempotency key is reused for different job input.
    """


@dataclass(frozen=True)
class JobExecutionContext:
    organization_id: str
    project_id: str
    actor_id: str
    submitted_request_id: str
    correlation_id: str | None = None


@dataclass(frozen=True)
class Job:
    """
    Persisted governance job with lease and retry metadata.
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
    result_ref: str | None
    failure_reason: str | None
    leased_by: str | None
    lease_expires_at: datetime | None
    heartbeat_at: datetime | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    execution_context: JobExecutionContext | None = None

    def __post_init__(self) -> None:
        _require_non_empty("job_id", self.job_id)
        _require_non_empty("input_hash", self.input_hash)
        _require_non_empty("idempotency_key", self.idempotency_key)
        _require_non_empty("submitted_by", self.submitted_by)
        if self.attempt_count < 0:
            raise ValueError("Job attempt_count must not be negative.")
        if self.max_attempts <= 0:
            raise ValueError("Job max_attempts must be greater than zero.")
        object.__setattr__(self, "input_refs", dict(self.input_refs))


@dataclass(frozen=True)
class JobSubmission:
    """
    Request to submit a governance job.
    """

    job_type: JobType
    input_refs: dict[str, Any]
    idempotency_key: str
    submitted_by: str
    max_attempts: int = 3
    execution_context: JobExecutionContext | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_refs", dict(self.input_refs))


@dataclass(frozen=True)
class JobResult:
    """
    Result returned by a job handler after execution.
    """

    job_id: str
    status: JobStatus
    result_ref: str | None
    failure_reason: str | None


def _require_non_empty(
    field_name: str,
    value: str,
) -> None:
    if not value.strip():
        raise ValueError(f"Job {field_name} must not be empty.")
