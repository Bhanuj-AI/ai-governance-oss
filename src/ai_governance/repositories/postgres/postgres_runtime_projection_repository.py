"""PostgreSQL persistence for runtime ontology projection state.

Stores projection state outside Neo4j so it survives graph outages
and process restarts. The Neo4j projection repository writes the graph;
this repository persists the authoritative state record.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import final

from ai_governance.databases.postgres.database import PostgresDatabase
from ai_governance.domain.agent_execution.projection import (
    ProjectionStatus,
    RuntimeOntologyProjection,
    UnresolvedReference,
)


@final
class PostgresRuntimeProjectionRepository:
    """PostgreSQL-backed runtime ontology projection state repository."""

    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def save_projection(
        self, projection: RuntimeOntologyProjection
    ) -> RuntimeOntologyProjection:
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO runtime_ontology_projection (
                    execution_id, organization_id, project_id, status,
                    projection_version, source_version, relationships_projected,
                    unresolved_json, last_projected_at, created_at, updated_at,
                    schema_version
                ) VALUES (
                    %(execution_id)s, %(organization_id)s, %(project_id)s,
                    %(status)s, %(projection_version)s, %(source_version)s,
                    %(relationships_projected)s, %(unresolved_json)s,
                    %(last_projected_at)s, %(created_at)s, %(updated_at)s,
                    %(schema_version)s
                ) ON CONFLICT (organization_id, project_id, execution_id) DO UPDATE SET
                    status=EXCLUDED.status,
                    projection_version=EXCLUDED.projection_version,
                    source_version=EXCLUDED.source_version,
                    relationships_projected=EXCLUDED.relationships_projected,
                    unresolved_json=EXCLUDED.unresolved_json,
                    last_projected_at=EXCLUDED.last_projected_at,
                    updated_at=EXCLUDED.updated_at
                """,
                {
                    "execution_id": projection.execution_id,
                    "organization_id": projection.organization_id,
                    "project_id": projection.project_id or "",
                    "status": projection.status.value,
                    "projection_version": projection.projection_version,
                    "source_version": projection.source_version,
                    "relationships_projected": projection.relationships_projected,
                    "unresolved_json": json.dumps(
                        [asdict(r) for r in projection.unresolved_references],
                        default=str,
                    ),
                    "last_projected_at": (
                        projection.last_projected_at.isoformat()
                        if projection.last_projected_at
                        else None
                    ),
                    "created_at": projection.created_at.isoformat(),
                    "updated_at": projection.updated_at.isoformat(),
                    "schema_version": "1",
                },
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
                WHERE organization_id=%(organization_id)s
                  AND project_id=%(project_id)s
                  AND execution_id=%(execution_id)s
                """,
                {
                    "organization_id": organization_id,
                    "project_id": project_id or "",
                    "execution_id": execution_id,
                },
            ).fetchone()
        if row is None:
            return None
        return _projection_from_row(row)

    def delete_projection(
        self,
        execution_id: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> bool:
        with self._database.connect() as connection:
            result = connection.execute(
                """
                DELETE FROM runtime_ontology_projection
                WHERE organization_id=%(organization_id)s
                  AND project_id=%(project_id)s
                  AND execution_id=%(execution_id)s
                """,
                {
                    "organization_id": organization_id,
                    "project_id": project_id or "",
                    "execution_id": execution_id,
                },
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
                WHERE organization_id=%(organization_id)s
                  AND project_id=%(project_id)s
                  AND status IN ('PENDING', 'FAILED')
                ORDER BY updated_at ASC
                LIMIT %(limit)s
                """,
                {
                    "organization_id": organization_id,
                    "project_id": project_id or "",
                    "limit": limit,
                },
            ).fetchall()
        return [_projection_from_row(row) for row in rows]

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
                WHERE organization_id=%(organization_id)s
                  AND project_id=%(project_id)s
                  AND execution_id=%(execution_id)s
                """,
                {
                    "organization_id": organization_id,
                    "project_id": project_id or "",
                    "execution_id": execution_id,
                },
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
                row["last_projected_at"].isoformat()
                if row.get("last_projected_at")
                else None
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
