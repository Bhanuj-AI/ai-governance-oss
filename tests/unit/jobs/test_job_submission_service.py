from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ai_governance.domain.jobs import (
    IdempotencyConflictError,
    JobStatus,
    JobSubmission,
    JobType,
)
from ai_governance.repositories.in_memory import InMemoryJobRepository
from ai_governance.services.job_submission_service import (
    JobSubmissionService,
    JobSubmissionValidationError,
    stable_input_hash,
)


def test_submit_creates_queued_job() -> None:
    repository = InMemoryJobRepository()
    service = JobSubmissionService(
        repository,
        id_generator=lambda: "job-1",
        clock=lambda: datetime(2026, 6, 28, tzinfo=UTC),
    )

    job = service.submit(_submission())

    assert job.job_id == "job-1"
    assert job.status == JobStatus.QUEUED
    assert job.attempt_count == 0
    assert repository.find_by_id("job-1") == job


def test_input_hash_is_stable_for_canonical_json() -> None:
    left = stable_input_hash({"b": 2, "a": {"c": 3}})
    right = stable_input_hash({"a": {"c": 3}, "b": 2})

    assert left == right


def test_duplicate_submission_returns_existing_job() -> None:
    repository = InMemoryJobRepository()
    service = JobSubmissionService(
        repository,
        id_generator=lambda: "job-1",
    )

    first = service.submit(_submission())
    second = service.submit(_submission())

    assert second == first


def test_idempotency_key_reuse_with_different_input_raises_conflict() -> None:
    repository = InMemoryJobRepository()
    service = JobSubmissionService(repository)

    service.submit(_submission())

    with pytest.raises(IdempotencyConflictError):
        service.submit(_submission(input_refs={"execution_id": "exec-2"}))


def test_submit_rejects_empty_input_refs() -> None:
    service = JobSubmissionService(InMemoryJobRepository())

    with pytest.raises(JobSubmissionValidationError):
        service.submit(_submission(input_refs={}))


def test_submit_rejects_missing_submitted_by() -> None:
    service = JobSubmissionService(InMemoryJobRepository())

    with pytest.raises(JobSubmissionValidationError):
        service.submit(_submission(submitted_by=" "))


@pytest.mark.parametrize("max_attempts", [0, 11])
def test_submit_rejects_invalid_max_attempts(
    max_attempts: int,
) -> None:
    service = JobSubmissionService(InMemoryJobRepository())

    with pytest.raises(JobSubmissionValidationError):
        service.submit(_submission(max_attempts=max_attempts))


def _submission(
    input_refs: dict[str, object] | None = None,
    submitted_by: str = "tester",
    max_attempts: int = 3,
) -> JobSubmission:
    resolved_input_refs = (
        {"execution_id": "exec-1"}
        if input_refs is None
        else input_refs
    )
    return JobSubmission(
        job_type=JobType.EVALUATION,
        input_refs=resolved_input_refs,
        idempotency_key="key-1",
        submitted_by=submitted_by,
        max_attempts=max_attempts,
    )
