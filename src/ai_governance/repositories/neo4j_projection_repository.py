"""Neo4j-backed runtime ontology projection repository.

Projects AgentExecution aggregates and their events from PostgreSQL
into Neo4j as derived graph state. All writes are idempotent via
MERGE + SET operations keyed on execution_id and relationship
aggregation properties.

This repository is deliberately isolated from the ontology layer.
It writes directly to Neo4j using its own schema (labels, relationship
types) that are separate from the governance ontology entities.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from ai_governance.config import (
    AI_GOVERNANCE_GRAPH_DATABASE,
    AI_GOVERNANCE_GRAPH_PASSWORD,
    AI_GOVERNANCE_GRAPH_URI,
    AI_GOVERNANCE_GRAPH_USER,
)
from ai_governance.domain.agent_execution import (
    AgentExecution,
    AgentExecutionEvent,
    EventType,
)
from ai_governance.domain.agent_execution.projection import (
    ProjectionStatus,
    RuntimeOntologyProjection,
    UnresolvedReference,
)

# ---------------------------------------------------------------------------
# Cypher schema statements
# ---------------------------------------------------------------------------

_PROJECTION_SCHEMA_CYPHER = [
    """
    CREATE CONSTRAINT execution_id_unique IF NOT EXISTS
    FOR (e:AgentExecutionProjection) REQUIRE e.execution_id IS UNIQUE
    """,
    """
    CREATE INDEX execution_projection_tenant IF NOT EXISTS
    FOR (e:AgentExecutionProjection) ON (e.organization_id, e.project_id)
    """,
    """
    CREATE INDEX execution_projection_status IF NOT EXISTS
    FOR (e:AgentExecutionProjection) ON (e.status)
    """,
]

# Schema version for this projection layer.
_PROJECTION_SCHEMA_VERSION = "1"


class Neo4jProjectionRepository:
    """Neo4j persistence for runtime ontology projections.

    All writes are idempotent: re-projecting the same execution produces
    an identical graph state. Failed projections can be retried without
    risk of duplication.
    """

    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
        *,
        database: str = "neo4j",
        driver: Any | None = None,
        durable_projection_repo: Any | None = None,
    ) -> None:
        self._database = database
        self._durable_repo = durable_projection_repo
        if driver is not None:
            self._driver = driver
            return

        try:
            from neo4j import GraphDatabase  # type: ignore
        except ImportError as exc:
            raise MissingNeo4jDriverError(
                "The Neo4j Python driver is required for "
                "Neo4jProjectionRepository. Install the `neo4j` package "
                "before using the graph adapter."
            ) from exc

        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    @classmethod
    def from_environment(
        cls,
        durable_projection_repo: Any | None = None,
    ) -> Neo4jProjectionRepository:
        """Build a repository from local graph environment variables.

        When ``durable_projection_repo`` is provided, state persistence
        delegates to it so projection state survives Neo4j outages.
        """
        return cls(
            uri=AI_GOVERNANCE_GRAPH_URI,
            user=AI_GOVERNANCE_GRAPH_USER,
            password=AI_GOVERNANCE_GRAPH_PASSWORD,
            database=AI_GOVERNANCE_GRAPH_DATABASE,
            durable_projection_repo=durable_projection_repo,
        )

    def close(self) -> None:
        """Close the underlying Neo4j driver."""
        self._driver.close()

    def initialize_schema(self) -> None:
        """Create projection constraints and indexes."""
        with self._session() as session:
            for statement in _PROJECTION_SCHEMA_CYPHER:
                session.run(statement)

    # -- Projection state -----------------------------------------------------

    def save_projection(
        self,
        projection: RuntimeOntologyProjection,
    ) -> RuntimeOntologyProjection:
        """Persist or update projection state.

        Delegates to the durable projection repository when available so
        state survives Neo4j outages. Falls back to Neo4j-only storage
        when no durable repository is configured.
        """
        if self._durable_repo is not None:
            return self._durable_repo.save_projection(projection)
        with self._session() as session:
            session.run(
                """
                MERGE (p:AgentExecutionProjection {execution_id: $execution_id})
                SET p.organization_id = $organization_id,
                    p.project_id = $project_id,
                    p.status = $status,
                    p.projection_version = $projection_version,
                    p.source_version = $source_version,
                    p.relationships_projected = $relationships_projected,
                    p.unresolved_json = $unresolved_json,
                    p.last_projected_at = $last_projected_at,
                    p.created_at = $created_at,
                    p.updated_at = $updated_at,
                    p.schema_version = $schema_version
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
                    "schema_version": _PROJECTION_SCHEMA_VERSION,
                },
            )
        return projection

    def get_projection(
        self,
        execution_id: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> RuntimeOntologyProjection | None:
        """Retrieve projection state for an execution.

        Delegates to the durable projection repository when available.
        """
        if self._durable_repo is not None:
            return self._durable_repo.get_projection(
                execution_id, organization_id, project_id
            )
        with self._session() as session:
            result = session.run(
                """
                MATCH (p:AgentExecutionProjection {execution_id: $execution_id})
                WHERE p.organization_id = $organization_id
                  AND ($project_id = '' OR p.project_id = $project_id)
                RETURN p
                """,
                {
                    "execution_id": execution_id,
                    "organization_id": organization_id,
                    "project_id": project_id or "",
                },
            )
            record = result.single()
        if record is None:
            return None
        return _projection_from_record(record["p"])

    def list_pending_projections(
        self,
        organization_id: str,
        limit: int = 100,
    ) -> list[RuntimeOntologyProjection]:
        """Find projections that need retry (PENDING or FAILED).

        Delegates to the durable projection repository when available.
        """
        if self._durable_repo is not None:
            return self._durable_repo.list_pending_projections(
                organization_id, limit=limit
            )
        with self._session() as session:
            result = session.run(
                """
                MATCH (p:AgentExecutionProjection)
                WHERE p.organization_id = $organization_id
                  AND p.status IN ['PENDING', 'FAILED']
                RETURN p ORDER BY p.updated_at ASC LIMIT $limit
                """,
                {
                    "organization_id": organization_id,
                    "limit": limit,
                },
            )
        return [_projection_from_record(record["p"]) for record in result]

    # -- Graph projection (execution + relationships) -------------------------

    def project_execution(
        self,
        execution: AgentExecution,
        events: list[AgentExecutionEvent],
        source_version: int,
    ) -> RuntimeOntologyProjection:
        """Project an execution and its events into Neo4j.

        Creates the AgentExecutionProjection node and all relationships
        (USED_MODEL, CALLED_TOOL, ACCESSED, PRODUCED, GOVERNED_BY,
        EVALUATED_BY, PARENT_OF) in a single transaction.

        Returns the updated projection state.
        """
        unresolved: list[UnresolvedReference] = []
        rel_count = 0

        with self._session() as session:
            # 1. Create/update the execution projection node.
            session.run(
                """
                MERGE (e:AgentExecutionProjection {execution_id: $execution_id})
                SET e.external_execution_id = $external_execution_id,
                    e.organization_id = $organization_id,
                    e.project_id = $project_id,
                    e.agent_id = $agent_id,
                    e.agent_name = $agent_name,
                    e.agent_version = $agent_version,
                    e.runtime_provider = $runtime_provider,
                    e.status = $status,
                    e.started_at = $started_at,
                    e.completed_at = $completed_at,
                    e.correlation_id = $correlation_id,
                    e.parent_execution_id = $parent_execution_id,
                    e.projection_version = $projection_version,
                    e.source_version = $source_version,
                    e.last_projected_at = $last_projected_at,
                    e.schema_version = $schema_version
                """,
                {
                    "execution_id": execution.execution_id,
                    "external_execution_id": execution.external_execution_id,
                    "organization_id": execution.organization_id,
                    "project_id": execution.project_id or "",
                    "agent_id": execution.agent_id,
                    "agent_name": execution.agent_name,
                    "agent_version": execution.agent_version,
                    "runtime_provider": execution.runtime_provider,
                    "status": execution.status.value,
                    "started_at": _datetime_to_string(execution.started_at),
                    "completed_at": (
                        _datetime_to_string(execution.completed_at)
                        if execution.completed_at
                        else None
                    ),
                    "correlation_id": execution.correlation_id,
                    "parent_execution_id": execution.parent_execution_id,
                    "projection_version": _PROJECTION_SCHEMA_VERSION,
                    "source_version": source_version,
                    "last_projected_at": datetime.now(UTC).isoformat(),
                    "schema_version": _PROJECTION_SCHEMA_VERSION,
                },
            )

            # 2. Process events to create relationships.
            for event in events:
                created = self._project_event_relationships(
                    session, execution, event, unresolved
                )
                rel_count += created

            # 3. Create parent-child relationship if applicable.
            if execution.parent_execution_id:
                session.run(
                    """
                    MATCH (parent:AgentExecutionProjection {execution_id: $parent_id})
                    MATCH (child:AgentExecutionProjection {execution_id: $child_id})
                    WHERE parent.organization_id = child.organization_id
                    MERGE (parent)-[:PARENT_OF]->(child)
                    """,
                    {
                        "parent_id": execution.parent_execution_id,
                        "child_id": execution.execution_id,
                    },
                )
                rel_count += 1

            # 4. Update projection state record.
            unresolved_refs = tuple(unresolved)
            projection = RuntimeOntologyProjection(
                execution_id=execution.execution_id,
                organization_id=execution.organization_id,
                project_id=execution.project_id,
                status=ProjectionStatus.PROJECTED,
                projection_version=_PROJECTION_SCHEMA_VERSION,
                source_version=source_version,
                relationships_projected=rel_count,
                unresolved_references=unresolved_refs,
                last_projected_at=datetime.now(UTC),
            )
            session.run(
                """
                MERGE (p:AgentExecutionProjection {execution_id: $execution_id})
                SET p.status = $status,
                    p.source_version = $source_version,
                    p.relationships_projected = $rel_count,
                    p.unresolved_json = $unresolved_json,
                    p.last_projected_at = $last_projected_at,
                    p.updated_at = $updated_at
                """,
                {
                    "execution_id": execution.execution_id,
                    "status": projection.status.value,
                    "source_version": source_version,
                    "rel_count": rel_count,
                    "unresolved_json": json.dumps(
                        [asdict(r) for r in unresolved_refs], default=str
                    ),
                    "last_projected_at": projection.last_projected_at.isoformat(),
                    "updated_at": projection.updated_at.isoformat(),
                },
            )

        return projection

    def _project_event_relationships(
        self,
        session: Any,
        execution: AgentExecution,
        event: AgentExecutionEvent,
        unresolved: list[UnresolvedReference],
    ) -> int:
        """Project relationships from a single event. Returns count."""
        created = 0

        if event.event_type == EventType.MODEL_CALL:
            model_id = event.attributes.get("model") or event.attributes.get("model_reference")
            if model_id:
                created += self._merge_relationship(
                    session, execution.execution_id, model_id, "Model", "USED_MODEL"
                )

        elif event.event_type == EventType.TOOL_CALL:
            tool_id = event.attributes.get("tool") or event.attributes.get("tool_id") or event.attributes.get("tool_identity")
            if tool_id:
                created += self._merge_relationship(
                    session, execution.execution_id, tool_id, "Tool", "CALLED_TOOL"
                )

        elif event.event_type == EventType.GOVERNANCE_DECISION:
            decision_id = event.attributes.get("decision_id") or event.attributes.get("governance_decision_id")
            if decision_id:
                created += self._merge_relationship(
                    session, execution.execution_id, decision_id, "GovernanceDecision", "PRODUCED"
                )
            policy_id = event.attributes.get("policy_id") or event.attributes.get("policy_reference")
            if policy_id:
                created += self._merge_relationship(
                    session, execution.execution_id, policy_id, "Policy", "GOVERNED_BY"
                )

        elif event.event_type == EventType.EVALUATION:
            eval_id = event.attributes.get("evaluation_result_id") or event.attributes.get("evaluation_id")
            if eval_id:
                created += self._merge_relationship(
                    session, execution.execution_id, eval_id, "EvaluationResult", "EVALUATED_BY"
                )

        # Resource references → ACCESSED relationships.
        for ref in event.resource_references:
            if not ref.strip():
                continue
            # Parse typed reference: "type:id" or just "id" (assumed GovernedAsset).
            if ":" in ref:
                ref_type, ref_id = ref.split(":", 1)
            else:
                ref_type = "GovernedAsset"
                ref_id = ref
            created += self._merge_relationship(
                session, execution.execution_id, ref_id, ref_type, "ACCESSED"
            )

        return created

    def _merge_relationship(
        self,
        session: Any,
        execution_id: str,
        target_id: str,
        target_label: str,
        relationship_type: str,
    ) -> int:
        """MERGE a relationship from execution projection node to target.

        Returns 1 if created, 0 if already existed (idempotent).
        """
        result = session.run(
            f"""
            MATCH (e:AgentExecutionProjection {{execution_id: $execution_id}})
            MERGE (t:{target_label} {{entity_id: $target_id}})
            ON CREATE SET t.entity_id = $target_id,
                          t.organization_id = $organization_id,
                          t.created_at = $now
            MERGE (e)-[r:{relationship_type}]->(t)
            ON CREATE SET r.created_at = $now,
                          r.call_count = 1
            ON MATCH SET r.call_count = (r.call_count + 1),
                         r.last_seen_at = $now
            RETURN elementId(r) AS rel_id
            """,
            {
                "execution_id": execution_id,
                "target_id": target_id,
                "organization_id": "",  # Tenant scope enforced at query level
                "now": datetime.now(UTC).isoformat(),
            },
        )
        record = result.single()
        return 1 if record is not None else 0

    def delete_projection(self, execution_id: str) -> bool:
        """Delete all projection data for an execution (rebuild support).

        Delegates to the durable projection repository when available.
        """
        if self._durable_repo is not None:
            return self._durable_repo.delete_projection(
                execution_id, "", None
            )
        with self._session() as session:
            result = session.run(
                """
                MATCH (e:AgentExecutionProjection {execution_id: $execution_id})
                DETACH DELETE e
                RETURN count(e) AS deleted
                """,
                {"execution_id": execution_id},
            )
            record = result.single()
        return bool(record and int(record["deleted"]) > 0)

    def get_projection_status(
        self,
        execution_id: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Get a lightweight projection status dict.

        Delegates to the durable projection repository when available.
        """
        if self._durable_repo is not None:
            return self._durable_repo.get_projection_status(
                execution_id, organization_id, project_id
            )
        projection = self.get_projection(
            execution_id, organization_id, project_id
        )
        if projection is None:
            return {
                "execution_id": execution_id,
                "status": "NOT_FOUND",
                "relationships_projected": 0,
                "unresolved_references": 0,
            }
        return {
            "execution_id": projection.execution_id,
            "status": projection.status.value,
            "projection_version": projection.projection_version,
            "source_version": projection.source_version,
            "relationships_projected": projection.relationships_projected,
            "unresolved_references": projection.unresolved_count,
            "last_projected_at": (
                projection.last_projected_at.isoformat()
                if projection.last_projected_at
                else None
            ),
        }

    # -- Session management ---------------------------------------------------

    def _session(self) -> Any:
        return self._driver.session(database=self._database)


class MissingNeo4jDriverError(ImportError):
    """Raised when the Neo4j Python driver is not installed."""


# -- Cypher property mappers --------------------------------------------------


def _projection_from_record(record: Any) -> RuntimeOntologyProjection:
    """Build a projection aggregate from a Neo4j node record."""
    import json as _json

    props = dict(record)
    unresolved_raw = props.get("unresolved_json")
    unresolved_refs: list[UnresolvedReference] = []
    if unresolved_raw:
        try:
            for item in _json.loads(unresolved_raw):
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
        execution_id=props["execution_id"],
        organization_id=props.get("organization_id", ""),
        project_id=props.get("project_id") or None,
        status=ProjectionStatus(props.get("status", "PENDING")),
        projection_version=props.get("projection_version", _PROJECTION_SCHEMA_VERSION),
        source_version=int(props.get("source_version", 0)),
        relationships_projected=int(props.get("relationships_projected", 0)),
        unresolved_references=tuple(unresolved_refs),
        last_projected_at=(
            datetime.fromisoformat(props["last_projected_at"])
            if props.get("last_projected_at")
            else None
        ),
        created_at=datetime.fromisoformat(props.get("created_at", "")),
        updated_at=datetime.fromisoformat(props.get("updated_at", "")),
    )


def _datetime_to_string(value: datetime) -> str:
    return value.isoformat()
