"""SQLite implementation of the durable Replay execution search projection."""

from __future__ import annotations

from datetime import datetime
from typing import final

from kavach.databases.sqlite.database import SQLiteDatabase
from kavach.services.replay_execution_discovery import (
    ReplayExecutionCatalog,
    ReplayExecutionProjection,
    ReplayExecutionSearchFilters,
    ReplayExecutionSearchPage,
    _decode_cursor,
    _encode_cursor,
    _search_item,
)
from kavach.tenancy.domain import TenantContext


@final
class SQLiteReplayExecutionCatalog(ReplayExecutionCatalog):
    """Durable tenant-scoped projection with keyset pagination."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def get(
        self, execution_id: str, context: TenantContext
    ) -> ReplayExecutionProjection | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM replay_execution_catalog WHERE organization_id=? AND project_id=? AND execution_id=?",
                (context.organization_id, context.project_id or "", execution_id),
            ).fetchone()
        return _projection(row) if row else None

    def search(
        self, filters: ReplayExecutionSearchFilters, context: TenantContext
    ) -> ReplayExecutionSearchPage:
        clauses = ["organization_id=?", "project_id=?"]
        parameters: list[object] = [context.organization_id, context.project_id or ""]
        if filters.query:
            like = f"%{filters.query.strip()}%"
            clauses.append(
                "(execution_id LIKE ? OR workflow_id LIKE ? OR workflow_name LIKE ?)"
            )
            parameters.extend((like, like, like))
        if filters.workflow_id:
            clauses.append("workflow_id=?")
            parameters.append(filters.workflow_id)
        if filters.status:
            clauses.append("execution_status=?")
            parameters.append(filters.status)
        if filters.created_after:
            clauses.append("executed_at>=?")
            parameters.append(filters.created_after.isoformat())
        if filters.created_before:
            clauses.append("executed_at<?")
            parameters.append(filters.created_before.isoformat())
        if filters.replayable_only:
            clauses.append("replayable=1")
        cursor = _decode_cursor(filters.cursor)
        if cursor:
            clauses.append("(executed_at<? OR (executed_at=? AND execution_id<?))")
            parameters.extend((cursor[0].isoformat(), cursor[0].isoformat(), cursor[1]))
        parameters.append(filters.limit + 1)
        with self._database.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM replay_execution_catalog WHERE {' AND '.join(clauses)} "
                "ORDER BY executed_at DESC, execution_id DESC LIMIT ?",
                parameters,
            ).fetchall()
        projections = [_projection(row) for row in rows]
        has_more = len(projections) > filters.limit
        projections = projections[: filters.limit]
        return ReplayExecutionSearchPage(
            items=tuple(_search_item(item) for item in projections),
            next_cursor=_encode_cursor(projections[-1])
            if has_more and projections
            else None,
            has_more=has_more,
        )

    def upsert(
        self, projection: ReplayExecutionProjection, context: TenantContext
    ) -> ReplayExecutionProjection:
        if (
            projection.organization_id != context.organization_id
            or projection.project_id != (context.project_id or "")
        ):
            raise ValueError(
                "Replay execution projection does not belong to the tenant."
            )
        record = _record(projection)
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO replay_execution_catalog (
                    organization_id, project_id, execution_id, workflow_id, workflow_name, workflow_version,
                    execution_status, executed_at, completed_at, actor_id, actor_type, replayable,
                    replayability_code, replayability_summary, evaluation_available, created_at, updated_at, projection_version
                ) VALUES (
                    :organization_id, :project_id, :execution_id, :workflow_id, :workflow_name, :workflow_version,
                    :execution_status, :executed_at, :completed_at, :actor_id, :actor_type, :replayable,
                    :replayability_code, :replayability_summary, :evaluation_available, :created_at, :updated_at, :projection_version
                ) ON CONFLICT(organization_id, project_id, execution_id) DO UPDATE SET
                    execution_status=excluded.execution_status, completed_at=excluded.completed_at,
                    actor_id=excluded.actor_id, actor_type=excluded.actor_type, replayable=excluded.replayable,
                    replayability_code=excluded.replayability_code, replayability_summary=excluded.replayability_summary,
                    evaluation_available=excluded.evaluation_available, updated_at=excluded.updated_at,
                    projection_version=excluded.projection_version
                """,
                record,
            )
            connection.commit()
        return projection

    def upsert_many(
        self, projections: tuple[ReplayExecutionProjection, ...], context: TenantContext
    ) -> int:
        for projection in projections:
            self.upsert(projection, context)
        return len(projections)

    def delete(self, execution_id: str, context: TenantContext) -> bool:
        with self._database.connect() as connection:
            result = connection.execute(
                "DELETE FROM replay_execution_catalog WHERE organization_id=? AND project_id=? AND execution_id=?",
                (context.organization_id, context.project_id or "", execution_id),
            )
            connection.commit()
        return result.rowcount == 1


def _record(projection: ReplayExecutionProjection) -> dict[str, object]:
    return {
        name: (
            value.isoformat()
            if isinstance(value, datetime)
            else int(value)
            if isinstance(value, bool)
            else value
        )
        for name, value in projection.__dict__.items()
    }


def _projection(row) -> ReplayExecutionProjection:
    return ReplayExecutionProjection(
        execution_id=row["execution_id"],
        organization_id=row["organization_id"],
        project_id=row["project_id"],
        workflow_id=row["workflow_id"],
        workflow_name=row["workflow_name"],
        workflow_version=row["workflow_version"],
        execution_status=row["execution_status"],
        executed_at=datetime.fromisoformat(row["executed_at"]),
        completed_at=datetime.fromisoformat(row["completed_at"])
        if row["completed_at"]
        else None,
        actor_id=row["actor_id"],
        actor_type=row["actor_type"],
        replayable=bool(row["replayable"]),
        replayability_code=row["replayability_code"],
        replayability_summary=row["replayability_summary"],
        evaluation_available=bool(row["evaluation_available"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        projection_version=row["projection_version"],
    )
