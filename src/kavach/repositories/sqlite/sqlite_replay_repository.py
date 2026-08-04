from __future__ import annotations

import sqlite3
from dataclasses import replace
from typing import final

from kavach.databases.sqlite.database import SQLiteDatabase
from kavach.domain.replay import Replay
from kavach.domain.replay.errors import ReplayConflict, ReplayIdempotencyConflict
from kavach.repositories.mappers.replay_persistence_mapper import (
    ReplayPersistenceMapper,
)
from kavach.repositories.replay_repository import ReplayListFilters, ReplayRepository


@final
class SQLiteReplayRepository(ReplayRepository):
    _INSERT_SQL = """
    INSERT INTO replay (
        replay_id, source_execution_id, status, mode, configuration_json,
        requested_by, organization_id, project_id, request_id, correlation_id,
        idempotency_key, input_hash, created_at, updated_at, archived_at,
        failure_json, metadata_json, version
        , job_id, replay_execution_id, queued_at, started_at,
        execution_completed_at, cancel_requested_at, cancelled_at, attempt_count,
        evaluation_job_id, baseline_evaluation_id, replay_evaluation_id,
        comparison_id, drift_id, result_id, evaluation_started_at,
        evaluation_completed_at, comparison_started_at, comparison_completed_at,
        completed_at
    ) VALUES (
        :replay_id, :source_execution_id, :status, :mode, :configuration_json,
        :requested_by, :organization_id, :project_id, :request_id, :correlation_id,
        :idempotency_key, :input_hash, :created_at, :updated_at, :archived_at,
        :failure_json, :metadata_json, :version
        , :job_id, :replay_execution_id, :queued_at, :started_at,
        :execution_completed_at, :cancel_requested_at, :cancelled_at, :attempt_count,
        :evaluation_job_id, :baseline_evaluation_id, :replay_evaluation_id,
        :comparison_id, :drift_id, :result_id, :evaluation_started_at,
        :evaluation_completed_at, :comparison_started_at, :comparison_completed_at,
        :completed_at
    )
    """
    _SELECT_COLUMNS = """
    SELECT replay_id, source_execution_id, status, mode, configuration_json,
           requested_by, organization_id, project_id, request_id, correlation_id,
           idempotency_key, input_hash, created_at, updated_at, archived_at,
           failure_json, metadata_json, version
           , job_id, replay_execution_id, queued_at, started_at,
           execution_completed_at, cancel_requested_at, cancelled_at, attempt_count,
           evaluation_job_id, baseline_evaluation_id, replay_evaluation_id,
           comparison_id, drift_id, result_id, evaluation_started_at,
           evaluation_completed_at, comparison_started_at, comparison_completed_at,
           completed_at
    FROM replay
    """

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def save(self, replay: Replay, expected_version: int | None = None) -> Replay:
        if expected_version is None:
            return self._insert(replay)
        return self._update(replay, expected_version)

    def get(
        self, replay_id: str, organization_id: str, project_id: str
    ) -> Replay | None:
        with self._database.connect() as connection:
            row = connection.execute(
                f"{self._SELECT_COLUMNS} WHERE replay_id=? AND organization_id=? AND project_id=?",
                (replay_id, organization_id, project_id),
            ).fetchone()
        return ReplayPersistenceMapper.from_persistence_record(row) if row else None

    def list(
        self, filters: ReplayListFilters, organization_id: str, project_id: str
    ) -> list[Replay]:
        clauses = ["organization_id=?", "project_id=?"]
        parameters: list[object] = [organization_id, project_id]
        for clause, value in (
            ("status=?", filters.status.value if filters.status else None),
            ("source_execution_id=?", filters.source_execution_id),
            ("requested_by=?", filters.requested_by),
            (
                "created_at>=?",
                filters.created_after.isoformat() if filters.created_after else None,
            ),
            (
                "created_at<=?",
                filters.created_before.isoformat() if filters.created_before else None,
            ),
        ):
            if value is not None:
                clauses.append(clause)
                parameters.append(value)
        parameters.append(filters.limit)
        with self._database.connect() as connection:
            rows = connection.execute(
                f"{self._SELECT_COLUMNS} WHERE {' AND '.join(clauses)} "
                "ORDER BY created_at DESC, replay_id DESC LIMIT ?",
                parameters,
            ).fetchall()
        return [ReplayPersistenceMapper.from_persistence_record(row) for row in rows]

    def find_by_idempotency(
        self, idempotency_key: str, organization_id: str, project_id: str
    ) -> Replay | None:
        with self._database.connect() as connection:
            row = connection.execute(
                f"{self._SELECT_COLUMNS} WHERE idempotency_key=? AND organization_id=? AND project_id=?",
                (idempotency_key, organization_id, project_id),
            ).fetchone()
        return ReplayPersistenceMapper.from_persistence_record(row) if row else None

    def update(self, replay: Replay, expected_version: int) -> Replay:
        return self._update(replay, expected_version)

    def archive(self, replay: Replay, expected_version: int) -> Replay:
        return self._update(replay, expected_version)

    def _insert(self, replay: Replay) -> Replay:
        stored = replace(replay, version=1)
        try:
            with self._database.connect() as connection:
                connection.execute(
                    self._INSERT_SQL,
                    ReplayPersistenceMapper.to_persistence_record(stored),
                )
                connection.commit()
        except sqlite3.IntegrityError as exc:
            if "idempotency" in str(exc).lower():
                raise ReplayIdempotencyConflict(
                    "Replay idempotency key is already in use for this project."
                ) from exc
            raise ReplayConflict("Replay already exists.") from exc
        return stored

    def _update(self, replay: Replay, expected_version: int) -> Replay:
        stored = replace(replay, version=expected_version + 1)
        record = ReplayPersistenceMapper.to_persistence_record(stored)
        with self._database.connect() as connection:
            result = connection.execute(
                """
                UPDATE replay SET source_execution_id=:source_execution_id, status=:status,
                    mode=:mode, configuration_json=:configuration_json,
                    requested_by=:requested_by, request_id=:request_id,
                    correlation_id=:correlation_id, updated_at=:updated_at,
                    archived_at=:archived_at, failure_json=:failure_json,
                    metadata_json=:metadata_json, version=:version,
                    job_id=:job_id, replay_execution_id=:replay_execution_id,
                    queued_at=:queued_at, started_at=:started_at,
                    execution_completed_at=:execution_completed_at,
                    cancel_requested_at=:cancel_requested_at,
                    cancelled_at=:cancelled_at, attempt_count=:attempt_count,
                    evaluation_job_id=:evaluation_job_id,
                    baseline_evaluation_id=:baseline_evaluation_id,
                    replay_evaluation_id=:replay_evaluation_id,
                    comparison_id=:comparison_id, drift_id=:drift_id,
                    result_id=:result_id,
                    evaluation_started_at=:evaluation_started_at,
                    evaluation_completed_at=:evaluation_completed_at,
                    comparison_started_at=:comparison_started_at,
                    comparison_completed_at=:comparison_completed_at,
                    completed_at=:completed_at
                WHERE replay_id=:replay_id AND organization_id=:organization_id
                    AND project_id=:project_id AND version=:expected_version
                """,
                {**record, "expected_version": expected_version},
            )
            if result.rowcount != 1:
                connection.rollback()
                raise ReplayConflict("Replay was modified by another request.")
            connection.commit()
        return stored
