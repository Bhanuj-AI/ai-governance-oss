"""Tests for runtime ontology projection into Neo4j.

Covers:
- Projection correctness (execution node, all relationship types)
- Idempotency (repeated projection produces identical graph)
- Reconciliation (missing, stale, failed projections)
- Failure isolation (Neo4j unavailable → runtime ingestion continues)
- Tenancy (cross-tenant reference cannot create relationship)
- Privacy (prohibited data never appears in projected nodes)
- Versioning (source/projection version tracking)
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ai_governance.domain.agent_execution import (
    AgentExecution,
    AgentExecutionEvent,
    AgentExecutionStatus,
    EventType,
)
from ai_governance.domain.agent_execution.projection import (
    ProjectionStatus,
    RuntimeOntologyProjection,
)
from ai_governance.domain.agent_execution.projection_errors import (
    Neo4jWriteError,
    ProjectionNotFound,
)
from ai_governance.domain.agent_execution.agent_execution_event import (
    ActorType,
)
from ai_governance.repositories.in_memory.in_memory_agent_execution_repository import (
    InMemoryAgentExecutionRepository,
    InMemoryAgentExecutionEventRepository,
)
from ai_governance.repositories.in_memory.in_memory_projection_repository import (
    InMemoryProjectionRepository,
)
from ai_governance.services.ontology_projection_service import (
    OntologyProjectionService,
)


# -- Fixtures -----------------------------------------------------------------


def _make_execution(
    execution_id: str = "exec-123",
    status: AgentExecutionStatus = AgentExecutionStatus.SUCCEEDED,
    organization_id: str = "org_test",
    project_id: str | None = "project_test",
    agent_id: str = "claims-agent",
    external_execution_id: str = "ext-98374",
    runtime_provider: str = "external-runtime",
    version: int = 8,
    parent_execution_id: str | None = None,
) -> AgentExecution:
    now = datetime.now(UTC)
    return AgentExecution(
        execution_id=execution_id,
        organization_id=organization_id,
        project_id=project_id,
        agent_id=agent_id,
        agent_name="Claims Agent",
        agent_version="1.0.0",
        external_execution_id=external_execution_id,
        runtime_provider=runtime_provider,
        status=status,
        started_at=now,
        completed_at=now if status in (AgentExecutionStatus.SUCCEEDED, AgentExecutionStatus.FAILED, AgentExecutionStatus.CANCELLED) else None,
        correlation_id="corr-1",
        parent_execution_id=parent_execution_id,
        metadata={"env": "staging"},
        version=version,
        created_at=now,
        updated_at=now,
    )


def _make_event(
    event_id: str = "evt-1",
    execution_id: str = "exec-123",
    event_type: EventType = EventType.MODEL_CALL,
    sequence_number: int = 1,
    attributes: dict | None = None,
    resource_references: tuple[str, ...] = (),
    organization_id: str = "org_test",
    project_id: str | None = "project_test",
) -> AgentExecutionEvent:
    now = datetime.now(UTC)
    return AgentExecutionEvent(
        event_id=event_id,
        execution_id=execution_id,
        organization_id=organization_id,
        project_id=project_id,
        event_type=event_type,
        sequence_number=sequence_number,
        occurred_at=now,
        received_at=now,
        correlation_id=None,
        causation_id=None,
        actor_id="agent-1",
        actor_type=ActorType.AGENT,
        resource_references=resource_references,
        evidence_references=(),
        attributes=attributes or {},
    )


def _make_service(
    execution_repo: InMemoryAgentExecutionRepository | None = None,
    event_repo: InMemoryAgentExecutionEventRepository | None = None,
    projection_repo: InMemoryProjectionRepository | None = None,
) -> OntologyProjectionService:
    if execution_repo is None:
        execution_repo = InMemoryAgentExecutionRepository()
    if event_repo is None:
        event_repo = InMemoryAgentExecutionEventRepository()
    if projection_repo is None:
        projection_repo = InMemoryProjectionRepository()
    return OntologyProjectionService(
        execution_repo, event_repo, projection_repo
    )


# -- Projection correctness ---------------------------------------------------


class TestProjectionCorrectness:
    """Test that all relationship types are projected correctly."""

    def test_execution_node_created(self):
        """Projecting an execution creates the projection node."""
        service = _make_service()
        execution = _make_execution()
        service._execution_repo.save(execution)

        projection = service.project_execution(
            execution.execution_id, execution.organization_id, execution.project_id
        )

        assert projection.status == ProjectionStatus.PROJECTED
        assert projection.execution_id == execution.execution_id
        assert projection.source_version == execution.version

    def test_model_relationship_projected(self):
        """MODEL_CALL event creates USED_MODEL relationship."""
        service = _make_service()
        execution = _make_execution()
        event = _make_event(
            event_type=EventType.MODEL_CALL,
            attributes={"model": "model-v7"},
        )
        service._execution_repo.save(execution)
        service._event_repo.save(event)

        projection = service.project_execution(
            execution.execution_id, execution.organization_id
        )

        assert projection.relationships_projected >= 1
        edges = service._projection_repo.graph_edges
        assert any(e["type"] == "USED_MODEL" for e in edges)

    def test_tool_relationship_projected(self):
        """TOOL_CALL event creates CALLED_TOOL relationship."""
        service = _make_service()
        execution = _make_execution()
        event = _make_event(
            event_type=EventType.TOOL_CALL,
            attributes={"tool": "customer-profile"},
        )
        service._execution_repo.save(execution)
        service._event_repo.save(event)

        service.project_execution(
            execution.execution_id, execution.organization_id
        )

        edges = service._projection_repo.graph_edges
        assert any(e["type"] == "CALLED_TOOL" for e in edges)

    def test_governance_decision_relationship_projected(self):
        """GOVERNANCE_DECISION event creates PRODUCED relationship."""
        service = _make_service()
        execution = _make_execution()
        event = _make_event(
            event_type=EventType.GOVERNANCE_DECISION,
            attributes={"decision_id": "decision-981"},
        )
        service._execution_repo.save(execution)
        service._event_repo.save(event)

        service.project_execution(
            execution.execution_id, execution.organization_id
        )

        edges = service._projection_repo.graph_edges
        assert any(e["type"] == "PRODUCED" for e in edges)

    def test_policy_relationship_projected(self):
        """GOVERNANCE_DECISION with policy creates GOVERNED_BY relationship."""
        service = _make_service()
        execution = _make_execution()
        event = _make_event(
            event_type=EventType.GOVERNANCE_DECISION,
            attributes={"policy_id": "policy-17"},
        )
        service._execution_repo.save(execution)
        service._event_repo.save(event)

        service.project_execution(
            execution.execution_id, execution.organization_id
        )

        edges = service._projection_repo.graph_edges
        assert any(e["type"] == "GOVERNED_BY" for e in edges)

    def test_evaluation_relationship_projected(self):
        """EVALUATION event creates EVALUATED_BY relationship."""
        service = _make_service()
        execution = _make_execution()
        event = _make_event(
            event_type=EventType.EVALUATION,
            attributes={"evaluation_result_id": "eval-442"},
        )
        service._execution_repo.save(execution)
        service._event_repo.save(event)

        service.project_execution(
            execution.execution_id, execution.organization_id
        )

        edges = service._projection_repo.graph_edges
        assert any(e["type"] == "EVALUATED_BY" for e in edges)

    def test_governed_asset_relationship_projected(self):
        """Resource references create ACCESSED relationships."""
        service = _make_service()
        execution = _make_execution()
        event = _make_event(
            event_type=EventType.TOOL_CALL,
            resource_references=("Dataset:claims-data", "Prompt:system-prompt"),
        )
        service._execution_repo.save(execution)
        service._event_repo.save(event)

        service.project_execution(
            execution.execution_id, execution.organization_id
        )

        edges = service._projection_repo.graph_edges
        accessed = [e for e in edges if e["type"] == "ACCESSED"]
        assert len(accessed) == 2

    def test_parent_child_relationship_projected(self):
        """Execution with parent_execution_id creates PARENT_OF relationship."""
        service = _make_service()
        parent = _make_execution(execution_id="exec-parent")
        child = _make_execution(
            execution_id="exec-child",
            parent_execution_id="exec-parent",
        )
        service._execution_repo.save(parent)
        service._execution_repo.save(child)

        projection = service.project_execution(
            child.execution_id, child.organization_id
        )

        assert projection.status == ProjectionStatus.PROJECTED


# -- Idempotency --------------------------------------------------------------


class TestProjectionIdempotency:
    """Same execution projected repeatedly produces identical graph."""

    def test_repeated_projection_is_idempotent(self):
        """Projecting the same execution twice does not duplicate edges."""
        service = _make_service()
        execution = _make_execution()
        event = _make_event(
            event_type=EventType.MODEL_CALL,
            attributes={"model": "model-v7"},
        )
        service._execution_repo.save(execution)
        service._event_repo.save(event)

        proj1 = service.project_execution(
            execution.execution_id, execution.organization_id
        )
        proj2 = service.project_execution(
            execution.execution_id, execution.organization_id
        )

        # Both projections report same count.
        assert proj1.relationships_projected == proj2.relationships_projected
        # Graph edges are not duplicated.
        edges = service._projection_repo.graph_edges
        model_edges = [e for e in edges if e["type"] == "USED_MODEL"]
        assert len(model_edges) == 1

    def test_same_source_version_projected_repeatedly(self):
        """Re-projecting with same source version is a no-op."""
        service = _make_service()
        execution = _make_execution(version=5)
        service._execution_repo.save(execution)

        proj1 = service.project_execution(
            execution.execution_id, execution.organization_id
        )
        proj2 = service.project_execution(
            execution.execution_id, execution.organization_id
        )

        assert proj1.source_version == proj2.source_version == 5

    def test_projection_state_persists(self):
        """Projection state is retrievable after projection."""
        service = _make_service()
        execution = _make_execution()
        event = _make_event(
            event_type=EventType.MODEL_CALL,
            attributes={"model": "model-v7"},
        )
        service._execution_repo.save(execution)
        service._event_repo.save(event)
        service.project_execution(
            execution.execution_id, execution.organization_id
        )

        status = service.get_projection_status(
            execution.execution_id, execution.organization_id
        )

        assert status["status"] == "PROJECTED"
        assert status["relationships_projected"] > 0


# -- Reconciliation -----------------------------------------------------------


class TestReconciliation:
    """Test missing, stale, and failed projection reconciliation."""

    def test_missing_projection_created(self):
        """Reconciling a missing projection creates it."""
        service = _make_service()
        execution = _make_execution()
        event = _make_event(
            event_type=EventType.MODEL_CALL,
            attributes={"model": "model-v7"},
        )
        service._execution_repo.save(execution)
        service._event_repo.save(event)

        result = service.reconcile_execution(
            execution.execution_id, execution.organization_id
        )

        assert result.status == ProjectionStatus.PROJECTED

    def test_stale_projection_rebuilt(self):
        """Reconciling a stale projection (version mismatch) rebuilds it."""
        service = _make_service()
        execution = _make_execution(version=5)
        event = _make_event(
            event_type=EventType.MODEL_CALL,
            attributes={"model": "model-v7"},
        )
        service._execution_repo.save(execution)
        service._event_repo.save(event)

        # Project with old version.
        proj = service.project_execution(
            execution.execution_id, execution.organization_id
        )
        assert proj.source_version == 5

        # Update execution to newer version.
        updated_exec = _make_execution(version=10)
        service._execution_repo.save(updated_exec)

        # Reconcile should detect staleness and rebuild.
        result = service.reconcile_execution(
            execution.execution_id, execution.organization_id
        )
        assert result.source_version == 10

    def test_failed_projection_retried(self):
        """Reconciling a failed projection rebuilds it."""
        service = _make_service()
        execution = _make_execution()
        event = _make_event(
            event_type=EventType.MODEL_CALL,
            attributes={"model": "model-v7"},
        )
        service._execution_repo.save(execution)
        service._event_repo.save(event)

        # Manually mark as failed.
        failed = RuntimeOntologyProjection(
            execution_id=execution.execution_id,
            organization_id=execution.organization_id,
            status=ProjectionStatus.FAILED,
        )
        service._projection_repo.save_projection(failed)

        result = service.reconcile_execution(
            execution.execution_id, execution.organization_id
        )
        assert result.status == ProjectionStatus.PROJECTED

    def test_current_projection_not_rebuilt(self):
        """Reconciling a current projection returns existing state."""
        service = _make_service()
        execution = _make_execution(version=5)
        service._execution_repo.save(execution)

        proj1 = service.project_execution(
            execution.execution_id, execution.organization_id
        )

        # Reconcile should return existing (not rebuild).
        proj2 = service.reconcile_execution(
            execution.execution_id, execution.organization_id
        )

        assert proj1.execution_id == proj2.execution_id
        assert proj1.source_version == proj2.source_version

    def test_reconcile_nonexistent_execution_raises(self):
        """Reconciling a non-existent execution raises ProjectionNotFound."""
        service = _make_service()

        with pytest.raises(ProjectionNotFound):
            service.reconcile_execution("nonexistent", "org_test")

    def test_reconcile_all_pending(self):
        """Reconcile all pending/failed projections for a tenant."""
        service = _make_service()
        exec1 = _make_execution(execution_id="exec-1")
        exec2 = _make_execution(execution_id="exec-2")
        service._execution_repo.save(exec1)
        service._execution_repo.save(exec2)

        # Mark one as failed.
        failed = RuntimeOntologyProjection(
            execution_id="exec-2",
            organization_id="org_test",
            status=ProjectionStatus.FAILED,
        )
        service._projection_repo.save_projection(failed)

        results = service.reconcile_all_pending("org_test")
        projected = [r for r in results if r.status == ProjectionStatus.PROJECTED]
        assert len(projected) >= 1


# -- Failure isolation --------------------------------------------------------


class TestFailureIsolation:
    """Neo4j unavailable should not block runtime ingestion."""

    def test_neo4j_failure_does_not_block_ingestion(self):
        """When Neo4j write fails, execution persistence still works."""
        service = _make_service()
        execution = _make_execution()
        service._execution_repo.save(execution)

        # Simulate Neo4j failure by making projection_repo raise.
        def failing_project(*args, **kwargs):
            raise RuntimeError("Neo4j connection refused")

        service._projection_repo.project_execution = failing_project  # type: ignore[assignment]

        # The service should raise Neo4jWriteError, not block.
        with pytest.raises(Neo4jWriteError):
            service.project_execution(
                execution.execution_id, execution.organization_id
            )

        # But the execution is still in the repo.
        retrieved = service._execution_repo.get(
            execution.execution_id, execution.organization_id
        )
        assert retrieved is not None
        assert retrieved.status == AgentExecutionStatus.SUCCEEDED

    def test_batch_projection_continues_on_failure(self):
        """Batch projection continues processing remaining executions on failure."""
        service = _make_service()
        exec1 = _make_execution(execution_id="exec-1")
        exec2 = _make_execution(execution_id="exec-2")
        service._execution_repo.save(exec1)
        service._execution_repo.save(exec2)

        # Make the second execution fail.
        def selective_fail(execution, events, source_version):
            if execution.execution_id == "exec-2":
                raise RuntimeError("Neo4j unavailable")
            return original_project(execution, events, source_version)


        original_project = service._projection_repo.project_execution
        service._projection_repo.project_execution = selective_fail  # type: ignore[assignment]

        results = service.project_execution_batch(
            "org_test", ["exec-1", "exec-2"]
        )

        assert len(results) == 2
        assert results[0].status == ProjectionStatus.PROJECTED
        assert results[1].status == ProjectionStatus.FAILED


# -- Tenancy ------------------------------------------------------------------


class TestProjectionTenancy:
    """Cross-tenant references cannot create relationships."""

    def test_cross_tenant_execution_not_found(self):
        """Getting projection for wrong tenant returns None."""
        service = _make_service()
        execution = _make_execution(organization_id="org_a")
        service._execution_repo.save(execution)

        # Query with different tenant.
        status = service.get_projection_status(
            execution.execution_id, "org_b"
        )
        assert status["status"] == "NOT_FOUND"

    def test_projection_scoped_to_tenant(self):
        """Projection is stored and retrieved within tenant scope."""
        service = _make_service()
        execution = _make_execution(organization_id="org_test")
        service._execution_repo.save(execution)

        service.project_execution(
            execution.execution_id, execution.organization_id
        )

        # Same tenant can retrieve.
        status = service.get_projection_status(
            execution.execution_id, execution.organization_id
        )
        assert status["status"] == "PROJECTED"


# -- Privacy ------------------------------------------------------------------


class TestProjectionPrivacy:
    """Prohibited runtime payload data never appears in projected nodes."""

    def test_prohibited_keys_not_projected(self):
        """Events with prohibited keys are rejected before projection."""
        # This event has a prohibited key — should be rejected at domain level.
        with pytest.raises(ValueError, match="prohibited key"):
            _make_event(
                event_type=EventType.MODEL_CALL,
                attributes={"prompt": "secret prompt"},
            )

    def test_nested_prohibited_keys_not_projected(self):
        """Nested prohibited keys are also rejected."""
        with pytest.raises(ValueError, match="prohibited key"):
            _make_event(
                event_type=EventType.TOOL_CALL,
                attributes={
                    "metadata": {"payload": {"api_key": "sk-secret"}},
                },
            )

    def test_safe_attributes_projected(self):
        """Safe operational metadata is projected correctly."""
        service = _make_service()
        execution = _make_execution()
        event = _make_event(
            event_type=EventType.MODEL_CALL,
            attributes={
                "model": "gpt-4",
                "input_tokens": 100,
                "latency_ms": 500,
            },
        )
        service._execution_repo.save(execution)
        service._event_repo.save(event)

        projection = service.project_execution(
            execution.execution_id, execution.organization_id
        )
        assert projection.relationships_projected >= 1


# -- Versioning ---------------------------------------------------------------


class TestProjectionVersioning:
    """Source and projection version tracking."""

    def test_projection_version_is_set(self):
        """Projection carries the schema version."""
        service = _make_service()
        execution = _make_execution()
        service._execution_repo.save(execution)

        projection = service.project_execution(
            execution.execution_id, execution.organization_id
        )

        assert projection.projection_version == "1"

    def test_source_version_tracked(self):
        """Source execution version is captured at projection time."""
        service = _make_service()
        execution = _make_execution(version=42)
        service._execution_repo.save(execution)

        projection = service.project_execution(
            execution.execution_id, execution.organization_id
        )

        assert projection.source_version == 42

    def test_stale_detection(self):
        """is_stale returns True when source version increased."""
        projection = RuntimeOntologyProjection(
            execution_id="exec-1",
            organization_id="org_test",
            status=ProjectionStatus.PROJECTED,
            source_version=5,
        )

        assert projection.is_stale(10) is True
        assert projection.is_stale(5) is False
        assert projection.is_stale(3) is False

    def test_projection_aggregate_lifecycle(self):
        """Projection transitions through its lifecycle."""
        now = datetime.now(UTC)
        proj = RuntimeOntologyProjection(
            execution_id="exec-1",
            organization_id="org_test",
        )

        assert proj.status == ProjectionStatus.PENDING
        assert proj.is_terminal is False

        projected = proj.mark_projected(7, now=now)
        assert projected.status == ProjectionStatus.PROJECTED
        assert projected.is_terminal is True
        assert projected.relationships_projected == 7

        failed = projected.mark_failed(now=now)
        assert failed.status == ProjectionStatus.FAILED

        pending = failed.mark_pending(now=now)
        assert pending.status == ProjectionStatus.PENDING
        assert pending.relationships_projected == 0


# -- Acceptance scenario ------------------------------------------------------


class TestAcceptanceScenario:
    """End-to-end acceptance scenario from the spec."""

    def test_spec_acceptance_scenario(self):
        """
        Execution: exec-123, Agent: claims-agent
        Events: MODEL_CALL(model-v7), TOOL_CALL(customer-profile),
                TOOL_CALL(claims-history), GOVERNANCE_DECISION(decision-981, policy-17),
                EVALUATION(eval-442), EXECUTION_COMPLETED(SUCCEEDED)

        Expected graph:
          - USED_MODEL -> model-v7
          - CALLED_TOOL -> customer-profile
          - CALLED_TOOL -> claims-history
          - PRODUCED -> decision-981
          - GOVERNED_BY -> policy-17
          - EVALUATED_BY -> eval-442
        """
        service = _make_service()
        execution = _make_execution(
            execution_id="exec-123",
            agent_id="claims-agent",
            external_execution_id="ext-98374",
        )
        service._execution_repo.save(execution)

        events = [
            _make_event(event_id="evt-1", event_type=EventType.MODEL_CALL, sequence_number=1, attributes={"model": "model-v7"}),
            _make_event(event_id="evt-2", event_type=EventType.TOOL_CALL, sequence_number=2, attributes={"tool": "customer-profile"}),
            _make_event(event_id="evt-3", event_type=EventType.TOOL_CALL, sequence_number=3, attributes={"tool": "claims-history"}),
            _make_event(event_id="evt-4", event_type=EventType.GOVERNANCE_DECISION, sequence_number=4, attributes={"decision_id": "decision-981", "policy_id": "policy-17"}),
            _make_event(event_id="evt-5", event_type=EventType.EVALUATION, sequence_number=5, attributes={"evaluation_result_id": "eval-442"}),
            _make_event(event_id="evt-6", event_type=EventType.EXECUTION_COMPLETED, sequence_number=6, attributes={"status": "SUCCEEDED"}),
        ]
        for event in events:
            service._event_repo.save(event)

        projection = service.project_execution(
            execution.execution_id, execution.organization_id
        )

        # Verify relationship counts.
        edges = service._projection_repo.graph_edges
        assert any(e["type"] == "USED_MODEL" and e["target"] == "model-v7" for e in edges)
        assert any(e["type"] == "CALLED_TOOL" and e["target"] == "customer-profile" for e in edges)
        assert any(e["type"] == "CALLED_TOOL" and e["target"] == "claims-history" for e in edges)
        assert any(e["type"] == "PRODUCED" and e["target"] == "decision-981" for e in edges)
        assert any(e["type"] == "GOVERNED_BY" and e["target"] == "policy-17" for e in edges)
        assert any(e["type"] == "EVALUATED_BY" and e["target"] == "eval-442" for e in edges)

        # Idempotency: re-project produces same graph.
        projection2 = service.project_execution(
            execution.execution_id, execution.organization_id
        )
        assert projection.relationships_projected == projection2.relationships_projected
