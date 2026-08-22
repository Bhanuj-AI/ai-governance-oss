"""PostgreSQL implementation of the shared, lease-based job repository."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import final

from ai_governance.databases.postgres.database import PostgresDatabase
from ai_governance.domain.jobs import (
    IdempotencyConflictError,
    Job,
    JobStatus,
    JobType,
    WorkerHeartbeat,
)
from ai_governance.repositories.job_repository import JobRepository
from ai_governance.repositories.mappers.job_persistence_mapper import (
    JobPersistenceMapper,
)
from ai_governance.repositories.postgres._record_adapter import with_jsonb_fields


@final
class PostgresJobRepository(JobRepository):
    """Shared job queue using row locks to claim work across worker replicas."""

    _SELECT_JOB_COLUMNS = """
    SELECT job_id, job_type, status, input_refs_json::text AS input_refs_json,
           input_hash, idempotency_key, submitted_by, attempt_count,
           max_attempts, result_ref, failure_reason, leased_by,
           lease_expires_at::text AS lease_expires_at,
           heartbeat_at::text AS heartbeat_at, created_at::text AS created_at,
           updated_at::text AS updated_at, started_at::text AS started_at,
           completed_at::text AS completed_at, organization_id, project_id,
           execution_context_json::text AS execution_context_json
    FROM job_execution
    """

    _UPSERT_JOB_SQL = """
    INSERT INTO job_execution (
        job_id, job_type, status, input_refs_json, input_hash, idempotency_key,
        submitted_by, attempt_count, max_attempts, result_ref, failure_reason,
        leased_by, lease_expires_at, heartbeat_at, created_at, updated_at,
        started_at, completed_at, organization_id, project_id,
        execution_context_json
    ) VALUES (
        %(job_id)s, %(job_type)s, %(status)s, %(input_refs_json)s,
        %(input_hash)s, %(idempotency_key)s, %(submitted_by)s,
        %(attempt_count)s, %(max_attempts)s, %(result_ref)s,
        %(failure_reason)s, %(leased_by)s, %(lease_expires_at)s,
        %(heartbeat_at)s, %(created_at)s, %(updated_at)s, %(started_at)s,
        %(completed_at)s, %(organization_id)s, %(project_id)s,
        %(execution_context_json)s
    ) ON CONFLICT (job_id) DO UPDATE SET
        job_type = EXCLUDED.job_type, status = EXCLUDED.status,
        input_refs_json = EXCLUDED.input_refs_json,
        input_hash = EXCLUDED.input_hash, idempotency_key = EXCLUDED.idempotency_key,
        submitted_by = EXCLUDED.submitted_by, attempt_count = EXCLUDED.attempt_count,
        max_attempts = EXCLUDED.max_attempts, result_ref = EXCLUDED.result_ref,
        failure_reason = EXCLUDED.failure_reason, leased_by = EXCLUDED.leased_by,
        lease_expires_at = EXCLUDED.lease_expires_at,
        heartbeat_at = EXCLUDED.heartbeat_at, updated_at = EXCLUDED.updated_at,
        started_at = EXCLUDED.started_at, completed_at = EXCLUDED.completed_at,
        organization_id = EXCLUDED.organization_id, project_id = EXCLUDED.project_id,
        execution_context_json = EXCLUDED.execution_context_json
    """

    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def register_worker(self, worker: WorkerHeartbeat) -> None:
        with self._database.connect() as connection:
            connection.execute(
                """INSERT INTO worker_heartbeat(worker_id, worker_type, heartbeat_at, status)
                VALUES(%s, %s, %s, %s)
                ON CONFLICT(worker_id) DO UPDATE SET
                    worker_type=EXCLUDED.worker_type,
                    heartbeat_at=EXCLUDED.heartbeat_at,
                    status=EXCLUDED.status""",
                (worker.worker_id, worker.worker_type, worker.heartbeat_at, worker.status),
            )
            connection.commit()

    def heartbeat_worker(self, worker_id: str, heartbeat_at: datetime) -> None:
        with self._database.connect() as connection:
            connection.execute(
                "UPDATE worker_heartbeat SET heartbeat_at=%s, status='RUNNING' WHERE worker_id=%s",
                (heartbeat_at, worker_id),
            )
            connection.commit()

    def list_worker_heartbeats(self) -> list[WorkerHeartbeat]:
        with self._database.connect() as connection:
            rows = connection.execute(
                "SELECT worker_id, worker_type, heartbeat_at, status FROM worker_heartbeat"
            ).fetchall()
        return [
            WorkerHeartbeat(
                worker_id=row["worker_id"],
                worker_type=row["worker_type"],
                heartbeat_at=row["heartbeat_at"],
                status=row["status"],
            )
            for row in rows
        ]

    def save(self, job: Job) -> None:
        organization_id = job.execution_context.organization_id if job.execution_context else None
        project_id = job.execution_context.project_id if job.execution_context else None
        existing = self.find_by_idempotency_key(
            job.job_type.value, job.idempotency_key, organization_id, project_id
        )
        if existing is not None and (
            existing.job_id != job.job_id or existing.input_hash != job.input_hash
        ):
            raise IdempotencyConflictError("Idempotency key was reused with different input.")

        record = with_jsonb_fields(
            JobPersistenceMapper.to_persistence_record(job),
            "input_refs_json",
            "execution_context_json",
        )
        with self._database.connect() as connection:
            try:
                connection.execute(self._UPSERT_JOB_SQL, record)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def find_by_id(
        self, job_id: str, organization_id: str | None = None, project_id: str | None = None
    ) -> Job | None:
        filters = ["job_id=%(job_id)s"]
        parameters: dict[str, object] = {"job_id": job_id}
        if organization_id is not None:
            filters.append("organization_id=%(organization_id)s")
            parameters["organization_id"] = organization_id
        if project_id is not None:
            filters.append("project_id=%(project_id)s")
            parameters["project_id"] = project_id
        return self._one(" AND ".join(filters), parameters)

    def find_by_idempotency_key(
        self,
        job_type: str,
        idempotency_key: str,
        organization_id: str | None = None,
        project_id: str | None = None,
    ) -> Job | None:
        filters = ["job_type=%(job_type)s", "idempotency_key=%(idempotency_key)s"]
        parameters: dict[str, object] = {
            "job_type": job_type,
            "idempotency_key": idempotency_key,
        }
        if organization_id is not None:
            filters.append("organization_id=%(organization_id)s")
            parameters["organization_id"] = organization_id
        if project_id is not None:
            filters.append("project_id=%(project_id)s")
            parameters["project_id"] = project_id
        return self._one(" AND ".join(filters), parameters)

    def list_by_status(self, status: JobStatus, limit: int = 100) -> list[Job]:
        return self.list_jobs(status=status, limit=limit)

    def list_jobs(
        self,
        status: JobStatus | None = None,
        job_type: JobType | None = None,
        limit: int = 100,
        organization_id: str | None = None,
        project_id: str | None = None,
    ) -> list[Job]:
        filters: list[str] = []
        parameters: dict[str, object] = {"limit": limit}
        if status is not None:
            filters.append("status=%(status)s")
            parameters["status"] = status.value
        if job_type is not None:
            filters.append("job_type=%(job_type)s")
            parameters["job_type"] = job_type.value
        if organization_id is not None:
            filters.append("organization_id=%(organization_id)s")
            parameters["organization_id"] = organization_id
        if project_id is not None:
            filters.append("project_id=%(project_id)s")
            parameters["project_id"] = project_id
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        with self._database.connect() as connection:
            rows = connection.execute(
                f"{self._SELECT_JOB_COLUMNS} {where} ORDER BY created_at, job_id LIMIT %(limit)s",
                parameters,
            ).fetchall()
        return JobPersistenceMapper.from_persistence_records(rows)

    def acquire_next_queued_job(
        self,
        worker_id: str,
        lease_seconds: int,
        job_types: tuple[JobType, ...] | None = None,
        job_operations: Mapping[JobType, tuple[str, ...]] | None = None,
    ) -> Job | None:
        now = datetime.now(UTC)
        filters = ["status=%(queued)s"]
        parameters: dict[str, object] = {
            "queued": JobStatus.QUEUED.value,
            "running": JobStatus.RUNNING.value,
            "worker_id": worker_id,
            "lease_expires_at": now + timedelta(seconds=lease_seconds),
            "now": now,
        }
        if job_types:
            filters.append("job_type = ANY(%(job_types)s)")
            parameters["job_types"] = [job_type.value for job_type in job_types]
        operation_filter = _operation_filter(job_types, job_operations, parameters)
        if operation_filter:
            filters.append(operation_filter)
        query = f"""
            WITH candidate AS (
                SELECT job_id FROM job_execution
                WHERE {' AND '.join(filters)}
                ORDER BY created_at, job_id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE job_execution AS job
            SET status=%(running)s, attempt_count=job.attempt_count + 1,
                leased_by=%(worker_id)s, lease_expires_at=%(lease_expires_at)s,
                heartbeat_at=%(now)s, started_at=COALESCE(job.started_at, %(now)s),
                updated_at=%(now)s
            FROM candidate
            WHERE job.job_id=candidate.job_id
            RETURNING job.job_id, job.job_type, job.status,
                job.input_refs_json::text AS input_refs_json, job.input_hash,
                job.idempotency_key, job.submitted_by, job.attempt_count,
                job.max_attempts, job.result_ref, job.failure_reason, job.leased_by,
                job.lease_expires_at::text AS lease_expires_at,
                job.heartbeat_at::text AS heartbeat_at,
                job.created_at::text AS created_at, job.updated_at::text AS updated_at,
                job.started_at::text AS started_at, job.completed_at::text AS completed_at,
                job.organization_id, job.project_id,
                job.execution_context_json::text AS execution_context_json
        """
        with self._database.connect() as connection:
            row = connection.execute(query, parameters).fetchone()
            connection.commit()
        return JobPersistenceMapper.from_persistence_record(row) if row else None

    def heartbeat(self, job_id: str, worker_id: str, lease_seconds: int) -> None:
        now = datetime.now(UTC)
        with self._database.connect() as connection:
            connection.execute(
                """UPDATE job_execution SET heartbeat_at=%s, lease_expires_at=%s, updated_at=%s
                WHERE job_id=%s AND status=%s AND leased_by=%s""",
                (
                    now,
                    now + timedelta(seconds=lease_seconds),
                    now,
                    job_id,
                    JobStatus.RUNNING.value,
                    worker_id,
                ),
            )
            connection.commit()

    def mark_succeeded(self, job_id: str, result_ref: str) -> None:
        self._finish(job_id, JobStatus.SUCCEEDED, result_ref=result_ref)

    def mark_failed(self, job_id: str, failure_reason: str) -> None:
        self._finish(job_id, JobStatus.FAILED, failure_reason=failure_reason)

    def cancel(self, job_id: str) -> None:
        now = datetime.now(UTC)
        with self._database.connect() as connection:
            connection.execute(
                """UPDATE job_execution SET status=%s, leased_by=NULL, lease_expires_at=NULL,
                heartbeat_at=NULL, updated_at=%s, completed_at=%s WHERE job_id=%s""",
                (JobStatus.CANCELLED.value, now, now, job_id),
            )
            connection.commit()

    def release_expired_leases(self) -> int:
        now = datetime.now(UTC)
        with self._database.connect() as connection:
            rows = connection.execute(
                """UPDATE job_execution SET
                    status=CASE WHEN attempt_count < max_attempts THEN %s ELSE %s END,
                    failure_reason=CASE WHEN attempt_count < max_attempts THEN NULL
                        ELSE 'Job lease expired after max attempts.' END,
                    leased_by=NULL, lease_expires_at=NULL, heartbeat_at=NULL,
                    updated_at=%s,
                    completed_at=CASE WHEN attempt_count < max_attempts THEN completed_at ELSE %s END
                WHERE status=%s AND lease_expires_at IS NOT NULL AND lease_expires_at <= %s
                RETURNING job_id""",
                (
                    JobStatus.QUEUED.value,
                    JobStatus.FAILED.value,
                    now,
                    now,
                    JobStatus.RUNNING.value,
                    now,
                ),
            ).fetchall()
            connection.commit()
        return len(rows)

    def _one(self, where: str, parameters: Mapping[str, object]) -> Job | None:
        with self._database.connect() as connection:
            row = connection.execute(
                f"{self._SELECT_JOB_COLUMNS} WHERE {where}", parameters
            ).fetchone()
        return JobPersistenceMapper.from_persistence_record(row) if row else None

    def _finish(
        self,
        job_id: str,
        status: JobStatus,
        *,
        result_ref: str | None = None,
        failure_reason: str | None = None,
    ) -> None:
        now = datetime.now(UTC)
        with self._database.connect() as connection:
            connection.execute(
                """UPDATE job_execution SET status=%s, result_ref=%s, failure_reason=%s,
                leased_by=NULL, lease_expires_at=NULL, heartbeat_at=NULL, updated_at=%s,
                completed_at=%s WHERE job_id=%s AND status != %s""",
                (status.value, result_ref, failure_reason, now, now, job_id, JobStatus.CANCELLED.value),
            )
            connection.commit()


def _operation_filter(
    job_types: tuple[JobType, ...] | None,
    job_operations: Mapping[JobType, tuple[str, ...]] | None,
    parameters: dict[str, object],
) -> str:
    if not job_operations:
        return ""
    clauses: list[str] = []
    unrestricted = [
        job_type for job_type in (job_types or ()) if job_type not in job_operations
    ]
    if unrestricted:
        parameters["unrestricted_types"] = [item.value for item in unrestricted]
        clauses.append("job_type = ANY(%(unrestricted_types)s)")
    for index, (job_type, operations) in enumerate(job_operations.items()):
        if not operations:
            continue
        parameters[f"operation_type_{index}"] = job_type.value
        operation_clauses: list[str] = []
        for operation_index, operation in enumerate(operations):
            parameter_name = f"operation_{index}_{operation_index}"
            parameters[parameter_name] = operation
            operation_clauses.append(
                f"input_refs_json ->> 'operation' = %({parameter_name})s"
            )
        clauses.append(
            f"(job_type=%(operation_type_{index})s AND ({' OR '.join(operation_clauses)}))"
        )
    return "(" + " OR ".join(clauses) + ")" if clauses else "FALSE"
