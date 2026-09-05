"""In-memory projection repository for unit tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ai_governance.domain.agent_execution import (
    AgentExecution,
    AgentExecutionEvent,
)
from ai_governance.domain.agent_execution.projection import (
    ProjectionStatus,
    RuntimeOntologyProjection,
)
from ai_governance.repositories.neo4j_projection_repository import (
    Neo4jProjectionRepository,
)


class InMemoryProjectionRepository(Neo4jProjectionRepository):
    """In-memory projection store for deterministic unit tests."""

    def __init__(self) -> None:
        self._projections: dict[str, RuntimeOntologyProjection] = {}
        self._graph_nodes: dict[str, dict[str, Any]] = {}
        self._graph_edges: list[dict[str, Any]] = []

    def close(self) -> None:
        pass

    def initialize_schema(self) -> None:
        pass

    def save_projection(
        self, projection: RuntimeOntologyProjection
    ) -> RuntimeOntologyProjection:
        self._projections[projection.execution_id] = projection
        return projection

    def get_projection(
        self,
        execution_id: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> RuntimeOntologyProjection | None:
        return self._projections.get(execution_id)

    def list_pending_projections(
        self,
        organization_id: str,
        limit: int = 100,
    ) -> list[RuntimeOntologyProjection]:
        return [
            p
            for p in self._projections.values()
            if p.status in (ProjectionStatus.PENDING, ProjectionStatus.FAILED)
        ][:limit]

    def project_execution(
        self,
        execution: AgentExecution,
        events: list[AgentExecutionEvent],
        source_version: int,
    ) -> RuntimeOntologyProjection:
        """Project execution into in-memory graph store."""
        # Store the execution node.
        self._graph_nodes[execution.execution_id] = {
            "label": "AgentExecutionProjection",
            "properties": {
                "execution_id": execution.execution_id,
                "agent_id": execution.agent_id,
                "status": execution.status.value,
            },
        }

        # Process events to create edges (idempotent: skip duplicates).
        rel_count = 0
        existing_keys = {(e["source"], e["target"], e["type"]) for e in self._graph_edges}
        for event in events:
            if event.event_type.value == "MODEL_CALL":
                model_id = event.attributes.get("model") or event.attributes.get("model_reference")
                if model_id:
                    key = (execution.execution_id, model_id, "USED_MODEL")
                    if key not in existing_keys:
                        self._graph_edges.append({
                            "source": execution.execution_id,
                            "target": model_id,
                            "type": "USED_MODEL",
                        })
                        existing_keys.add(key)
                        rel_count += 1

            elif event.event_type.value == "TOOL_CALL":
                tool_id = event.attributes.get("tool") or event.attributes.get("tool_id") or event.attributes.get("tool_identity")
                if tool_id:
                    key = (execution.execution_id, tool_id, "CALLED_TOOL")
                    if key not in existing_keys:
                        self._graph_edges.append({
                            "source": execution.execution_id,
                            "target": tool_id,
                            "type": "CALLED_TOOL",
                        })
                        existing_keys.add(key)
                        rel_count += 1

            elif event.event_type.value == "GOVERNANCE_DECISION":
                decision_id = event.attributes.get("decision_id") or event.attributes.get("governance_decision_id")
                if decision_id:
                    key = (execution.execution_id, decision_id, "PRODUCED")
                    if key not in existing_keys:
                        self._graph_edges.append({
                            "source": execution.execution_id,
                            "target": decision_id,
                            "type": "PRODUCED",
                        })
                        existing_keys.add(key)
                        rel_count += 1
                policy_id = event.attributes.get("policy_id") or event.attributes.get("policy_reference")
                if policy_id:
                    key = (execution.execution_id, policy_id, "GOVERNED_BY")
                    if key not in existing_keys:
                        self._graph_edges.append({
                            "source": execution.execution_id,
                            "target": policy_id,
                            "type": "GOVERNED_BY",
                        })
                        existing_keys.add(key)
                        rel_count += 1

            elif event.event_type.value == "EVALUATION":
                eval_id = event.attributes.get("evaluation_result_id") or event.attributes.get("evaluation_id")
                if eval_id:
                    key = (execution.execution_id, eval_id, "EVALUATED_BY")
                    if key not in existing_keys:
                        self._graph_edges.append({
                            "source": execution.execution_id,
                            "target": eval_id,
                            "type": "EVALUATED_BY",
                        })
                        existing_keys.add(key)
                        rel_count += 1

            for ref in event.resource_references:
                if not ref.strip():
                    continue
                key = (execution.execution_id, ref, "ACCESSED")
                if key not in existing_keys:
                    self._graph_edges.append({
                        "source": execution.execution_id,
                        "target": ref,
                        "type": "ACCESSED",
                    })
                    existing_keys.add(key)
                    rel_count += 1

        now = datetime.now(UTC)
        # Preserve existing relationship count on re-projection.
        existing_proj = self._projections.get(execution.execution_id)
        if existing_proj and existing_proj.status == ProjectionStatus.PROJECTED:
            rel_count = max(rel_count, existing_proj.relationships_projected)

        projection = RuntimeOntologyProjection(
            execution_id=execution.execution_id,
            organization_id=execution.organization_id,
            project_id=execution.project_id,
            status=ProjectionStatus.PROJECTED,
            source_version=source_version,
            relationships_projected=rel_count,
            last_projected_at=now,
            updated_at=now,
        )
        self._projections[execution.execution_id] = projection
        return projection

    def delete_projection(self, execution_id: str) -> bool:
        removed = execution_id in self._projections
        if removed:
            del self._projections[execution_id]
        # Also clean graph data.
        self._graph_nodes.pop(execution_id, None)
        self._graph_edges = [
            e for e in self._graph_edges if e["source"] != execution_id
        ]
        return removed

    def get_projection_status(
        self,
        execution_id: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        projection = self._projections.get(execution_id)
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

    @property
    def graph_nodes(self) -> dict[str, dict[str, Any]]:
        return dict(self._graph_nodes)

    @property
    def graph_edges(self) -> list[dict[str, Any]]:
        return list(self._graph_edges)
