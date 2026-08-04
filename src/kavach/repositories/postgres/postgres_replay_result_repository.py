from __future__ import annotations

from kavach.databases.postgres.database import PostgresDatabase
from kavach.domain.replay import ReplayResult
from kavach.domain.replay.errors import ReplayResultConflict
from kavach.repositories.mappers.replay_result_persistence_mapper import (
    ReplayResultPersistenceMapper,
)
from kavach.repositories.replay_result_repository import (
    ReplayResultListFilters,
    ReplayResultRepository,
)


class PostgresReplayResultRepository(ReplayResultRepository):
    _COLUMNS = "result_id, replay_id, source_execution_id, replay_execution_id, baseline_evaluation_id, replay_evaluation_id, comparison_id, drift_id, baseline_strategy, comparison_summary_json::text AS comparison_summary_json, drift_summary_json::text AS drift_summary_json, organization_id, project_id, created_at::text AS created_at, metadata_json::text AS metadata_json"

    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def save(self, result: ReplayResult) -> ReplayResult:
        record = ReplayResultPersistenceMapper.to_persistence_record(result)
        existing = self.get_by_replay(
            result.replay_id, result.organization_id, result.project_id
        )
        if existing:
            if existing == result:
                return existing
            raise ReplayResultConflict(
                "A finalized ReplayResult already exists for replay."
            )
        try:
            with self._database.connect() as connection:
                connection.execute(
                    """INSERT INTO replay_result (result_id,replay_id,source_execution_id,replay_execution_id,baseline_evaluation_id,replay_evaluation_id,comparison_id,drift_id,baseline_strategy,comparison_summary_json,drift_summary_json,organization_id,project_id,created_at,metadata_json)
                    VALUES (%(result_id)s,%(replay_id)s,%(source_execution_id)s,%(replay_execution_id)s,%(baseline_evaluation_id)s,%(replay_evaluation_id)s,%(comparison_id)s,%(drift_id)s,%(baseline_strategy)s,%(comparison_summary_json)s::jsonb,%(drift_summary_json)s::jsonb,%(organization_id)s,%(project_id)s,%(created_at)s,%(metadata_json)s::jsonb)""",
                    record,
                )
                connection.commit()
        except Exception as error:
            raise ReplayResultConflict(
                "A conflicting ReplayResult already exists."
            ) from error
        return result

    def get(
        self, result_id: str, organization_id: str, project_id: str
    ) -> ReplayResult | None:
        return self._one(
            "result_id=%(result_id)s AND organization_id=%(organization_id)s AND project_id=%(project_id)s",
            {
                "result_id": result_id,
                "organization_id": organization_id,
                "project_id": project_id,
            },
        )

    def get_by_replay(
        self, replay_id: str, organization_id: str, project_id: str
    ) -> ReplayResult | None:
        return self._one(
            "replay_id=%(replay_id)s AND organization_id=%(organization_id)s AND project_id=%(project_id)s",
            {
                "replay_id": replay_id,
                "organization_id": organization_id,
                "project_id": project_id,
            },
        )

    def list(
        self, filters: ReplayResultListFilters, organization_id: str, project_id: str
    ) -> list[ReplayResult]:
        clauses, params = (
            ["organization_id=%(organization_id)s", "project_id=%(project_id)s"],
            {
                "organization_id": organization_id,
                "project_id": project_id,
                "limit": filters.limit,
            },
        )
        for name, clause, value in (
            (
                "source_execution_id",
                "source_execution_id=%(source_execution_id)s",
                filters.source_execution_id,
            ),
            (
                "replay_execution_id",
                "replay_execution_id=%(replay_execution_id)s",
                filters.replay_execution_id,
            ),
            (
                "drift_severity",
                "drift_summary_json->>'severity'=%(drift_severity)s",
                filters.drift_severity,
            ),
            ("created_after", "created_at>=%(created_after)s", filters.created_after),
            (
                "created_before",
                "created_at<=%(created_before)s",
                filters.created_before,
            ),
        ):
            if value is not None:
                clauses.append(clause)
                params[name] = value
        if filters.cursor:
            clauses.append("result_id<%(cursor)s")
            params["cursor"] = filters.cursor
        with self._database.connect() as connection:
            rows = connection.execute(
                f"SELECT {self._COLUMNS} FROM replay_result WHERE {' AND '.join(clauses)} ORDER BY created_at DESC,result_id DESC LIMIT %(limit)s",
                params,
            ).fetchall()
        return [
            ReplayResultPersistenceMapper.from_persistence_record(row) for row in rows
        ]

    def _one(self, where: str, params: dict[str, str]) -> ReplayResult | None:
        with self._database.connect() as connection:
            row = connection.execute(
                f"SELECT {self._COLUMNS} FROM replay_result WHERE {where}", params
            ).fetchone()
        return (
            ReplayResultPersistenceMapper.from_persistence_record(row) if row else None
        )
