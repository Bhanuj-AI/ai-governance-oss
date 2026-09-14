"""Focused contracts for provider-neutral workflow-step runtime evidence."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.domain.agent_execution import (
    AgentExecutionEvent,
    AgentExecutionStatus,
    EventType,
    WorkflowStep,
    WorkflowStepLifecycle,
)
from ai_governance.domain.agent_execution.agent_execution_event import ActorType
from ai_governance.domain.agent_execution.errors import AgentExecutionInvalidTransition
from ai_governance.repositories.in_memory.in_memory_agent_execution_repository import (
    InMemoryAgentExecutionEventRepository,
    InMemoryAgentExecutionRepository,
)
from ai_governance.repositories.sqlite.sqlite_agent_execution_repository import (
    SQLiteAgentExecutionEventRepository,
)
from ai_governance.services.agent_execution_service import AgentExecutionService
from ai_governance.tenancy.domain import TenantContext

NOW = datetime(2026, 9, 14, tzinfo=UTC)
CONTEXT = TenantContext("org-a", "project-a", "runtime", "request-a")


def _workflow_event(step: WorkflowStep) -> AgentExecutionEvent:
    return AgentExecutionEvent(
        event_id="workflow-event",
        execution_id="execution-a",
        organization_id=CONTEXT.organization_id,
        project_id=CONTEXT.project_id,
        event_type=EventType.WORKFLOW_STEP,
        sequence_number=1,
        occurred_at=NOW,
        received_at=NOW,
        correlation_id="correlation-a",
        causation_id=None,
        actor_id="workflow-runtime",
        actor_type=ActorType.SYSTEM,
        workflow_step=step,
    )


@pytest.mark.parametrize(
    "lifecycle",
    [
        WorkflowStepLifecycle.STARTED,
        WorkflowStepLifecycle.COMPLETED,
        WorkflowStepLifecycle.FAILED,
    ],
)
def test_workflow_step_accepts_every_supported_lifecycle(
    lifecycle: WorkflowStepLifecycle,
) -> None:
    event = _workflow_event(WorkflowStep("step-1", "check_policy", lifecycle))

    assert event.event_type is EventType.WORKFLOW_STEP
    assert event.workflow_step is not None
    assert event.workflow_step.lifecycle is lifecycle


def test_workflow_step_accepts_optional_parent_and_source_kind() -> None:
    step = WorkflowStep(
        "step-child",
        "evaluate_evidence",
        WorkflowStepLifecycle.STARTED,
        parent_step_id="step-parent",
        source_kind="langgraph.node",
    )

    assert step.parent_step_id == "step-parent"
    assert step.source_kind == "langgraph.node"


@pytest.mark.parametrize(
    "step",
    [
        pytest.param(
            lambda: WorkflowStep("step-1", "check_policy", "UNKNOWN"),
            id="invalid-lifecycle",
        ),
        pytest.param(
            lambda: WorkflowStep("", "check_policy", WorkflowStepLifecycle.STARTED),
            id="missing-step-id",
        ),
        pytest.param(
            lambda: WorkflowStep("step-1", "", WorkflowStepLifecycle.STARTED),
            id="missing-step-name",
        ),
        pytest.param(
            lambda: WorkflowStep(
                "step-1",
                "check_policy",
                WorkflowStepLifecycle.STARTED,
                source_kind="LangGraph Node",
            ),
            id="invalid-source-kind",
        ),
    ],
)
def test_workflow_step_rejects_invalid_required_fields(step) -> None:
    with pytest.raises(ValueError):
        step()


def test_workflow_step_cannot_be_carried_by_a_tool_call() -> None:
    with pytest.raises(ValueError, match="valid only for WORKFLOW_STEP"):
        AgentExecutionEvent(
            event_id="tool-event",
            execution_id="execution-a",
            organization_id=CONTEXT.organization_id,
            project_id=CONTEXT.project_id,
            event_type=EventType.TOOL_CALL,
            sequence_number=1,
            occurred_at=NOW,
            received_at=NOW,
            correlation_id=None,
            causation_id=None,
            actor_id="lookup",
            actor_type=ActorType.TOOL,
            workflow_step=WorkflowStep(
                "step-1", "check_policy", WorkflowStepLifecycle.STARTED
            ),
        )


def _service() -> tuple[AgentExecutionService, InMemoryAgentExecutionEventRepository]:
    events = InMemoryAgentExecutionEventRepository()
    return AgentExecutionService(InMemoryAgentExecutionRepository(), events), events


def _start_execution(service: AgentExecutionService, external_id: str = "run-a") -> str:
    return service.ingest_start(
        agent_id="claims-agent",
        agent_name="Claims Agent",
        agent_version="1.0",
        external_execution_id=external_id,
        runtime_provider="langgraph",
        context=CONTEXT,
    ).execution_id


def test_workflow_step_lifecycle_is_ordered_and_tool_calls_remain_independent() -> None:
    service, events = _service()
    execution_id = _start_execution(service)
    parent = WorkflowStep(
        "load-claim",
        "load_claim",
        WorkflowStepLifecycle.STARTED,
        source_kind="langgraph.node",
    )
    child = WorkflowStep(
        "check-policy",
        "check_policy",
        WorkflowStepLifecycle.STARTED,
        parent_step_id="load-claim",
        source_kind="langgraph.node",
    )

    service.ingest_event(
        execution_id=execution_id,
        event_type=EventType.WORKFLOW_STEP,
        workflow_step=parent,
        attributes={},
        context=CONTEXT,
    )
    service.ingest_event(
        execution_id=execution_id,
        event_type=EventType.WORKFLOW_STEP,
        workflow_step=child,
        attributes={},
        context=CONTEXT,
    )
    service.ingest_event(
        execution_id=execution_id,
        event_type=EventType.TOOL_CALL,
        attributes={"tool": "policy-api"},
        context=CONTEXT,
    )
    service.ingest_event(
        execution_id=execution_id,
        event_type=EventType.WORKFLOW_STEP,
        workflow_step=WorkflowStep(
            "check-policy",
            "check_policy",
            WorkflowStepLifecycle.COMPLETED,
            parent_step_id="load-claim",
            source_kind="langgraph.node",
        ),
        attributes={},
        context=CONTEXT,
    )
    service.ingest_event(
        execution_id=execution_id,
        event_type=EventType.WORKFLOW_STEP,
        workflow_step=WorkflowStep(
            "load-claim",
            "load_claim",
            WorkflowStepLifecycle.COMPLETED,
            source_kind="langgraph.node",
        ),
        attributes={},
        context=CONTEXT,
    )

    recorded = events.list_by_execution(
        execution_id, CONTEXT.organization_id, CONTEXT.project_id
    )
    assert [event.sequence_number for event in recorded] == [0, 1, 2, 3, 4, 5]
    assert [event.event_type for event in recorded[1:]] == [
        EventType.WORKFLOW_STEP,
        EventType.WORKFLOW_STEP,
        EventType.TOOL_CALL,
        EventType.WORKFLOW_STEP,
        EventType.WORKFLOW_STEP,
    ]
    assert recorded[1].workflow_step is not None
    assert recorded[1].workflow_step.step_id == recorded[5].workflow_step.step_id


def test_workflow_step_requires_started_parent_in_the_same_execution() -> None:
    service, _ = _service()
    execution_id = _start_execution(service)

    with pytest.raises(AgentExecutionInvalidTransition, match="parent_step_id"):
        service.ingest_event(
            execution_id=execution_id,
            event_type=EventType.WORKFLOW_STEP,
            workflow_step=WorkflowStep(
                "child",
                "child",
                WorkflowStepLifecycle.STARTED,
                parent_step_id="missing-parent",
            ),
            attributes={},
            context=CONTEXT,
        )

    with pytest.raises(AgentExecutionInvalidTransition, match="must start"):
        service.ingest_event(
            execution_id=execution_id,
            event_type=EventType.WORKFLOW_STEP,
            workflow_step=WorkflowStep(
                "orphan", "orphan", WorkflowStepLifecycle.COMPLETED
            ),
            attributes={},
            context=CONTEXT,
        )


def test_deterministic_langgraph_shape_records_four_steps_without_tool_calls() -> None:
    """The guide's code-only graph emits no fabricated tool invocations."""
    service, events = _service()
    execution_id = _start_execution(service, external_id="langgraph-deterministic")
    node_names = (
        "load_claim",
        "check_policy",
        "evaluate_evidence",
        "make_decision",
    )

    for node_name in node_names:
        step_id = f"{execution_id}:node:{node_name}"
        for lifecycle in (
            WorkflowStepLifecycle.STARTED,
            WorkflowStepLifecycle.COMPLETED,
        ):
            service.ingest_event(
                execution_id=execution_id,
                event_type=EventType.WORKFLOW_STEP,
                workflow_step=WorkflowStep(
                    step_id,
                    node_name,
                    lifecycle,
                    source_kind="langgraph.node",
                ),
                attributes={},
                context=CONTEXT,
                idempotency_key=f"{step_id}:{lifecycle.value}",
            )
    completed = service.mark_completed(
        execution_id, AgentExecutionStatus.SUCCEEDED, CONTEXT
    )

    recorded = events.list_by_execution(
        execution_id, CONTEXT.organization_id, CONTEXT.project_id
    )
    workflow_events = [
        event for event in recorded if event.event_type is EventType.WORKFLOW_STEP
    ]
    assert completed.status is AgentExecutionStatus.SUCCEEDED
    assert [event.event_type for event in recorded] == [
        EventType.EXECUTION_STARTED,
        *([EventType.WORKFLOW_STEP] * 8),
        EventType.EXECUTION_COMPLETED,
    ]
    assert not [event for event in recorded if event.event_type is EventType.TOOL_CALL]
    assert [event.workflow_step.step_name for event in workflow_events] == [
        "load_claim",
        "load_claim",
        "check_policy",
        "check_policy",
        "evaluate_evidence",
        "evaluate_evidence",
        "make_decision",
        "make_decision",
    ]
    assert all(
        workflow_events[index].workflow_step.step_id
        == workflow_events[index + 1].workflow_step.step_id
        for index in range(0, len(workflow_events), 2)
    )


def test_sqlite_round_trip_preserves_typed_workflow_step(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "workflow-step.sqlite")
    database.initialize()
    repository = SQLiteAgentExecutionEventRepository(database)
    event = _workflow_event(
        WorkflowStep(
            "step-1",
            "check_policy",
            WorkflowStepLifecycle.FAILED,
            parent_step_id="step-parent",
            source_kind="langgraph.node",
        )
    )

    repository.save(event, idempotency_key="workflow-step-1")
    restored = repository.get_by_id(
        event.event_id,
        event.execution_id,
        event.organization_id,
        event.project_id,
    )

    assert restored is not None
    assert restored.event_type is EventType.WORKFLOW_STEP
    assert restored.workflow_step == event.workflow_step
