from __future__ import annotations

from dataclasses import replace
from typing import final

from ai_governance.databases.postgres.database import PostgresDatabase
from ai_governance.domain.replay import Replay
from ai_governance.domain.replay.errors import ReplayConflict, ReplayIdempotencyConflict
from ai_governance.repositories.mappers.replay_persistence_mapper import (
    ReplayPersistenceMapper,
)
from ai_governance.repositories.replay_repository import ReplayListFilters, ReplayRepository


@final
class PostgresReplayRepository(ReplayRepository):
    """PostgreSQL Replay repository with tenant-scoped optimistic updates."""

    _COLUMNS = """
    replay_id, source_execution_id, status, mode, configuration_json::text AS configuration_json,
    requested_by, organization_id, project_id, request_id, correlation_id,
    idempotency_key, input_hash, created_at::text AS created_at, updated_at::text AS updated_at,
    archived_at::text AS archived_at, failure_json::text AS failure_json,
    metadata_json::text AS metadata_json, version
    , job_id, replay_execution_id, queued_at::text AS queued_at,
    started_at::text AS started_at,
    execution_completed_at::text AS execution_completed_at,
    cancel_requested_at::text AS cancel_requested_at,
    cancelled_at::text AS cancelled_at, attempt_count,
    evaluation_job_id, baseline_evaluation_id, replay_evaluation_id,
    comparison_id, drift_id, result_id,
    evaluation_started_at::text AS evaluation_started_at,
    evaluation_completed_at::text AS evaluation_completed_at,
    comparison_started_at::text AS comparison_started_at,
    comparison_completed_at::text AS comparison_completed_at,
    completed_at::text AS completed_at
    """

    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def save(self, replay: Replay, expected_version: int | None = None) -> Replay:
        return (
            self._insert(replay)
            if expected_version is None
            else self._update(replay, expected_version)
        )

    def get(
        self, replay_id: str, organization_id: str, project_id: str
    ) -> Replay | None:
        return self._one(
            "replay_id=%(replay_id)s AND organization_id=%(organization_id)s AND project_id=%(project_id)s",
            {
                "replay_id": replay_id,
                "organization_id": organization_id,
                "project_id": project_id,
            },
        )

    def list(
        self, filters: ReplayListFilters, organization_id: str, project_id: str
    ) -> list[Replay]:
        clauses = ["organization_id=%(organization_id)s", "project_id=%(project_id)s"]
        parameters: dict[str, object] = {
            "organization_id": organization_id,
            "project_id": project_id,
            "limit": filters.limit,
        }
        for name, clause, value in (
            (
                "status",
                "status=%(status)s",
                filters.status.value if filters.status else None,
            ),
            (
                "source_execution_id",
                "source_execution_id=%(source_execution_id)s",
                filters.source_execution_id,
            ),
            ("requested_by", "requested_by=%(requested_by)s", filters.requested_by),
            ("created_after", "created_at>=%(created_after)s", filters.created_after),
            (
                "created_before",
                "created_at<=%(created_before)s",
                filters.created_before,
            ),
        ):
            if value is not None:
                clauses.append(clause)
                parameters[name] = value
        with self._database.connect() as connection:
            rows = connection.execute(
                f"SELECT {self._COLUMNS} FROM replay WHERE {' AND '.join(clauses)} "
                "ORDER BY created_at DESC, replay_id DESC LIMIT %(limit)s",
                parameters,
            ).fetchall()
        return [ReplayPersistenceMapper.from_persistence_record(row) for row in rows]

    def find_by_idempotency(
        self, idempotency_key: str, organization_id: str, project_id: str
    ) -> Replay | None:
        return self._one(
            "idempotency_key=%(idempotency_key)s AND organization_id=%(organization_id)s AND project_id=%(project_id)s",
            {
                "idempotency_key": idempotency_key,
                "organization_id": organization_id,
                "project_id": project_id,
            },
        )

    def update(self, replay: Replay, expected_version: int) -> Replay:
        return self._update(replay, expected_version)

    def archive(self, replay: Replay, expected_version: int) -> Replay:
        return self._update(replay, expected_version)

    def _one(self, where: str, parameters: dict[str, object]) -> Replay | None:
        with self._database.connect() as connection:
            row = connection.execute(
                f"SELECT {self._COLUMNS} FROM replay WHERE {where}", parameters
            ).fetchone()
        return ReplayPersistenceMapper.from_persistence_record(row) if row else None

    def _insert(self, replay: Replay) -> Replay:
        stored = replace(replay, version=1)
        record = ReplayPersistenceMapper.to_persistence_record(stored)
        with self._database.connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO replay (replay_id, source_execution_id, status, mode, configuration_json,
                    requested_by, organization_id, project_id, request_id, correlation_id, idempotency_key,
                    input_hash, created_at, updated_at, archived_at, failure_json, metadata_json, version,
                    job_id, replay_execution_id, queued_at, started_at, execution_completed_at,
                    cancel_requested_at, cancelled_at, attempt_count,
                    evaluation_job_id, baseline_evaluation_id, replay_evaluation_id,
                    comparison_id, drift_id, result_id, evaluation_started_at,
                    evaluation_completed_at, comparison_started_at, comparison_completed_at,
                    completed_at)
                    VALUES (%(replay_id)s, %(source_execution_id)s, %(status)s, %(mode)s,
                    %(configuration_json)s::jsonb, %(requested_by)s, %(organization_id)s, %(project_id)s,
                    %(request_id)s, %(correlation_id)s, %(idempotency_key)s, %(input_hash)s,
                    %(created_at)s, %(updated_at)s, %(archived_at)s, %(failure_json)s::jsonb,
                    %(metadata_json)s::jsonb, %(version)s, %(job_id)s,
                    %(replay_execution_id)s, %(queued_at)s, %(started_at)s,
                    %(execution_completed_at)s, %(cancel_requested_at)s,
                    %(cancelled_at)s, %(attempt_count)s, %(evaluation_job_id)s,
                    %(baseline_evaluation_id)s, %(replay_evaluation_id)s,
                    %(comparison_id)s, %(drift_id)s, %(result_id)s,
                    %(evaluation_started_at)s, %(evaluation_completed_at)s,
                    %(comparison_started_at)s, %(comparison_completed_at)s,
                    %(completed_at)s)
                    """,
                    record,
                )
                connection.commit()
            except Exception as exc:
                connection.rollback()
                if "idempotency" in str(exc).lower() or "unique" in str(exc).lower():
                    raise ReplayIdempotencyConflict(
                        "Replay idempotency key is already in use for this project."
                    ) from exc
                raise ReplayConflict("Replay already exists.") from exc
        return stored

    def _update(self, replay: Replay, expected_version: int) -> Replay:
        stored = replace(replay, version=expected_version + 1)
        record = ReplayPersistenceMapper.to_persistence_record(stored)
        record["expected_version"] = expected_version
        with self._database.connect() as connection:
            result = connection.execute(
                """
                UPDATE replay SET status=%(status)s, configuration_json=%(configuration_json)s::jsonb,
                    correlation_id=%(correlation_id)s, updated_at=%(updated_at)s,
                    archived_at=%(archived_at)s, failure_json=%(failure_json)s::jsonb,
                    metadata_json=%(metadata_json)s::jsonb, version=%(version)s,
                    job_id=%(job_id)s, replay_execution_id=%(replay_execution_id)s,
                    queued_at=%(queued_at)s, started_at=%(started_at)s,
                    execution_completed_at=%(execution_completed_at)s,
                    cancel_requested_at=%(cancel_requested_at)s,
                    cancelled_at=%(cancelled_at)s, attempt_count=%(attempt_count)s,
                    evaluation_job_id=%(evaluation_job_id)s,
                    baseline_evaluation_id=%(baseline_evaluation_id)s,
                    replay_evaluation_id=%(replay_evaluation_id)s,
                    comparison_id=%(comparison_id)s, drift_id=%(drift_id)s,
                    result_id=%(result_id)s,
                    evaluation_started_at=%(evaluation_started_at)s,
                    evaluation_completed_at=%(evaluation_completed_at)s,
                    comparison_started_at=%(comparison_started_at)s,
                    comparison_completed_at=%(comparison_completed_at)s,
                    completed_at=%(completed_at)s
                WHERE replay_id=%(replay_id)s AND organization_id=%(organization_id)s
                    AND project_id=%(project_id)s AND version=%(expected_version)s
                """,
                record,
            )
            if result.rowcount != 1:
                connection.rollback()
                raise ReplayConflict("Replay was modified by another request.")
            connection.commit()
        return stored
