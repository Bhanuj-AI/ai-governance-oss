"""Application service for runtime ontology projection.

Reads AgentExecution aggregates and events from PostgreSQL,
projects them into Neo4j as derived graph state.

Projection is asynchronous and isolated from the synchronous
runtime ingestion path. If Neo4j is unavailable, execution
persistence continues unaffected.
"""

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
from ai_governance.domain.agent_execution.projection_errors import (
    Neo4jWriteError,
    ProjectionNotFound,
)


class OntologyProjectionService:
    """Orchestrates runtime-to-graph projection.

    This service reads authoritative data from the PostgreSQL-backed
    agent execution repositories and writes derived state to Neo4j.

    It is deliberately decoupled from the ingestion service so that
    graph projection failures never block runtime event persistence.
    """

    def __init__(
        self,
        execution_repository: Any,
        event_repository: Any,
        projection_repository: Any,
    ) -> None:
        self._execution_repo = execution_repository
        self._event_repo = event_repository
        self._projection_repo = projection_repository

    # -- Projection entry points ----------------------------------------------

    def project_execution(
        self,
        execution_id: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> RuntimeOntologyProjection:
        """Project a single execution into Neo4j.

        Reads the execution and all its events from PostgreSQL,
        projects them into Neo4j, and returns the projection state.

        Raises:
            ProjectionNotFound: If the execution does not exist.
            Neo4jWriteError: If Neo4j write fails.
        """
        execution = self._execution_repo.get(
            execution_id, organization_id, project_id
        )
        if execution is None:
            raise ProjectionNotFound(execution_id)

        events = self._event_repo.list_by_execution(
            execution_id, organization_id, project_id
        )

        return self._do_project(execution, events)

    def project_execution_batch(
        self,
        organization_id: str,
        execution_ids: list[str],
    ) -> list[RuntimeOntologyProjection]:
        """Project multiple executions in sequence.

        Each execution is projected independently; a failure on one
        does not abort the others. Failed projections are recorded
        with status FAILED and can be retried.
        """
        results: list[RuntimeOntologyProjection] = []
        for exec_id in execution_ids:
            try:
                result = self.project_execution(
                    exec_id, organization_id
                )
                results.append(result)
            except ProjectionNotFound:
                continue
            except Neo4jWriteError:
                # Record as failed so reconciliation can retry.
                now = datetime.now(UTC)
                failed = RuntimeOntologyProjection(
                    execution_id=exec_id,
                    organization_id=organization_id,
                    status=ProjectionStatus.FAILED,
                    updated_at=now,
                )
                self._projection_repo.save_projection(failed)
                results.append(failed)
        return results

    def reconcile_execution(
        self,
        execution_id: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> RuntimeOntologyProjection:
        """Reconcile projection for a single execution.

        If the existing projection is stale (source_version mismatch)
        or failed, rebuild it from scratch. Otherwise return current state.
        """
        existing = self._projection_repo.get_projection(
            execution_id, organization_id, project_id
        )

        execution = self._execution_repo.get(
            execution_id, organization_id, project_id
        )
        if execution is None:
            raise ProjectionNotFound(execution_id)

        # Check if rebuild is needed.
        needs_rebuild = False
        if existing is None or existing.is_stale(execution.version) or existing.status == ProjectionStatus.FAILED:
            needs_rebuild = True

        if not needs_rebuild:
            return existing

        # Delete stale projection and rebuild.
        if existing is not None:
            self._projection_repo.delete_projection(execution_id)

        events = self._event_repo.list_by_execution(
            execution_id, organization_id, project_id
        )
        return self._do_project(execution, events)

    def reconcile_all_pending(
        self,
        organization_id: str,
        limit: int = 100,
    ) -> list[RuntimeOntologyProjection]:
        """Reconcile all pending/failed projections for a tenant."""
        pending = self._projection_repo.list_pending_projections(
            organization_id, limit
        )
        results: list[RuntimeOntologyProjection] = []
        for proj in pending:
            try:
                result = self.reconcile_execution(
                    proj.execution_id, organization_id, proj.project_id
                )
                results.append(result)
            except ProjectionNotFound:
                continue
            except Neo4jWriteError:
                now = datetime.now(UTC)
                failed = RuntimeOntologyProjection(
                    execution_id=proj.execution_id,
                    organization_id=organization_id,
                    project_id=proj.project_id,
                    status=ProjectionStatus.FAILED,
                    updated_at=now,
                )
                self._projection_repo.save_projection(failed)
                results.append(failed)
        return results

    def get_projection_status(
        self,
        execution_id: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Get lightweight projection status."""
        return self._projection_repo.get_projection_status(
            execution_id, organization_id, project_id
        )

    # -- Internal -------------------------------------------------------------

    def _do_project(
        self,
        execution: AgentExecution,
        events: list[AgentExecutionEvent],
    ) -> RuntimeOntologyProjection:
        """Execute the actual Neo4j projection.

        Wraps the repository call in error handling so that Neo4j
        failures are isolated and never propagate to the caller.
        """
        try:
            return self._projection_repo.project_execution(
                execution, events, source_version=execution.version
            )
        except Exception as exc:
            raise Neo4jWriteError(execution.execution_id, exc) from exc
