"""Focused contracts for provider-neutral tool-call execution context."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.domain.agent_execution import (
    ActorType,
    AgentExecutionEvent,
    EventType,
    ToolCallContext,
)
from ai_governance.domain.agent_execution.errors import (
    AgentExecutionRuntimeToolCallConflict,
)
from ai_governance.repositories.in_memory.in_memory_agent_execution_repository import (
    InMemoryAgentExecutionEventRepository,
)
from ai_governance.repositories.sqlite.sqlite_agent_execution_repository import (
    SQLiteAgentExecutionEventRepository,
)

NOW = datetime(2026, 9, 18, tzinfo=UTC)


def _event(
    event_id: str,
    sequence_number: int,
    context: ToolCallContext | None,
    execution_id: str = "execution-a",
) -> AgentExecutionEvent:
    return AgentExecutionEvent(
        event_id=event_id,
        execution_id=execution_id,
        organization_id="org-a",
        project_id="project-a",
        event_type=EventType.TOOL_CALL,
        sequence_number=sequence_number,
        occurred_at=NOW,
        received_at=NOW,
        correlation_id=None,
        causation_id=None,
        actor_id="risk-tool",
        actor_type=ActorType.TOOL,
        tool_call_context=context,
        evidence_references=(f"artifact://evidence/{event_id}",),
        attributes={"tool": "risk.lookup"},
    )


def test_tool_call_context_validates_its_bounded_immutable_contract() -> None:
    context = ToolCallContext("1", "call-risk", "risk-decision", ("call-a",))

    assert context.depends_on_tool_call_ids == ("call-a",)
    with pytest.raises(ValueError, match="schema version"):
        ToolCallContext("2", "call-risk", "risk-decision")
    with pytest.raises(ValueError, match="not be blank"):
        ToolCallContext("1", " ", "risk-decision")
    with pytest.raises(ValueError, match="unique"):
        ToolCallContext("1", "call-risk", "risk-decision", ("call-a", "call-a"))
    with pytest.raises(ValueError, match="itself"):
        ToolCallContext("1", "call-risk", "risk-decision", ("call-risk",))
    with pytest.raises(ValueError, match="64"):
        ToolCallContext(
            "1",
            "call-risk",
            "risk-decision",
            tuple(f"call-{index}" for index in range(65)),
        )


def test_tool_call_context_is_only_valid_for_tool_calls_and_remains_optional() -> None:
    context = ToolCallContext("1", "call-risk", "risk-decision")
    with pytest.raises(ValueError, match="only for TOOL_CALL"):
        AgentExecutionEvent(
            event_id="model-event",
            execution_id="execution-a",
            organization_id="org-a",
            project_id="project-a",
            event_type=EventType.MODEL_CALL,
            sequence_number=1,
            occurred_at=NOW,
            received_at=NOW,
            correlation_id=None,
            causation_id=None,
            actor_id="model",
            actor_type=ActorType.MODEL,
            tool_call_context=context,
        )

    assert _event("ordinary-tool-event", 1, None).tool_call_context is None

    with pytest.raises(ValueError, match="prohibited key"):
        AgentExecutionEvent(
            event_id="legacy-identity-event",
            execution_id="execution-a",
            organization_id="org-a",
            project_id="project-a",
            event_type=EventType.TOOL_CALL,
            sequence_number=2,
            occurred_at=NOW,
            received_at=NOW,
            correlation_id=None,
            causation_id=None,
            actor_id="risk-tool",
            actor_type=ActorType.TOOL,
            attributes={"metadata": {"external_tool_call_id": "call-risk"}},
        )


def test_parallel_siblings_and_fan_in_persist_without_inferred_dependencies() -> None:
    repository = InMemoryAgentExecutionEventRepository()
    device = _event(
        "device-event",
        10,
        ToolCallContext("1", "call-device", "risk-inputs"),
    )
    profile = _event(
        "profile-event",
        11,
        ToolCallContext("1", "call-profile", "risk-inputs"),
    )
    risk = _event(
        "risk-event",
        12,
        ToolCallContext(
            "1",
            "call-risk",
            "risk-decision",
            ("call-device", "call-profile"),
        ),
    )
    for event in (device, profile, risk):
        repository.save(event)

    recorded = repository.list_by_execution("execution-a", "org-a", "project-a")
    assert [event.sequence_number for event in recorded] == [10, 11, 12]
    assert recorded[1].tool_call_context is not None
    assert recorded[1].tool_call_context.depends_on_tool_call_ids == ()
    assert recorded[2].tool_call_context is not None
    assert recorded[2].tool_call_context.depends_on_tool_call_ids == (
        "call-device",
        "call-profile",
    )


def test_runtime_tool_call_id_is_unique_per_execution_but_not_globally() -> None:
    repository = InMemoryAgentExecutionEventRepository()
    context = ToolCallContext("1", "call-device", "risk-inputs")
    repository.save(_event("event-a", 1, context))

    with pytest.raises(AgentExecutionRuntimeToolCallConflict):
        repository.save(_event("event-b", 2, context))

    repository.save(_event("event-c", 1, context, execution_id="execution-b"))


def test_sqlite_round_trip_preserves_tool_call_context(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "tool-call-context.sqlite")
    database.initialize()
    repository = SQLiteAgentExecutionEventRepository(database)
    event = _event(
        "risk-event",
        12,
        ToolCallContext(
            "1",
            "call-risk",
            "risk-decision",
            ("call-device", "call-profile"),
        ),
    )

    repository.save(event)
    restored = repository.get_by_id("risk-event", "execution-a", "org-a", "project-a")

    assert restored is not None
    assert restored.tool_call_context == event.tool_call_context

    with pytest.raises(AgentExecutionRuntimeToolCallConflict):
        repository.save(
            _event(
                "duplicate-risk-event",
                13,
                ToolCallContext(
                    "1",
                    "call-risk",
                    "risk-decision",
                    ("call-device", "call-profile"),
                ),
            )
        )

