"""PostgreSQL integration coverage for tool-call execution context."""

from __future__ import annotations

from datetime import UTC, datetime

import psycopg
import pytest

from ai_governance.databases.postgres.database import PostgresDatabase
from ai_governance.domain.agent_execution import (
    ActorType,
    AgentExecutionEvent,
    EventType,
    ToolCallContext,
)
from ai_governance.domain.agent_execution.errors import (
    AgentExecutionRuntimeToolCallConflict,
)
from ai_governance.repositories.postgres.postgres_agent_execution_repository import (
    PostgresAgentExecutionEventRepository,
)

NOW = datetime(2026, 9, 18, tzinfo=UTC)


def _event(
    event_id: str,
    sequence_number: int,
    context: ToolCallContext,
) -> AgentExecutionEvent:
    return AgentExecutionEvent(
        event_id=event_id,
        execution_id="execution-a",
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


def test_postgres_persists_tool_call_context_jsonb_and_execution_uniqueness(
    postgres_database: PostgresDatabase,
) -> None:
    """Exercise JSONB storage and its partial unique index in PostgreSQL."""
    repository = PostgresAgentExecutionEventRepository(postgres_database)
    event = _event(
        "risk-event",
        3,
        ToolCallContext(
            schema_version="1",
            runtime_tool_call_id="call-risk",
            tool_call_group_id="risk-decision",
            depends_on_tool_call_ids=("call-device", "call-profile"),
        ),
    )

    repository.save(event)

    restored = repository.get_by_id(
        event.event_id,
        event.execution_id,
        event.organization_id,
        event.project_id,
    )
    assert restored is not None
    assert restored.tool_call_context == event.tool_call_context

    with postgres_database.connect() as connection:
        row = connection.execute(
            """
            SELECT pg_typeof(depends_on_tool_call_ids_json)::text AS column_type,
                   depends_on_tool_call_ids_json
            FROM agent_execution_event
            WHERE event_id=%(event_id)s
            """,
            {"event_id": event.event_id},
        ).fetchone()

    assert row == {
        "column_type": "jsonb",
        "depends_on_tool_call_ids_json": ["call-device", "call-profile"],
    }

    with pytest.raises(AgentExecutionRuntimeToolCallConflict):
        repository.save(
            _event(
                "duplicate-through-repository",
                4,
                ToolCallContext("1", "call-risk", "risk-decision"),
            )
        )

    # Bypass the repository preflight check to prove PostgreSQL itself enforces
    # the execution-scoped partial unique index under concurrent-writer races.
    with (
        postgres_database.connect() as connection,
        pytest.raises(psycopg.errors.UniqueViolation),
    ):
        connection.execute(
            """
            INSERT INTO agent_execution_event (
                event_id, execution_id, organization_id, project_id,
                event_type, sequence_number, occurred_at, received_at,
                runtime_tool_call_id, created_at
            ) VALUES (
                'duplicate-through-index', 'execution-a', 'org-a', 'project-a',
                'TOOL_CALL', 5, %(occurred_at)s, %(received_at)s,
                'call-risk', %(created_at)s
            )
            """,
            {
                "occurred_at": NOW,
                "received_at": NOW,
                "created_at": NOW,
            },
        )

