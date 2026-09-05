"""SQLite persistence for runtime ontology projection state.

Stores projection state outside Neo4j so it survives graph outages
and process restarts. The Neo4j projection repository writes the graph;
this repository persists the authoritative state record.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from threading import Lock
from typing import final

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.domain.agent_execution.projection import (
    ProjectionStatus,
    RuntimeOntologyProjection,
    UnresolvedReference,
)


@final
class SQLiteRuntimeProjectionRepository:
    """SQLite-backed runtime ontology projection state repository."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database
        self._lock = Lock()

    def save_projection(
        self, projection: RuntimeOntologyProjection
    ) -> RuntimeOntologyProjection:
        with self._lock:  # noqa: SIM117 - keep transaction ownership explicit.
            with self._database.connect() as connection:
                connection.execute(
                    """
                    INSERT INTO runtime_ontology_projection (
                        execution_id, organization_id, project_id, status,
                        projection_version, source_version, relationships_projected,
                        unresolved_json, last_projected_at, created_at, updated_at,
                        schema_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (organization_id, project_id, execution_id) DO UPDATE SET
                        status=excluded.status,
                        projection_version=excluded.projection_version,
                        source_version=excluded.source_version,
                        relationships_projected=excluded.relationships_projected,
                        unresolved_json=excluded.unresolved_json,
                        last_projected_at=excluded.last_projected_at,
                        updated_at=excluded.updated_at
                    """,
                    (
                        projection.execution_id,
                        projection.organization_id,
                        projection.project_id or "",
                        projection.status.value,
                        projection.projection_version,
                        projection.source_version,
                        projection.relationships_projected,
                        json.dumps(
                            [asdict(r) for r in projection.unresolved_references],
                            default=str,
                        ),
                        (
                            projection.last_projected_at.isoformat()
                            if projection.last_projected_at
                            else None
                        ),
                        projection.created_at.isoformat(),
                        projection.updated_at.isoformat(),
                        "1",
                    ),
                )
                connection.commit()
        return projection

    def get_projection(
        self,
        execution_id: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> RuntimeOntologyProjection | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM runtime_ontology_projection
                WHERE organization_id=? AND project_id=? AND execution_id=?
                """,
                (organization_id, project_id or "", execution_id),
            ).fetchone()
        if row is None:
            return None
        return _projection_from_row(dict(row))

    def delete_projection(
        self,
        execution_id: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> bool:
        with self._lock, self._database.connect() as connection:
            result = connection.execute(
                """
                    DELETE FROM runtime_ontology_projection
                    WHERE organization_id=? AND project_id=? AND execution_id=?
                    """,
                (organization_id, project_id or "", execution_id),
            )
            connection.commit()
        return bool(result and result.rowcount > 0)

    def list_pending_projections(
        self,
        organization_id: str,
        project_id: str | None = None,
        limit: int = 100,
    ) -> list[RuntimeOntologyProjection]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM runtime_ontology_projection
                WHERE organization_id=? AND project_id=?
                  AND status IN ('PENDING', 'FAILED')
                ORDER BY updated_at ASC
                LIMIT ?
                """,
                (organization_id, project_id or "", limit),
            ).fetchall()
        return [_projection_from_row(dict(row)) for row in rows]

    def get_projection_status(
        self,
        execution_id: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> dict | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT status, projection_version, source_version,
                       relationships_projected, unresolved_json, last_projected_at
                FROM runtime_ontology_projection
                WHERE organization_id=? AND project_id=? AND execution_id=?
                """,
                (organization_id, project_id or "", execution_id),
            ).fetchone()
        if row is None:
            return None
        unresolved_raw = row.get("unresolved_json")
        unresolved_count = 0
        if unresolved_raw:
            try:
                unresolved_count = len(json.loads(unresolved_raw))
            except (json.JSONDecodeError, TypeError):
                pass
        return {
            "execution_id": execution_id,
            "status": row["status"],
            "projection_version": row.get("projection_version"),
            "source_version": int(row.get("source_version", 0)),
            "relationships_projected": int(row.get("relationships_projected", 0)),
            "unresolved_references": unresolved_count,
            "last_projected_at": (
                row["last_projected_at"] if row.get("last_projected_at") else None
            ),
        }


def _projection_from_row(row: dict) -> RuntimeOntologyProjection:
    unresolved_raw = row.get("unresolved_json")
    unresolved_refs: list[UnresolvedReference] = []
    if unresolved_raw:
        try:
            for item in json.loads(unresolved_raw):
                unresolved_refs.append(
                    UnresolvedReference(
                        reference_type=item.get("reference_type", ""),
                        reference_id=item.get("reference_id", ""),
                        source_event_id=item.get("source_event_id", ""),
                    )
                )
        except (json.JSONDecodeError, TypeError):
            pass

    return RuntimeOntologyProjection(
        execution_id=row["execution_id"],
        organization_id=row["organization_id"],
        project_id=row.get("project_id") or None,
        status=ProjectionStatus(row["status"]),
        projection_version=row.get("projection_version", "1"),
        source_version=int(row.get("source_version", 0)),
        relationships_projected=int(row.get("relationships_projected", 0)),
        unresolved_references=tuple(unresolved_refs),
        last_projected_at=(
            datetime.fromisoformat(row["last_projected_at"])
            if row.get("last_projected_at")
            else None
        ),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )
