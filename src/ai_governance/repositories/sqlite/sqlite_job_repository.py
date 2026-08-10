from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from collections.abc import Mapping
from typing import final

from ai_governance.databases.sqlite.database import SQLiteDatabase
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


@final
class SQLiteJobRepository(JobRepository):
    """
    SQLite implementation of the JobRepository contract.
    """

    def register_worker(self, worker: WorkerHeartbeat) -> None:
        with self._database.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO worker_heartbeat "
                "(worker_id, worker_type, heartbeat_at, status) VALUES (?, ?, ?, ?)",
                (worker.worker_id, worker.worker_type, worker.heartbeat_at.isoformat(), worker.status),
            )
            connection.commit()

    def heartbeat_worker(self, worker_id: str, heartbeat_at) -> None:
        with self._database.connect() as connection:
            connection.execute(
                "UPDATE worker_heartbeat SET heartbeat_at = ?, status = 'RUNNING' WHERE worker_id = ?",
                (heartbeat_at.isoformat(), worker_id),
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
                heartbeat_at=datetime.fromisoformat(row["heartbeat_at"]),
                status=row["status"],
            )
            for row in rows
        ]
    _INSERT_JOB_SQL = """
    INSERT OR REPLACE INTO job_execution (
        job_id,
        job_type,
        status,
        input_refs_json,
        input_hash,
        idempotency_key,
        submitted_by,
        attempt_count,
        max_attempts,
        result_ref,
        failure_reason,
        leased_by,
        lease_expires_at,
        heartbeat_at,
        created_at,
        updated_at,
        started_at,
        completed_at
        , organization_id
        , project_id
        , execution_context_json
    )
    VALUES (
        :job_id,
        :job_type,
        :status,
        :input_refs_json,
        :input_hash,
        :idempotency_key,
        :submitted_by,
        :attempt_count,
        :max_attempts,
        :result_ref,
        :failure_reason,
        :leased_by,
        :lease_expires_at,
        :heartbeat_at,
        :created_at,
        :updated_at,
        :started_at,
        :completed_at
        , :organization_id
        , :project_id
        , :execution_context_json
    )
    """

    _SELECT_JOB_COLUMNS = """
    SELECT
        job_id,
        job_type,
        status,
        input_refs_json,
        input_hash,
        idempotency_key,
        submitted_by,
        attempt_count,
        max_attempts,
        result_ref,
        failure_reason,
        leased_by,
        lease_expires_at,
        heartbeat_at,
        created_at,
        updated_at,
        started_at,
        completed_at
        , organization_id
        , project_id
        , execution_context_json
    FROM job_execution
    """

    def __init__(
        self,
        database: SQLiteDatabase,
    ) -> None:
        self._database = database

    def save(
        self,
        job: Job,
    ) -> None:
        existing = self.find_by_idempotency_key(
            job.job_type.value,
            job.idempotency_key,
            job.execution_context.organization_id if job.execution_context else None,
            job.execution_context.project_id if job.execution_context else None,
        )
        if existing is not None and (
            existing.job_id != job.job_id or existing.input_hash != job.input_hash
        ):
            raise IdempotencyConflictError(
                "Idempotency key was reused with different input."
            )

        record = JobPersistenceMapper.to_persistence_record(job)
        with self._database.connect() as connection:
            try:
                connection.execute(self._INSERT_JOB_SQL, record)
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def find_by_id(
        self,
        job_id: str,
        organization_id: str | None = None,
        project_id: str | None = None,
    ) -> Job | None:
        scope = ""
        parameters: list[object] = [job_id]
        if organization_id is not None:
            scope += " AND organization_id = ?"
            parameters.append(organization_id)
        if project_id is not None:
            scope += " AND project_id = ?"
            parameters.append(project_id)
        with self._database.connect() as connection:
            row = connection.execute(
                f"{self._SELECT_JOB_COLUMNS} WHERE job_id = ?{scope}",
                parameters,
            ).fetchone()

        if row is None:
            return None

        return JobPersistenceMapper.from_persistence_record(row)

    def find_by_idempotency_key(
        self,
        job_type: str,
        idempotency_key: str,
        organization_id: str | None = None,
        project_id: str | None = None,
    ) -> Job | None:
        scope = ""
        parameters: list[object] = [job_type, idempotency_key]
        if organization_id is not None:
            scope += " AND organization_id = ?"
            parameters.append(organization_id)
        if project_id is not None:
            scope += " AND project_id = ?"
            parameters.append(project_id)
        with self._database.connect() as connection:
            row = connection.execute(
                f"{self._SELECT_JOB_COLUMNS} "
                f"WHERE job_type = ? AND idempotency_key = ?{scope}",
                parameters,
            ).fetchone()

        if row is None:
            return None

        return JobPersistenceMapper.from_persistence_record(row)

    def list_by_status(
        self,
        status: JobStatus,
        limit: int = 100,
    ) -> list[Job]:
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
        values: list[object] = []
        if status is not None:
            filters.append("status = ?")
            values.append(status.value)
        if job_type is not None:
            filters.append("job_type = ?")
            values.append(job_type.value)
        if organization_id is not None:
            filters.append("organization_id = ?")
            values.append(organization_id)
        if project_id is not None:
            filters.append("project_id = ?")
            values.append(project_id)

        where_clause = ""
        if filters:
            where_clause = f"WHERE {' AND '.join(filters)} "
        values.append(limit)

        with self._database.connect() as connection:
            rows = connection.execute(
                f"{self._SELECT_JOB_COLUMNS} "
                f"{where_clause}"
                "ORDER BY created_at, job_id "
                "LIMIT ?",
                values,
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
        # BEGIN IMMEDIATE serializes competing SQLite workers.  The conditional
        # UPDATE makes the claim a compare-and-set rather than a read/save race.
        with self._database.connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                clauses = ["status=?"]
                parameters: list[object] = [JobStatus.QUEUED.value]
                if job_types:
                    clauses.append(
                        f"job_type IN ({','.join('?' for _ in job_types)})"
                    )
                    parameters.extend(job_type.value for job_type in job_types)
                if job_operations:
                    operation_clauses: list[str] = []
                    unrestricted_types = [
                        job_type for job_type in (job_types or ()) if job_type not in job_operations
                    ]
                    if unrestricted_types:
                        operation_clauses.append(
                            f"job_type IN ({','.join('?' for _ in unrestricted_types)})"
                        )
                        parameters.extend(job_type.value for job_type in unrestricted_types)
                    for job_type, operations in job_operations.items():
                        if not operations:
                            continue
                        operation_clauses.append(
                            "(job_type=? AND ("
                            + " OR ".join(
                                "json_extract(input_refs_json, '$.operation') = ?"
                                for _ in operations
                            )
                            + "))"
                        )
                        parameters.append(job_type.value)
                        parameters.extend(operations)
                    clauses.append("(" + " OR ".join(operation_clauses) + ")")
                row = connection.execute(
                    f"{self._SELECT_JOB_COLUMNS} WHERE {' AND '.join(clauses)} "
                    "ORDER BY created_at, job_id LIMIT 1",
                    parameters,
                ).fetchone()
                if row is None:
                    connection.commit()
                    return None
                job = JobPersistenceMapper.from_persistence_record(row)
                updated = connection.execute(
                    """
                    UPDATE job_execution
                    SET status=?, attempt_count=?, leased_by=?, lease_expires_at=?,
                        heartbeat_at=?, started_at=COALESCE(started_at, ?), updated_at=?
                    WHERE job_id=? AND status=?
                    """,
                    (
                        JobStatus.RUNNING.value,
                        job.attempt_count + 1,
                        worker_id,
                        (now + timedelta(seconds=lease_seconds)).isoformat(),
                        now.isoformat(),
                        now.isoformat(),
                        now.isoformat(),
                        job.job_id,
                        JobStatus.QUEUED.value,
                    ),
                )
                if updated.rowcount != 1:
                    connection.rollback()
                    return None
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return self.find_by_id(job.job_id)

    def heartbeat(
        self,
        job_id: str,
        worker_id: str,
        lease_seconds: int,
    ) -> None:
        job = self.find_by_id(job_id)
        if job is None or job.status != JobStatus.RUNNING or job.leased_by != worker_id:
            return

        now = datetime.now(UTC)
        self.save(
            replace(
                job,
                heartbeat_at=now,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                updated_at=now,
            )
        )

    def mark_succeeded(
        self,
        job_id: str,
        result_ref: str,
    ) -> None:
        now = datetime.now(UTC)
        with self._database.connect() as connection:
            connection.execute(
                """
                UPDATE job_execution
                SET status=?, result_ref=?, failure_reason=NULL, leased_by=NULL,
                    lease_expires_at=NULL, heartbeat_at=NULL, updated_at=?, completed_at=?
                WHERE job_id=? AND status != ?
                """,
                (JobStatus.SUCCEEDED.value, result_ref, now.isoformat(), now.isoformat(), job_id, JobStatus.CANCELLED.value),
            )
            connection.commit()

    def mark_failed(
        self,
        job_id: str,
        failure_reason: str,
    ) -> None:
        now = datetime.now(UTC)
        with self._database.connect() as connection:
            connection.execute(
                """
                UPDATE job_execution
                SET status=?, result_ref=NULL, failure_reason=?, leased_by=NULL,
                    lease_expires_at=NULL, heartbeat_at=NULL, updated_at=?, completed_at=?
                WHERE job_id=? AND status != ?
                """,
                (JobStatus.FAILED.value, failure_reason, now.isoformat(), now.isoformat(), job_id, JobStatus.CANCELLED.value),
            )
            connection.commit()

    def cancel(
        self,
        job_id: str,
    ) -> None:
        job = self.find_by_id(job_id)
        if job is None:
            return

        now = datetime.now(UTC)
        self.save(
            replace(
                job,
                status=JobStatus.CANCELLED,
                leased_by=None,
                lease_expires_at=None,
                heartbeat_at=None,
                updated_at=now,
                completed_at=now,
            )
        )

    def release_expired_leases(self) -> int:
        now = datetime.now(UTC)
        running_jobs = self.list_by_status(JobStatus.RUNNING, limit=1000)
        released = 0

        for job in running_jobs:
            if job.lease_expires_at is None or job.lease_expires_at > now:
                continue

            if job.attempt_count < job.max_attempts:
                self.save(
                    replace(
                        job,
                        status=JobStatus.QUEUED,
                        leased_by=None,
                        lease_expires_at=None,
                        heartbeat_at=None,
                        updated_at=now,
                    )
                )
            else:
                self.save(
                    replace(
                        job,
                        status=JobStatus.FAILED,
                        failure_reason="Job lease expired after max attempts.",
                        leased_by=None,
                        lease_expires_at=None,
                        heartbeat_at=None,
                        updated_at=now,
                        completed_at=now,
                    )
                )
            released += 1

        return released
