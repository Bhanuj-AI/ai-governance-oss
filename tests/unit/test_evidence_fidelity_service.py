from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.domain.agent_execution import (
    ActorType,
    AgentExecution,
    AgentExecutionEvent,
    AgentExecutionStatus,
    EventType,
)
from ai_governance.domain.evidence_fidelity import EvidenceFidelityStatus
from ai_governance.repositories.in_memory.in_memory_agent_execution_repository import (
    InMemoryAgentExecutionEventRepository,
    InMemoryAgentExecutionRepository,
)
from ai_governance.repositories.in_memory.in_memory_evidence_fidelity_repository import (
    InMemoryEvidenceFidelityComparisonRepository,
)
from ai_governance.repositories.sqlite.sqlite_agent_execution_repository import (
    SQLiteAgentExecutionEventRepository,
    SQLiteAgentExecutionRepository,
)
from ai_governance.repositories.sqlite.sqlite_evidence_fidelity_repository import (
    SQLiteEvidenceFidelityComparisonRepository,
)
from ai_governance.services.evidence_fidelity_service import EvidenceFidelityService
from ai_governance.tenancy.domain import TenantContext


def _context(project_id: str = "project-a") -> TenantContext:
    return TenantContext("org-a", project_id, "tester", "request-1")


def _service(*, broken_order: bool = False):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    executions = InMemoryAgentExecutionRepository()
    events = InMemoryAgentExecutionEventRepository()
    execution = AgentExecution(
        execution_id="execution-1", organization_id="org-a", project_id="project-a",
        agent_id="inspect-ai", agent_name="Inspect sample", agent_version="1",
        external_execution_id="run-1:sample:1", runtime_provider="inspect_ai",
        status=AgentExecutionStatus.SUCCEEDED, started_at=now,
        completed_at=now + timedelta(seconds=2), correlation_id=None,
        parent_execution_id=None, created_at=now, updated_at=now + timedelta(seconds=2),
        metadata={"sample_id": "1", "runner_provenance": {"model": "test-model", "solver": "controlled"}},
    )
    executions.save(execution)
    definitions = (
        (EventType.EXECUTION_STARTED, {"runner": "inspect_ai"}, (), ActorType.AGENT),
        (EventType.TOOL_CALL, {"tool": "lookup", "arguments_digest": "a" * 64}, ("artifact://lookup/1",), ActorType.TOOL),
        (EventType.ERROR, {"error_class": "tool_timeout", "timeout": True}, (), ActorType.TOOL),
        (EventType.TOOL_CALL, {"tool": "lookup", "retry_of": "event-3", "recovery_of": "event-3", "arguments_digest": "b" * 64}, ("artifact://lookup/2",), ActorType.TOOL),
        (EventType.MODEL_CALL, {"model": "test-model", "input_tokens": 4, "output_tokens": 2, "total_tokens": 6, "score": 1.0}, (), ActorType.MODEL),
        (EventType.EXECUTION_COMPLETED, {"final_status": "SUCCEEDED", "duration_seconds": 2.0}, (), ActorType.SYSTEM),
    )
    for index, (event_type, attributes, evidence_references, actor_type) in enumerate(definitions):
        sequence = index if not (broken_order and index == 3) else 7
        events.save(AgentExecutionEvent(
            event_id=f"event-{index + 1}", execution_id=execution.execution_id,
            organization_id="org-a", project_id="project-a", event_type=event_type,
            sequence_number=sequence, occurred_at=now + timedelta(milliseconds=index),
            received_at=now + timedelta(milliseconds=index), correlation_id=None,
            causation_id="event-3" if index == 3 else None, actor_id="inspect-ai",
            actor_type=actor_type, resource_references=(), evidence_references=evidence_references,
            attributes=attributes,
        ))
    comparisons = InMemoryEvidenceFidelityComparisonRepository()
    return EvidenceFidelityService(comparisons, executions, events), comparisons


