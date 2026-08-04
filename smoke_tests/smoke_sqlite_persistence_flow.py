from __future__ import annotations

import argparse
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from kavach.databases.sqlite.database import SQLiteDatabase
from kavach.domain.jobs import JobSubmission, JobType
from kavach.mcp.audit import MCPExecutionAuditLog
from kavach.mcp.dto import WriteEnvelope
from kavach.repositories.sqlite.sqlite_job_repository import SQLiteJobRepository
from kavach.services.job_submission_service import JobSubmissionService


def main() -> None:
    args = _parse_args()

    with _database_path(args.database) as database_path:
        database = SQLiteDatabase(database_path)
        database.initialize()

        job_repository = SQLiteJobRepository(database)
        submission_service = JobSubmissionService(
            job_repository,
            id_generator=lambda: "sqlite-job-1",
        )
        job = submission_service.submit(
            JobSubmission(
                job_type=JobType.EVALUATION,
                input_refs={"execution_id": "sqlite-execution-1"},
                idempotency_key="sqlite-job-key-1",
                submitted_by="smoke-test",
            )
        )

        audit_log = MCPExecutionAuditLog.sqlite(database_path)
        audit = audit_log.start(
            tool_name="evaluation.submit_async",
            operation_type="SUBMIT_EVALUATION_JOB",
            resource_type="evaluation",
            resource_id="sqlite-execution-1",
            envelope=WriteEnvelope(
                request_id="sqlite-request-1",
                correlation_id="sqlite-correlation-1",
                idempotency_key="sqlite-audit-key-1",
                requested_by="smoke-test",
                actor_type="SERVICE",
                reason="Smoke-test SQLite persistence",
            ),
            payload={
                "execution_id": "sqlite-execution-1",
                "provider_config": {"api_key": "should-not-leak"},
            },
            resolved_versions={"provider_name": "mock"},
        )
        audit_log.complete(
            audit,
            status="SUCCEEDED",
            job_id=job.job_id,
            result_reference=f"job:{job.job_id}",
        )

        reopened_database = SQLiteDatabase(database_path)
        reopened_job_repository = SQLiteJobRepository(reopened_database)
        reopened_audit_log = MCPExecutionAuditLog.sqlite(database_path)
        loaded_job = reopened_job_repository.find_by_id(job.job_id)
        loaded_audit = reopened_audit_log.get(audit.audit_id)

        if loaded_job is None or loaded_audit is None:
            raise AssertionError("Expected persisted job and audit record.")

        print(f"database={database_path}")
        print()
        print("[job]")
        print(f"job_id={loaded_job.job_id}")
        print(f"status={loaded_job.status.value}")
        print(f"input_refs={loaded_job.input_refs}")
        print(f"idempotency_key={loaded_job.idempotency_key}")
        print()
        print("[audit]")
        print(f"audit_id={loaded_audit.audit_id}")
        print(f"status={loaded_audit.status}")
        print(f"job_id={loaded_audit.job_id}")
        print(f"request_hash={loaded_audit.request_hash}")
        print(
            "provider_config_summary="
            f"{loaded_audit.request_summary['provider_config']}"
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smoke-test SQLite job and MCP audit persistence.",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=None,
        help="Optional SQLite DB path. If omitted, a temporary DB is used.",
    )
    return parser.parse_args()


@contextmanager
def _database_path(
    database: Path | None,
) -> Iterator[Path]:
    if database is not None:
        database.parent.mkdir(parents=True, exist_ok=True)
        yield database
        return

    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "kavach-sqlite-smoke.db"


if __name__ == "__main__":
    main()
