"""PostgreSQL adapter for the durable Replay execution search projection."""

from __future__ import annotations

from typing import final

from kavach.databases.postgres.database import PostgresDatabase
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
class PostgresReplayExecutionCatalog(ReplayExecutionCatalog):
    """Tenant-scoped projection repository using atomic upsert and keysets."""

    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def get(
        self, execution_id: str, context: TenantContext
    ) -> ReplayExecutionProjection | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM replay_execution_catalog WHERE organization_id=%(organization_id)s AND project_id=%(project_id)s AND execution_id=%(execution_id)s",
                {
                    "organization_id": context.organization_id,
                    "project_id": context.project_id or "",
                    "execution_id": execution_id,
                },
            ).fetchone()
        return _projection(row) if row else None

    def search(
        self, filters: ReplayExecutionSearchFilters, context: TenantContext
    ) -> ReplayExecutionSearchPage:
        clauses = ["organization_id=%(organization_id)s", "project_id=%(project_id)s"]
        parameters: dict[str, object] = {
            "organization_id": context.organization_id,
            "project_id": context.project_id or "",
            "limit": filters.limit + 1,
        }
        if filters.query:
            clauses.append(
                "(execution_id ILIKE %(query)s OR workflow_id ILIKE %(query)s OR workflow_name ILIKE %(query)s)"
            )
            parameters["query"] = f"%{filters.query.strip()}%"
        for name, column, value, operator in (
            ("workflow_id", "workflow_id", filters.workflow_id, "="),
            ("status", "execution_status", filters.status, "="),
            ("created_after", "executed_at", filters.created_after, ">="),
            ("created_before", "executed_at", filters.created_before, "<"),
        ):
            if value is not None:
                clauses.append(f"{column}{operator}%({name})s")
                parameters[name] = value
        if filters.replayable_only:
            clauses.append("replayable=TRUE")
        cursor = _decode_cursor(filters.cursor)
        if cursor:
            clauses.append(
                "(executed_at<%(cursor_at)s OR (executed_at=%(cursor_at)s AND execution_id<%(cursor_id)s))"
            )
            parameters.update({"cursor_at": cursor[0], "cursor_id": cursor[1]})
        with self._database.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM replay_execution_catalog WHERE {' AND '.join(clauses)} ORDER BY executed_at DESC, execution_id DESC LIMIT %(limit)s",
                parameters,
            ).fetchall()
        projections = [_projection(row) for row in rows]
        has_more = len(projections) > filters.limit
        projections = projections[: filters.limit]
        return ReplayExecutionSearchPage(
            tuple(_search_item(item) for item in projections),
            _encode_cursor(projections[-1]) if has_more and projections else None,
            has_more,
        )

    def upsert(
        self, projection: ReplayExecutionProjection, context: TenantContext
    ) -> ReplayExecutionProjection:
        _check_scope(projection, context)
        with self._database.connect() as connection:
            connection.execute(
                """INSERT INTO replay_execution_catalog (organization_id, project_id, execution_id, workflow_id, workflow_name, workflow_version, execution_status, executed_at, completed_at, actor_id, actor_type, replayable, replayability_code, replayability_summary, evaluation_available, created_at, updated_at, projection_version)
                VALUES (%(organization_id)s, %(project_id)s, %(execution_id)s, %(workflow_id)s, %(workflow_name)s, %(workflow_version)s, %(execution_status)s, %(executed_at)s, %(completed_at)s, %(actor_id)s, %(actor_type)s, %(replayable)s, %(replayability_code)s, %(replayability_summary)s, %(evaluation_available)s, %(created_at)s, %(updated_at)s, %(projection_version)s)
                ON CONFLICT (organization_id, project_id, execution_id) DO UPDATE SET execution_status=EXCLUDED.execution_status, completed_at=EXCLUDED.completed_at, actor_id=EXCLUDED.actor_id, actor_type=EXCLUDED.actor_type, replayable=EXCLUDED.replayable, replayability_code=EXCLUDED.replayability_code, replayability_summary=EXCLUDED.replayability_summary, evaluation_available=EXCLUDED.evaluation_available, updated_at=EXCLUDED.updated_at, projection_version=EXCLUDED.projection_version""",
                projection.__dict__,
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
                "DELETE FROM replay_execution_catalog WHERE organization_id=%(organization_id)s AND project_id=%(project_id)s AND execution_id=%(execution_id)s",
                {
                    "organization_id": context.organization_id,
                    "project_id": context.project_id or "",
                    "execution_id": execution_id,
                },
            )
            connection.commit()
        return result.rowcount == 1


def _check_scope(projection: ReplayExecutionProjection, context: TenantContext) -> None:
    if (
        projection.organization_id != context.organization_id
        or projection.project_id != (context.project_id or "")
    ):
        raise ValueError("Replay execution projection does not belong to the tenant.")


def _projection(row) -> ReplayExecutionProjection:
    return ReplayExecutionProjection(
        execution_id=row["execution_id"],
        organization_id=row["organization_id"],
        project_id=row["project_id"],
        workflow_id=row["workflow_id"],
        workflow_name=row["workflow_name"],
        workflow_version=row["workflow_version"],
        execution_status=row["execution_status"],
        executed_at=row["executed_at"],
        completed_at=row["completed_at"],
        actor_id=row["actor_id"],
        actor_type=row["actor_type"],
        replayable=bool(row["replayable"]),
        replayability_code=row["replayability_code"],
        replayability_summary=row["replayability_summary"],
        evaluation_available=bool(row["evaluation_available"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        projection_version=row["projection_version"],
    )
