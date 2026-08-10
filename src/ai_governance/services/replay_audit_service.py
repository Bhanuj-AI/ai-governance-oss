"""Read-only, replay-scoped audit timeline.

The generic Studio audit page intentionally exposes MCP controlled-write
records.  A replay, however, is normally created and driven through REST and
worker jobs.  This read model therefore derives an auditable timeline from the
durable Replay aggregate and its tenant-scoped jobs instead of mixing an
unrelated MCP feed into a replay detail page.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ai_governance.domain.jobs import Job, JobStatus
from ai_governance.domain.replay import Replay, ReplayStatus
from ai_governance.repositories.job_repository import JobRepository
from ai_governance.tenancy.domain import TenantContext


class ReplayReader(Protocol):
    def get(self, replay_id: str, context: TenantContext) -> Replay: ...


@dataclass(frozen=True)
class ReplayAuditRecord:
    """One durable replay action or worker outcome shown in Studio."""

    event_id: str
    operation_type: str
    status: str
    occurred_at: datetime
    resource_type: str
    resource_id: str
    detail: str
    job_id: str | None = None
    result_reference: str | None = None


class ReplayAuditService:
    """Compose a bounded audit trail from a replay and its two worker jobs."""

    def __init__(
        self,
        *,
        replay_reader: ReplayReader,
        job_repository: JobRepository,
    ) -> None:
        self._replays = replay_reader
        self._jobs = job_repository

    def list_records(
        self, replay_id: str, context: TenantContext
    ) -> tuple[ReplayAuditRecord, ...]:
        replay = self._replays.get(replay_id, context)
        project_id = context.project_id or ""
        execution_job = self._job(replay.job_id, context.organization_id, project_id)
        evaluation_job = self._job(
            replay.evaluation_job_id, context.organization_id, project_id
        )
        records: list[ReplayAuditRecord] = [
            _record(
                replay,
                "CREATE_REPLAY",
                "SUCCEEDED",
                replay.created_at,
                "Replay request persisted with its operator and tenant context.",
            )
        ]

        if replay.configuration is not None:
            records.append(
                _record(
                    replay,
                    "FREEZE_SOURCE_EVIDENCE",
                    "SUCCEEDED",
                    replay.configuration.resolved_at or replay.updated_at,
                    "Historical source configuration was resolved and frozen.",
                )
            )
        elif replay.failure is not None:
            records.append(
                _record(
                    replay,
                    "FREEZE_SOURCE_EVIDENCE",
                    "FAILED",
                    replay.failure.occurred_at,
                    replay.failure.message,
                )
            )

        if replay.job_id is not None:
            records.append(
                _record(
                    replay,
                    "SUBMIT_REPLAY_EXECUTION",
                    "SUCCEEDED",
                    replay.queued_at
                    or (
                        execution_job.created_at
                        if execution_job is not None
                        else replay.updated_at
                    ),
                    "Durable replay execution job submitted.",
                    job_id=replay.job_id,
                )
            )
        if execution_job is not None:
            records.append(_job_record(replay, execution_job, "REPLAY_EXECUTION"))

        if replay.evaluation_job_id is not None:
            records.append(
                _record(
                    replay,
                    "SUBMIT_REPLAY_EVALUATION",
                    "SUCCEEDED",
                    replay.evaluation_started_at
                    or (
                        evaluation_job.created_at
                        if evaluation_job is not None
                        else replay.updated_at
                    ),
                    "Durable replay evaluation job submitted.",
                    job_id=replay.evaluation_job_id,
                )
            )
        if evaluation_job is not None:
            records.append(_job_record(replay, evaluation_job, "REPLAY_EVALUATION"))

        if replay.baseline_evaluation_id is not None:
            records.append(
                _record(
                    replay,
                    "RESOLVE_REPLAY_BASELINE",
                    "SUCCEEDED",
                    replay.evaluation_completed_at or replay.updated_at,
                    "Compatible source evaluation selected for comparison.",
                    resource_type="Evaluation",
                    resource_id=replay.baseline_evaluation_id,
                )
            )
        if replay.comparison_id is not None:
            records.append(
                _record(
                    replay,
                    "COMPARE_REPLAY_EVALUATIONS",
                    "SUCCEEDED",
                    replay.comparison_completed_at or replay.updated_at,
                    "Baseline and replay evaluation evidence compared.",
                    resource_type="ReplayComparison",
                    resource_id=replay.comparison_id,
                )
            )
        if replay.drift_id is not None:
            records.append(
                _record(
                    replay,
                    "ANALYZE_REPLAY_DRIFT",
                    "SUCCEEDED",
                    replay.comparison_completed_at or replay.updated_at,
                    "Semantic drift analysis persisted as replay evidence.",
                    resource_type="DriftAnalysis",
                    resource_id=replay.drift_id,
                )
            )
        if replay.status in {
            ReplayStatus.COMPLETED,
            ReplayStatus.FAILED,
            ReplayStatus.CANCELLED,
        }:
            records.append(
                _record(
                    replay,
                    "FINALIZE_REPLAY",
                    _terminal_status(replay),
                    replay.completed_at
                    or replay.cancelled_at
                    or (replay.failure.occurred_at if replay.failure else replay.updated_at),
                    replay.failure.message
                    if replay.failure
                    else "Replay workflow reached a terminal outcome.",
                    resource_type="ReplayResult" if replay.result_id else "Replay",
                    resource_id=replay.result_id or replay.replay_id,
                    result_reference=(
                        f"replay_result:{replay.result_id}" if replay.result_id else None
                    ),
                )
            )

        return tuple(
            sorted(
                records,
                key=lambda item: (item.occurred_at, item.event_id),
                reverse=True,
            )
        )

    def _job(
        self, job_id: str | None, organization_id: str, project_id: str
    ) -> Job | None:
        return (
            self._jobs.find_by_id(job_id, organization_id, project_id)
            if job_id is not None
            else None
        )


def _record(
    replay: Replay,
    operation_type: str,
    status: str,
    occurred_at: datetime,
    detail: str,
    *,
    resource_type: str = "Replay",
    resource_id: str | None = None,
    job_id: str | None = None,
    result_reference: str | None = None,
) -> ReplayAuditRecord:
    resolved_resource_id = resource_id or replay.replay_id
    return ReplayAuditRecord(
        event_id=f"{replay.replay_id}:{operation_type}:{resolved_resource_id}",
        operation_type=operation_type,
        status=status,
        occurred_at=occurred_at,
        resource_type=resource_type,
        resource_id=resolved_resource_id,
        detail=detail,
        job_id=job_id,
        result_reference=result_reference,
    )


def _job_record(replay: Replay, job: Job, operation_type: str) -> ReplayAuditRecord:
    occurred_at = job.completed_at or job.started_at or job.created_at
    detail = (
        job.failure_reason
        if job.status is JobStatus.FAILED and job.failure_reason
        else f"{job.job_type.value} job is {job.status.value.lower()}."
    )
    return _record(
        replay,
        operation_type,
        job.status.value,
        occurred_at,
        detail,
        resource_type="Job",
        resource_id=job.job_id,
        job_id=job.job_id,
        result_reference=job.result_ref,
    )


def _terminal_status(replay: Replay) -> str:
    if replay.status is ReplayStatus.COMPLETED:
        return "SUCCEEDED"
    if replay.status is ReplayStatus.CANCELLED:
        return "CANCELLED"
    return "FAILED"
