from __future__ import annotations

import sqlite3

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.domain.replay import ReplayResult
from ai_governance.domain.replay.errors import ReplayResultConflict
from ai_governance.repositories.mappers.replay_result_persistence_mapper import (
    ReplayResultPersistenceMapper,
)
from ai_governance.repositories.replay_result_repository import (
    ReplayResultListFilters,
    ReplayResultRepository,
)


class SQLiteReplayResultRepository(ReplayResultRepository):
    _COLUMNS = "result_id, replay_id, source_execution_id, replay_execution_id, baseline_evaluation_id, replay_evaluation_id, comparison_id, drift_id, baseline_strategy, comparison_summary_json, drift_summary_json, organization_id, project_id, created_at, metadata_json"

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def save(self, result: ReplayResult) -> ReplayResult:
        record = ReplayResultPersistenceMapper.to_persistence_record(result)
        try:
            with self._database.connect() as connection:
                existing = connection.execute(
                    "SELECT * FROM replay_result WHERE result_id=? OR replay_id=?",
                    (result.result_id, result.replay_id),
                ).fetchone()
                if existing:
                    persisted = ReplayResultPersistenceMapper.from_persistence_record(
                        existing
                    )
                    if persisted == result:
                        return persisted
                    raise ReplayResultConflict(
                        "A conflicting ReplayResult already exists."
                    )
                connection.execute(
                    f"INSERT INTO replay_result ({self._COLUMNS}) VALUES ({','.join(':' + key for key in record)})",
                    record,
                )
                connection.commit()
        except sqlite3.IntegrityError as error:
            raise ReplayResultConflict(
                "A conflicting ReplayResult already exists."
            ) from error
        return result

    def get(
        self, result_id: str, organization_id: str, project_id: str
    ) -> ReplayResult | None:
        return self._one(
            "result_id=? AND organization_id=? AND project_id=?",
            (result_id, organization_id, project_id),
        )

    def get_by_replay(
        self, replay_id: str, organization_id: str, project_id: str
    ) -> ReplayResult | None:
        return self._one(
            "replay_id=? AND organization_id=? AND project_id=?",
            (replay_id, organization_id, project_id),
        )

    def list(
        self, filters: ReplayResultListFilters, organization_id: str, project_id: str
    ) -> list[ReplayResult]:
        clauses, values = (
            ["organization_id=?", "project_id=?"],
            [organization_id, project_id],
        )
        for clause, value in (
            ("source_execution_id=?", filters.source_execution_id),
            ("replay_execution_id=?", filters.replay_execution_id),
            (
                "json_extract(drift_summary_json, '$.severity')=?",
                filters.drift_severity,
            ),
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
                values.append(value)
        if filters.cursor:
            clauses.append("result_id<?")
            values.append(filters.cursor)
        values.append(filters.limit)
        with self._database.connect() as connection:
            rows = connection.execute(
                f"SELECT {self._COLUMNS} FROM replay_result WHERE {' AND '.join(clauses)} ORDER BY created_at DESC, result_id DESC LIMIT ?",
                values,
            ).fetchall()
        return [
            ReplayResultPersistenceMapper.from_persistence_record(row) for row in rows
        ]

    def _one(self, clause: str, values: tuple[str, str, str]) -> ReplayResult | None:
        with self._database.connect() as connection:
            row = connection.execute(
                f"SELECT {self._COLUMNS} FROM replay_result WHERE {clause}", values
            ).fetchone()
        return (
            ReplayResultPersistenceMapper.from_persistence_record(row) if row else None
        )
