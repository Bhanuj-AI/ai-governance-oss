from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from kavach.domain.jobs import Job, JobExecutionContext, JobStatus, JobType


class JobPersistenceMapper:
    """
    Maps Job domain objects to and from persistence records.
    """

    @staticmethod
    def canonical_json(
        value: Mapping[str, Any],
    ) -> str:
        """
        Return stable JSON used for persistence and input hashing.
        """
        return json.dumps(
            dict(value),
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def to_persistence_record(
        cls,
        job: Job,
    ) -> dict[str, Any]:
        return {
            "job_id": job.job_id,
            "job_type": job.job_type.value,
            "status": job.status.value,
            "input_refs_json": cls.canonical_json(job.input_refs),
            "input_hash": job.input_hash,
            "idempotency_key": job.idempotency_key,
            "submitted_by": job.submitted_by,
            "attempt_count": job.attempt_count,
            "max_attempts": job.max_attempts,
            "result_ref": job.result_ref,
            "failure_reason": job.failure_reason,
            "leased_by": job.leased_by,
            "lease_expires_at": _datetime_to_text(job.lease_expires_at),
            "heartbeat_at": _datetime_to_text(job.heartbeat_at),
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
            "started_at": _datetime_to_text(job.started_at),
            "completed_at": _datetime_to_text(job.completed_at),
            "organization_id": job.execution_context.organization_id
            if job.execution_context
            else "org_default",
            "project_id": job.execution_context.project_id
            if job.execution_context
            else "project_default",
            "execution_context_json": (
                cls.canonical_json(
                    {
                        "organization_id": job.execution_context.organization_id,
                        "project_id": job.execution_context.project_id,
                        "actor_id": job.execution_context.actor_id,
                        "submitted_request_id": job.execution_context.submitted_request_id,
                        "correlation_id": job.execution_context.correlation_id,
                    }
                )
                if job.execution_context
                else None
            ),
        }

    @staticmethod
    def from_persistence_record(
        record: Mapping[str, Any],
    ) -> Job:
        return Job(
            job_id=record["job_id"],
            job_type=JobType(record["job_type"]),
            status=JobStatus(record["status"]),
            input_refs=json.loads(record["input_refs_json"]),
            input_hash=record["input_hash"],
            idempotency_key=record["idempotency_key"],
            submitted_by=record["submitted_by"],
            attempt_count=record["attempt_count"],
            max_attempts=record["max_attempts"],
            result_ref=record["result_ref"],
            failure_reason=record["failure_reason"],
            leased_by=record["leased_by"],
            lease_expires_at=_datetime_from_text(record["lease_expires_at"]),
            heartbeat_at=_datetime_from_text(record["heartbeat_at"]),
            created_at=datetime.fromisoformat(record["created_at"]),
            updated_at=datetime.fromisoformat(record["updated_at"]),
            started_at=_datetime_from_text(record["started_at"]),
            completed_at=_datetime_from_text(record["completed_at"]),
            execution_context=_execution_context(record),
        )

    @classmethod
    def from_persistence_records(
        cls,
        records: list[Mapping[str, Any]],
    ) -> list[Job]:
        return [cls.from_persistence_record(record) for record in records]


def _datetime_to_text(
    value: datetime | None,
) -> str | None:
    return value.isoformat() if value is not None else None


def _execution_context(record: Mapping[str, Any]) -> JobExecutionContext | None:
    try:
        raw = record["execution_context_json"]
    except (KeyError, IndexError):
        raw = None
    if not raw:
        return None
    data = json.loads(raw) if isinstance(raw, str) else dict(raw)
    return JobExecutionContext(**data)


def _datetime_from_text(
    value: str | None,
) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None