def test_compares_authoritative_event_trajectory_to_actual_graph_projection() -> None:
    service, _ = _service()

    result = service.request("execution-1", _context())

    assert result.status is EvidenceFidelityStatus.SUCCEEDED
    assert result.trajectory is not None
    assert result.runtime_projection is not None
    assert result.trajectory.projection_type == "full_observable_trajectory"
    assert result.runtime_projection.projection_type == "runtime_ontology_projection"
    assert result.trajectory.event_count == 6
    assert result.ordering_preserved is False
    assert result.token_usage_preserved is False
    assert result.recovery_sequence_preserved is False
    assert result.causal_evidence_complete is False
    assert "evidence_before_action" in result.unsupported_conclusions


def test_request_is_idempotent_and_tenant_scoped() -> None:
    service, _ = _service()

    first = service.request("execution-1", _context())
    second = service.request("execution-1", _context())

    assert first.comparison_id == second.comparison_id
    assert service.list_for_execution("execution-1", _context("project-b")) == []


def test_incomplete_order_is_persisted_as_a_fail_closed_result() -> None:
    service, _ = _service(broken_order=True)

    result = service.request("execution-1", _context())

    assert result.status is EvidenceFidelityStatus.FAILED
    assert result.failure_code == "EVENT_ORDER_UNAVAILABLE"
    assert result.unsupported_conclusions == ("ALL_CONCLUSIONS_INSUFFICIENT_EVIDENCE",)


def test_source_digest_mismatch_is_explicit_and_no_private_text_is_stored() -> None:
    service, _ = _service()

    result = service.request("execution-1", _context(), expected_source_digest="0" * 64)
    recovered = service.request("execution-1", _context())

    assert result.status is EvidenceFidelityStatus.FAILED
    assert result.failure_code == "SOURCE_DIGEST_MISMATCH"
    assert recovered.status is EvidenceFidelityStatus.SUCCEEDED
    assert recovered.comparison_id != result.comparison_id
    serialized = repr(result)
    assert "chain_of_thought" not in serialized
    assert "prompt" not in serialized


def test_comparison_is_immutable() -> None:
    service, repository = _service()
    result = service.request("execution-1", _context())

    with pytest.raises(ValueError, match="immutable"):
        repository.save(result.__class__(**{**result.__dict__, "failure_reason": "changed"}))


def test_sqlite_comparison_survives_service_restart(tmp_path) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    database = SQLiteDatabase(tmp_path / "evidence-fidelity.sqlite")
    database.initialize()
    executions = SQLiteAgentExecutionRepository(database)
    events = SQLiteAgentExecutionEventRepository(database)
    executions.save(AgentExecution(
        execution_id="sqlite-execution", organization_id="org-a", project_id="project-a",
        agent_id="agent", agent_name="Agent", agent_version="1", external_execution_id="external",
        runtime_provider="inspect_ai", status=AgentExecutionStatus.SUCCEEDED,
        started_at=now, completed_at=now + timedelta(seconds=1), correlation_id=None,
        parent_execution_id=None, created_at=now, updated_at=now + timedelta(seconds=1),
    ))
    for sequence, event_type in enumerate((EventType.EXECUTION_STARTED, EventType.EXECUTION_COMPLETED)):
        events.save(AgentExecutionEvent(
            event_id=f"sqlite-event-{sequence}", execution_id="sqlite-execution",
            organization_id="org-a", project_id="project-a", event_type=event_type,
            sequence_number=sequence, occurred_at=now + timedelta(milliseconds=sequence),
            received_at=now + timedelta(milliseconds=sequence), correlation_id=None,
            causation_id=None, actor_id="agent", actor_type=ActorType.AGENT,
            attributes={"final_status": "SUCCEEDED"} if sequence else {},
        ))
    first = EvidenceFidelityService(
        SQLiteEvidenceFidelityComparisonRepository(database), executions, events
    ).request("sqlite-execution", _context())
    restarted = EvidenceFidelityService(
        SQLiteEvidenceFidelityComparisonRepository(database),
        SQLiteAgentExecutionRepository(database),
        SQLiteAgentExecutionEventRepository(database),
    )

    assert restarted.get(first.comparison_id, _context()) == first
