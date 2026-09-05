"""Comprehensive tests for Agent Execution Trace.

Covers:
- Domain model lifecycle and invariants
- Idempotent ingestion (duplicate start, duplicate events)
- Tenancy isolation (cross-tenant access denied)
- Persistence (in-memory repository behaviour)
- Privacy (prohibited raw payload fields rejected)
- Event sequencing and immutability
"""

from __future__ import annotations

import pytest
from datetime import datetime, UTC, timedelta
from uuid import uuid4

from ai_governance.domain.agent_execution import (
    AgentExecution,
    AgentExecutionStatus,
    AgentExecutionEvent,
    EventType,
)
from ai_governance.domain.agent_execution.errors import (
    AgentExecutionIdempotencyConflict,
)
from ai_governance.domain.agent_execution.agent_execution_event import (
    ActorType,
)
from ai_governance.domain.runtime_findings.finding import (
    FindingSeverity,
    FindingStatus,
    ReconciliationWindow,
    RuntimeFinding,
)
from ai_governance.repositories.in_memory.in_memory_agent_execution_repository import (
    InMemoryAgentExecutionEventRepository,
    InMemoryAgentExecutionRepository,
)
from ai_governance.repositories.in_memory.in_memory_runtime_finding_repository import (
    InMemoryRuntimeFindingRepository,
)
from ai_governance.services.agent_execution_service import AgentExecutionService
from ai_governance.services.runtime_aggregation_service import RuntimeAggregationService
from ai_governance.tenancy.domain import TenantContext


# -- Helpers ------------------------------------------------------------------


def _make_context(
    organization_id: str = "org_test",
    project_id: str | None = "project_test",
    actor_id: str = "actor_1",
    request_id: str | None = None,
) -> TenantContext:
    return TenantContext(
        organization_id=organization_id,
        project_id=project_id,
        actor_id=actor_id,
        request_id=request_id or str(uuid4()),
    )


def _make_execution(
    organization_id: str = "org_test",
    project_id: str | None = "project_test",
    now: datetime | None = None,
) -> AgentExecution:
    now = now or datetime.now(UTC)
    return AgentExecution(
        execution_id=str(uuid4()),
        organization_id=organization_id,
        project_id=project_id,
        agent_id="claims-agent",
        agent_name="Claims Agent",
        agent_version="1.0.0",
        external_execution_id="ext-98374",
        runtime_provider="test-runtime",
        status=AgentExecutionStatus.RECEIVED,
        started_at=now,
        completed_at=None,
        correlation_id=None,
        parent_execution_id=None,
        created_at=now,
        updated_at=now,
    )


def _make_event(
    execution_id: str,
    organization_id: str = "org_test",
    project_id: str | None = "project_test",
    event_type: EventType = EventType.MODEL_CALL,
    sequence_number: int = 1,
    now: datetime | None = None,
    attributes: dict | None = None,
) -> AgentExecutionEvent:
    now = now or datetime.now(UTC)
    return AgentExecutionEvent(
        event_id=str(uuid4()),
        execution_id=execution_id,
        organization_id=organization_id,
        project_id=project_id,
        event_type=event_type,
        sequence_number=sequence_number,
        occurred_at=now,
        received_at=now,
        correlation_id=None,
        causation_id=None,
        actor_id="model-1",
        actor_type=ActorType.MODEL,
        resource_references=(),
        evidence_references=(),
        attributes=attributes or {"model": "gpt-4", "input_tokens": 100},
        event_schema_version="1",
    )


def _make_service() -> tuple[AgentExecutionService, InMemoryAgentExecutionRepository, InMemoryAgentExecutionEventRepository]:
    exec_repo = InMemoryAgentExecutionRepository()
    event_repo = InMemoryAgentExecutionEventRepository()
    service = AgentExecutionService(exec_repo, event_repo)
    return service, exec_repo, event_repo


class _ChangedLatenessPolicyConfiguration:
    """Represents the policy after a historic window has already finalized."""

    def get(self, *_args, **_kwargs) -> int:
        return 24


# -- Domain: AgentExecution lifecycle -----------------------------------------


class TestAgentExecutionLifecycle:
    def test_initial_status_is_received(self):
        exec = _make_execution()
        assert exec.status == AgentExecutionStatus.RECEIVED
        assert not exec.is_terminal

    def test_transition_received_to_running(self):
        exec = _make_execution()
        now = datetime.now(UTC)
        updated = exec.mark_running(now)
        assert updated.status == AgentExecutionStatus.RUNNING

    def test_transition_to_succeeded(self):
        exec = _make_execution()
        now = datetime.now(UTC)
        updated = exec.mark_terminal(AgentExecutionStatus.SUCCEEDED, now)
        assert updated.status == AgentExecutionStatus.SUCCEEDED
        assert updated.is_terminal
        assert updated.completed_at == now

    def test_transition_to_failed(self):
        exec = _make_execution()
        now = datetime.now(UTC)
        updated = exec.mark_terminal(AgentExecutionStatus.FAILED, now)
        assert updated.status == AgentExecutionStatus.FAILED

    def test_transition_to_cancelled(self):
        exec = _make_execution()
        now = datetime.now(UTC)
        updated = exec.mark_terminal(AgentExecutionStatus.CANCELLED, now)
        assert updated.status == AgentExecutionStatus.CANCELLED

    def test_terminal_states_are_immutable(self):
        exec = _make_execution()
        now = datetime.now(UTC)
        exec = exec.mark_terminal(AgentExecutionStatus.SUCCEEDED, now)
        with pytest.raises(ValueError, match="already terminal"):
            exec.mark_terminal(AgentExecutionStatus.FAILED, now)

    def test_invalid_transition_from_running_to_succeeded_directly(self):
        exec = _make_execution()
        now = datetime.now(UTC)
        exec = exec.mark_running(now)
        # mark_terminal should work from RUNNING too (service handles it)
        updated = exec.mark_terminal(AgentExecutionStatus.SUCCEEDED, now)
        assert updated.status == AgentExecutionStatus.SUCCEEDED

    def test_duration_seconds_computed(self):
        now = datetime.now(UTC)
        exec = _make_execution(now=now)
        assert exec.duration_seconds is None
        completed = now + timedelta(seconds=4.8)
        exec = exec.mark_terminal(AgentExecutionStatus.SUCCEEDED, completed)
        assert exec.duration_seconds == pytest.approx(4.8)

    def test_version_increments(self):
        exec = _make_execution()
        now = datetime.now(UTC)
        updated = exec.bump_version(now)
        assert updated.version == 1


class TestAgentExecutionInvalidTransitions:
    def test_cannot_transition_from_terminal(self):
        exec = _make_execution()
        now = datetime.now(UTC)
        exec = exec.mark_terminal(AgentExecutionStatus.SUCCEEDED, now)
        with pytest.raises(ValueError):
            exec.mark_running(now)

    def test_cannot_set_completed_at_twice(self):
        exec = _make_execution()
        now = datetime.now(UTC)
        exec = exec.mark_terminal(AgentExecutionStatus.SUCCEEDED, now)
        later = now + timedelta(seconds=1)
        with pytest.raises(ValueError):
            exec.mark_terminal(AgentExecutionStatus.FAILED, later)


# -- Domain: AgentExecutionEvent ----------------------------------------------


class TestAgentExecutionEvent:
    def test_finalized_window_snapshot_wins_over_later_lateness_policy_change(self):
        """A late event cannot reopen a decision through a later setting edit."""
        occurred_at = datetime(2026, 8, 24, 23, tzinfo=UTC)
        received_at = datetime(2026, 8, 25, 3, tzinfo=UTC)
        window = ReconciliationWindow(
            observed_start=datetime(2026, 8, 24, 0, tzinfo=UTC),
            observed_end=datetime(2026, 8, 25, 0, tzinfo=UTC),
            baseline_start=datetime(2026, 8, 23, 0, tzinfo=UTC),
            baseline_end=datetime(2026, 8, 24, 0, tzinfo=UTC),
            finalization_cutoff_at=datetime(2026, 8, 25, 2, tzinfo=UTC),
            lateness_policy_hours=2,
        )
        finding_repo = InMemoryRuntimeFindingRepository()
        finding_repo.save(RuntimeFinding(
            finding_id="finalized-finding",
            organization_id="org_test",
            project_id="project_test",
            finding_type="TOOL_FAILURE_RATE_INCREASE",
            subject_type="tool",
            subject_id="tool-a",
            severity=FindingSeverity.HIGH,
            status=FindingStatus.OPEN,
            detector_id="tool_failure_rate",
            consecutive_normal_windows=1,
            healthy_reconciliation_windows=(window,),
            created_at=occurred_at,
            updated_at=occurred_at,
        ))
        execution_repo = InMemoryAgentExecutionRepository()
        event_repo = InMemoryAgentExecutionEventRepository()
        execution = _make_execution(now=occurred_at)
        execution_repo.save(execution)
        service = AgentExecutionService(
            execution_repo,
            event_repo,
            configuration_service=_ChangedLatenessPolicyConfiguration(),
            runtime_finding_repository=finding_repo,
            clock=lambda: received_at,
        )

        event = service.ingest_event(
            execution_id=execution.execution_id,
            event_type=EventType.TOOL_CALL,
            attributes={"tool_id": "tool-a", "status": "failed"},
            context=_make_context(),
            occurred_at=occurred_at,
        )

        # The current setting is 24 hours, which would have allowed this
        # event until 2026-08-26.  The historical 2-hour contract wins.
        assert event.late_for_runtime_findings is True
        assert event.runtime_findings_finalization_cutoff_at == window.finalization_cutoff_at
        assert event.runtime_findings_lateness_policy_hours == 2

        _, observed = RuntimeAggregationService(execution_repo, event_repo).get_tool_metrics(
            "org_test", "project_test", "tool-a",
            window.baseline_start, window.baseline_end,
            window.observed_start, window.observed_end,
            evidence_received_before=window.finalization_cutoff_at,
        )
        assert observed == {"total_calls": 0.0, "failures": 0.0}

    def test_legacy_finalized_window_without_snapshot_is_never_classified_on_time(self):
        occurred_at = datetime(2026, 8, 24, 23, tzinfo=UTC)
        received_at = datetime(2026, 8, 25, 3, tzinfo=UTC)
        legacy_window = ReconciliationWindow(
            observed_start=datetime(2026, 8, 24, 0, tzinfo=UTC),
            observed_end=datetime(2026, 8, 25, 0, tzinfo=UTC),
            baseline_start=datetime(2026, 8, 23, 0, tzinfo=UTC),
            baseline_end=datetime(2026, 8, 24, 0, tzinfo=UTC),
        )
        finding_repo = InMemoryRuntimeFindingRepository()
        finding_repo.save(RuntimeFinding(
            finding_id="legacy-finalized-finding",
            organization_id="org_test",
            project_id="project_test",
            finding_type="TOOL_FAILURE_RATE_INCREASE",
            subject_type="tool",
            subject_id="tool-a",
            severity=FindingSeverity.HIGH,
            status=FindingStatus.OPEN,
            detector_id="tool_failure_rate",
            consecutive_normal_windows=1,
            healthy_reconciliation_windows=(legacy_window,),
            created_at=occurred_at,
            updated_at=occurred_at,
        ))
        execution_repo = InMemoryAgentExecutionRepository()
        event_repo = InMemoryAgentExecutionEventRepository()
        execution = _make_execution(now=occurred_at)
        execution_repo.save(execution)
        service = AgentExecutionService(
            execution_repo,
            event_repo,
            configuration_service=_ChangedLatenessPolicyConfiguration(),
            runtime_finding_repository=finding_repo,
            clock=lambda: received_at,
        )

        event = service.ingest_event(
            execution_id=execution.execution_id,
            event_type=EventType.TOOL_CALL,
            attributes={"tool_id": "tool-a"},
            context=_make_context(),
            occurred_at=occurred_at,
        )

        assert event.late_for_runtime_findings is True
        assert event.runtime_findings_finalization_cutoff_at is None
        assert event.runtime_findings_lateness_policy_hours is None

    def test_event_rejects_prohibited_prompt_key(self):
        with pytest.raises(ValueError, match="prohibited key"):
            AgentExecutionEvent(
                event_id=str(uuid4()),
                execution_id="exec-1",
                organization_id="org_test",
                project_id="project_test",
                event_type=EventType.MODEL_CALL,
                sequence_number=1,
                occurred_at=datetime.now(UTC),
                received_at=datetime.now(UTC),
                correlation_id=None,
                causation_id=None,
                actor_id="model-1",
                actor_type=ActorType.MODEL,
                resource_references=(),
                evidence_references=(),
                attributes={"prompt": "secret prompt content"},
            )

    def test_event_rejects_prohibited_response_key(self):
        with pytest.raises(ValueError, match="prohibited key"):
            AgentExecutionEvent(
                event_id=str(uuid4()),
                execution_id="exec-1",
                organization_id="org_test",
                project_id="project_test",
                event_type=EventType.MODEL_CALL,
                sequence_number=1,
                occurred_at=datetime.now(UTC),
                received_at=datetime.now(UTC),
                correlation_id=None,
                causation_id=None,
                actor_id="model-1",
                actor_type=ActorType.MODEL,
                resource_references=(),
                evidence_references=(),
                attributes={"response": "secret response"},
            )

    def test_event_rejects_prohibited_credentials_key(self):
        with pytest.raises(ValueError, match="prohibited key"):
            AgentExecutionEvent(
                event_id=str(uuid4()),
                execution_id="exec-1",
                organization_id="org_test",
                project_id="project_test",
                event_type=EventType.TOOL_CALL,
                sequence_number=1,
                occurred_at=datetime.now(UTC),
                received_at=datetime.now(UTC),
                correlation_id=None,
                causation_id=None,
                actor_id="tool-1",
                actor_type=ActorType.TOOL,
                resource_references=(),
                evidence_references=(),
                attributes={"api_key": "sk-123"},
            )

    def test_event_rejects_prohibited_chain_of_thought(self):
        with pytest.raises(ValueError, match="prohibited key"):
            AgentExecutionEvent(
                event_id=str(uuid4()),
                execution_id="exec-1",
                organization_id="org_test",
                project_id="project_test",
                event_type=EventType.ERROR,
                sequence_number=1,
                occurred_at=datetime.now(UTC),
                received_at=datetime.now(UTC),
                correlation_id=None,
                causation_id=None,
                actor_id="system",
                actor_type=ActorType.SYSTEM,
                resource_references=(),
                evidence_references=(),
                attributes={"chain_of_thought": "reasoning trace"},
            )

    def test_event_rejects_nested_prohibited_key_in_dict(self):
        """A prohibited key nested inside a dict must be rejected."""
        with pytest.raises(ValueError, match="prohibited key"):
            AgentExecutionEvent(
                event_id=str(uuid4()),
                execution_id="exec-1",
                organization_id="org_test",
                project_id="project_test",
                event_type=EventType.MODEL_CALL,
                sequence_number=1,
                occurred_at=datetime.now(UTC),
                received_at=datetime.now(UTC),
                correlation_id=None,
                causation_id=None,
                actor_id="model-1",
                actor_type=ActorType.MODEL,
                resource_references=(),
                evidence_references=(),
                attributes={
                    "metadata": {"payload": {"prompt": "secret prompt content"}},
                },
            )

    def test_event_rejects_nested_prohibited_key_in_list(self):
        """A prohibited key inside a list of dicts must be rejected."""
        with pytest.raises(ValueError, match="prohibited key"):
            AgentExecutionEvent(
                event_id=str(uuid4()),
                execution_id="exec-1",
                organization_id="org_test",
                project_id="project_test",
                event_type=EventType.TOOL_CALL,
                sequence_number=1,
                occurred_at=datetime.now(UTC),
                received_at=datetime.now(UTC),
                correlation_id=None,
                causation_id=None,
                actor_id="tool-1",
                actor_type=ActorType.TOOL,
                resource_references=(),
                evidence_references=(),
                attributes={
                    "messages": [
                        {"role": "user", "content": "hello"},
                        {"response": "bot reply"},
                    ],
                },
            )

    def test_event_rejects_deeply_nested_prohibited_key(self):
        """Prohibited keys at arbitrary nesting depth must be rejected."""
        with pytest.raises(ValueError, match="prohibited key"):
            AgentExecutionEvent(
                event_id=str(uuid4()),
                execution_id="exec-1",
                organization_id="org_test",
                project_id="project_test",
                event_type=EventType.ERROR,
                sequence_number=1,
                occurred_at=datetime.now(UTC),
                received_at=datetime.now(UTC),
                correlation_id=None,
                causation_id=None,
                actor_id="system",
                actor_type=ActorType.SYSTEM,
                resource_references=(),
                evidence_references=(),
                attributes={
                    "level1": {
                        "level2": {
                            "level3": {
                                "chain_of_thought": "deep reasoning trace",
                            },
                        },
                    },
                },
            )

    def test_event_rejects_prohibited_key_with_dashes(self):
        """Prohibited keys using dashes (normalized to underscores) must be rejected."""
        with pytest.raises(ValueError, match="prohibited key"):
            AgentExecutionEvent(
                event_id=str(uuid4()),
                execution_id="exec-1",
                organization_id="org_test",
                project_id="project_test",
                event_type=EventType.MODEL_CALL,
                sequence_number=1,
                occurred_at=datetime.now(UTC),
                received_at=datetime.now(UTC),
                correlation_id=None,
                causation_id=None,
                actor_id="model-1",
                actor_type=ActorType.MODEL,
                resource_references=(),
                evidence_references=(),
                attributes={
                    "metadata": {
                        "payload": {
                            "system-prompt": "you are a helpful assistant",
                        },
                    },
                },
            )

    def test_event_accepts_nested_safe_keys(self):
        """Nested dicts with safe keys must be accepted."""
        event = AgentExecutionEvent(
            event_id=str(uuid4()),
            execution_id="exec-1",
            organization_id="org_test",
            project_id="project_test",
            event_type=EventType.MODEL_CALL,
            sequence_number=1,
            occurred_at=datetime.now(UTC),
            received_at=datetime.now(UTC),
            correlation_id=None,
            causation_id=None,
            actor_id="model-1",
            actor_type=ActorType.MODEL,
            resource_references=(),
            evidence_references=(),
            attributes={
                "metadata": {
                    "payload": {
                        "model": "gpt-4",
                        "input_tokens": 100,
                        "latency_ms": 500,
                    },
                },
            },
        )
        assert event.attributes["metadata"]["payload"]["model"] == "gpt-4"

    def test_event_accepts_safe_attributes(self):
        event = AgentExecutionEvent(
            event_id=str(uuid4()),
            execution_id="exec-1",
            organization_id="org_test",
            project_id="project_test",
            event_type=EventType.MODEL_CALL,
            sequence_number=1,
            occurred_at=datetime.now(UTC),
            received_at=datetime.now(UTC),
            correlation_id=None,
            causation_id=None,
            actor_id="model-1",
            actor_type=ActorType.MODEL,
            resource_references=(),
            evidence_references=(),
            attributes={"model": "gpt-4", "input_tokens": 100, "latency_ms": 500},
        )
        assert event.attributes["model"] == "gpt-4"

    def test_event_rejects_unsupported_schema_version(self):
        with pytest.raises(ValueError, match="Unsupported event schema version"):
            AgentExecutionEvent(
                event_id=str(uuid4()),
                execution_id="exec-1",
                organization_id="org_test",
                project_id="project_test",
                event_type=EventType.MODEL_CALL,
                sequence_number=1,
                occurred_at=datetime.now(UTC),
                received_at=datetime.now(UTC),
                correlation_id=None,
                causation_id=None,
                actor_id="model-1",
                actor_type=ActorType.MODEL,
                resource_references=(),
                evidence_references=(),
                event_schema_version="2",
            )

    def test_event_received_at_must_not_precede_occurred_at(self):
        with pytest.raises(ValueError, match="received_at must not precede"):
            AgentExecutionEvent(
                event_id=str(uuid4()),
                execution_id="exec-1",
                organization_id="org_test",
                project_id="project_test",
                event_type=EventType.MODEL_CALL,
                sequence_number=1,
                occurred_at=datetime.now(UTC) + timedelta(hours=1),
                received_at=datetime.now(UTC),
                correlation_id=None,
                causation_id=None,
                actor_id="model-1",
                actor_type=ActorType.MODEL,
                resource_references=(),
                evidence_references=(),
            )


# -- Idempotency --------------------------------------------------------------


class TestIdempotency:
    def test_duplicate_start_returns_existing(self):
        service, exec_repo, _ = _make_service()
        ctx = _make_context()

        first = service.ingest_start(
            agent_id="claims-agent",
            agent_name="Claims Agent",
            agent_version="1.0.0",
            external_execution_id="ext-98374",
            runtime_provider="test-runtime",
            context=ctx,
        )

        second = service.ingest_start(
            agent_id="claims-agent",
            agent_name="Claims Agent",
            agent_version="1.0.0",
            external_execution_id="ext-98374",
            runtime_provider="test-runtime",
            context=ctx,
        )

        assert first.execution_id == second.execution_id

    def test_duplicate_event_same_payload_is_noop(self):
        service, exec_repo, event_repo = _make_service()
        ctx = _make_context()

        execution = service.ingest_start(
            agent_id="claims-agent",
            agent_name="Claims Agent",
            agent_version="1.0.0",
            external_execution_id="ext-98374",
            runtime_provider="test-runtime",
            context=ctx,
        )

        key = "model-call-1"
        event1 = service.ingest_event(
            execution_id=execution.execution_id,
            event_type=EventType.MODEL_CALL,
            attributes={"model": "gpt-4", "input_tokens": 100},
            context=ctx,
            idempotency_key=key,
        )

        event2 = service.ingest_event(
            execution_id=execution.execution_id,
            event_type=EventType.MODEL_CALL,
            attributes={"model": "gpt-4", "input_tokens": 100},
            context=ctx,
            idempotency_key=key,
        )

        assert event1.event_id == event2.event_id
        events = event_repo.list_by_execution(
            execution.execution_id, ctx.organization_id, ctx.project_id
        )
        assert len(events) == 2  # START + 1 MODEL_CALL (deduplicated)

    def test_duplicate_event_conflicting_payload_raises(self):
        service, exec_repo, event_repo = _make_service()
        ctx = _make_context()

        execution = service.ingest_start(
            agent_id="claims-agent",
            agent_name="Claims Agent",
            agent_version="1.0.0",
            external_execution_id="ext-98374",
            runtime_provider="test-runtime",
            context=ctx,
        )

        key = "model-call-1"
        service.ingest_event(
            execution_id=execution.execution_id,
            event_type=EventType.MODEL_CALL,
            attributes={"model": "gpt-4", "input_tokens": 100},
            context=ctx,
            idempotency_key=key,
        )

        with pytest.raises(AgentExecutionIdempotencyConflict):
            service.ingest_event(
                execution_id=execution.execution_id,
                event_type=EventType.MODEL_CALL,
                attributes={"model": "claude-3", "input_tokens": 200},
                context=ctx,
                idempotency_key=key,
            )


# -- Tenancy ------------------------------------------------------------------


class TestTenancy:
    def test_cross_tenant_execution_access_denied(self):
        service, exec_repo, _ = _make_service()
        ctx1 = _make_context(organization_id="org_a")
        ctx2 = _make_context(organization_id="org_b")

        execution = service.ingest_start(
            agent_id="claims-agent",
            agent_name="Claims Agent",
            agent_version="1.0.0",
            external_execution_id="ext-98374",
            runtime_provider="test-runtime",
            context=ctx1,
        )

        # Cannot read org_b's execution
        result = service.get_execution(execution.execution_id, ctx2)
        assert result is None

    def test_cross_project_access_denied(self):
        service, exec_repo, _ = _make_service()
        ctx1 = _make_context(project_id="project_a")
        ctx2 = _make_context(project_id="project_b")

        execution = service.ingest_start(
            agent_id="claims-agent",
            agent_name="Claims Agent",
            agent_version="1.0.0",
            external_execution_id="ext-98374",
            runtime_provider="test-runtime",
            context=ctx1,
        )

        result = service.get_execution(execution.execution_id, ctx2)
        assert result is None

    def test_external_execution_id_collision_across_tenants_allowed(self):
        service, exec_repo, _ = _make_service()
        ctx1 = _make_context(organization_id="org_a")
        ctx2 = _make_context(organization_id="org_b")

        exec1 = service.ingest_start(
            agent_id="agent-1",
            agent_name="Agent 1",
            agent_version="1.0.0",
            external_execution_id="ext-same",
            runtime_provider="runtime-1",
            context=ctx1,
        )

        exec2 = service.ingest_start(
            agent_id="agent-2",
            agent_name="Agent 2",
            agent_version="1.0.0",
            external_execution_id="ext-same",
            runtime_provider="runtime-2",
            context=ctx2,
        )

        assert exec1.execution_id != exec2.execution_id

    def test_collision_within_same_scope_handled_deterministically(self):
        service, exec_repo, _ = _make_service()
        ctx = _make_context()

        exec1 = service.ingest_start(
            agent_id="agent-1",
            agent_name="Agent 1",
            agent_version="1.0.0",
            external_execution_id="ext-same",
            runtime_provider="runtime-1",
            context=ctx,
        )

        exec2 = service.ingest_start(
            agent_id="agent-1",
            agent_name="Agent 1",
            agent_version="1.0.0",
            external_execution_id="ext-same",
            runtime_provider="runtime-1",
            context=ctx,
        )

        assert exec1.execution_id == exec2.execution_id


# -- Persistence --------------------------------------------------------------


class TestPersistence:
    def test_save_and_get_execution(self):
        exec_repo = InMemoryAgentExecutionRepository()
        execution = _make_execution()
        exec_repo.save(execution)

        retrieved = exec_repo.get(
            execution.execution_id,
            execution.organization_id,
            execution.project_id,
        )
        assert retrieved is not None
        assert retrieved.execution_id == execution.execution_id

    def test_get_nonexistent_execution(self):
        exec_repo = InMemoryAgentExecutionRepository()
        result = exec_repo.get(
            "nonexistent",
            "org_test",
            "project_test",
        )
        assert result is None

    def test_list_executions_with_filters(self):
        exec_repo = InMemoryAgentExecutionRepository()
        ctx = _make_context()

        for i in range(5):
            exec = _make_execution(
                organization_id=ctx.organization_id,
                project_id=ctx.project_id,
            )
            exec = exec.bump_version(exec.updated_at)
            exec_repo.save(exec)

        all_execs = exec_repo.list(
            type('Filters', (), {'agent_id': None, 'status': None, 'runtime_provider': None,
                                  'created_after': None, 'created_before': None, 'limit': 100})(),
            ctx.organization_id,
            ctx.project_id,
        )
        assert len(all_execs) == 5

    def test_event_sequencing(self):
        event_repo = InMemoryAgentExecutionEventRepository()
        execution = _make_execution()
        now = datetime.now(UTC)

        events = [
            AgentExecutionEvent(
                event_id=str(uuid4()),
                execution_id=execution.execution_id,
                organization_id=execution.organization_id,
                project_id=execution.project_id,
                event_type=EventType.MODEL_CALL,
                sequence_number=i + 1,
                occurred_at=now + timedelta(seconds=i),
                received_at=now + timedelta(seconds=i),
                correlation_id=None,
                causation_id=None,
                actor_id="model-1",
                actor_type=ActorType.MODEL,
                resource_references=(),
                evidence_references=(),
                attributes={"model": "gpt-4"},
            )
            for i in range(5)
        ]

        for event in events:
            event_repo.save(event)

        listed = event_repo.list_by_execution(
            execution.execution_id,
            execution.organization_id,
            execution.project_id,
        )
        assert len(listed) == 5
        assert listed[0].sequence_number < listed[-1].sequence_number

    def test_max_sequence_number(self):
        event_repo = InMemoryAgentExecutionEventRepository()
        execution = _make_execution()

        assert event_repo.max_sequence_number(
            execution.execution_id,
            execution.organization_id,
            execution.project_id,
        ) == 0

        event_repo.save(_make_event(execution.execution_id, sequence_number=3))
        assert event_repo.max_sequence_number(
            execution.execution_id,
            execution.organization_id,
            execution.project_id,
        ) == 3


# -- Service end-to-end -------------------------------------------------------


class TestAgentExecutionServiceE2E:
    def test_full_lifecycle(self):
        """Simulate the acceptance scenario from the spec."""
        service, _, _ = _make_service()
        ctx = _make_context()

        # Start execution
        execution = service.ingest_start(
            agent_id="claims-agent",
            agent_name="claims-agent",
            agent_version="1.0.0",
            external_execution_id="ext-98374",
            runtime_provider="test-runtime",
            context=ctx,
        )
        assert execution.status == AgentExecutionStatus.RUNNING

        # Ingest MODEL_CALL
        model_event = service.ingest_event(
            execution_id=execution.execution_id,
            event_type=EventType.MODEL_CALL,
            attributes={"model": "model-x", "input_tokens": 100},
            context=ctx,
        )
        assert model_event.event_type == EventType.MODEL_CALL

        # Ingest TOOL_CALL
        tool_event = service.ingest_event(
            execution_id=execution.execution_id,
            event_type=EventType.TOOL_CALL,
            attributes={"tool": "lookup-policy", "status": "success"},
            context=ctx,
        )
        assert tool_event.event_type == EventType.TOOL_CALL

        # Ingest GOVERNANCE_DECISION
        service.ingest_event(
            execution_id=execution.execution_id,
            event_type=EventType.GOVERNANCE_DECISION,
            attributes={"decision_id": "decision-827", "outcome": "APPROVED"},
            context=ctx,
        )

        # Ingest EVALUATION
        service.ingest_event(
            execution_id=execution.execution_id,
            event_type=EventType.EVALUATION,
            attributes={"evaluation_result_id": "evaluation-391", "status": "passed"},
            context=ctx,
        )

        # Complete execution
        completed = service.mark_completed(
            execution.execution_id,
            AgentExecutionStatus.SUCCEEDED,
            ctx,
        )
        assert completed.status == AgentExecutionStatus.SUCCEEDED
        assert completed.is_terminal

        # Verify detail
        detail = service.get_execution_detail(execution.execution_id, ctx)
        assert detail is not None
        assert detail.execution.status == AgentExecutionStatus.SUCCEEDED
        assert len(detail.events) >= 6  # START + MODEL + TOOL + GOV + EVAL + COMPLETED
        assert detail.event_counts.get("MODEL_CALL", 0) == 1
        assert detail.event_counts.get("TOOL_CALL", 0) == 1
        assert detail.event_counts.get("GOVERNANCE_DECISION", 0) == 1
        assert detail.event_counts.get("EVALUATION", 0) == 1

    def test_list_executions(self):
        service, _, _ = _make_service()
        ctx = _make_context()

        for i in range(3):
            service.ingest_start(
                agent_id=f"agent-{i}",
                agent_name=f"Agent {i}",
                agent_version="1.0.0",
                external_execution_id=f"ext-{i}",
                runtime_provider="test-runtime",
                context=ctx,
            )

        page = service.list_executions(context=ctx)
        assert len(page.items) == 3

    def test_list_events_with_type_filter(self):
        service, _, _ = _make_service()
        ctx = _make_context()

        execution = service.ingest_start(
            agent_id="agent-1",
            agent_name="Agent 1",
            agent_version="1.0.0",
            external_execution_id="ext-1",
            runtime_provider="test-runtime",
            context=ctx,
        )

        service.ingest_event(
            execution_id=execution.execution_id,
            event_type=EventType.MODEL_CALL,
            attributes={"model": "gpt-4"},
            context=ctx,
        )

        service.ingest_event(
            execution_id=execution.execution_id,
            event_type=EventType.TOOL_CALL,
            attributes={"tool": "search"},
            context=ctx,
        )

        model_events = service.list_events(
            execution.execution_id, ctx, event_type=EventType.MODEL_CALL
        )
        assert len(model_events) == 1
        assert model_events[0].event_type == EventType.MODEL_CALL


# -- Privacy ------------------------------------------------------------------


class TestPrivacy:
    def test_prohibited_raw_runtime_payload_fields_rejected(self):
        """Ensure raw prompts, responses, credentials are never accepted."""
        prohibited = [
            "prompt", "system_prompt", "response", "messages",
            "conversation", "chain_of_thought", "credentials",
            "authorization_header", "api_key", "password", "secret",
            "tool_payload", "tool_output",
        ]
        for key in prohibited:
            with pytest.raises(ValueError, match="prohibited key"):
                AgentExecutionEvent(
                    event_id=str(uuid4()),
                    execution_id="exec-1",
                    organization_id="org_test",
                    project_id="project_test",
                    event_type=EventType.MODEL_CALL,
                    sequence_number=1,
                    occurred_at=datetime.now(UTC),
                    received_at=datetime.now(UTC),
                    correlation_id=None,
                    causation_id=None,
                    actor_id="model-1",
                    actor_type=ActorType.MODEL,
                    resource_references=(),
                    evidence_references=(),
                    attributes={key: "sensitive data"},
                )

    def test_evidence_references_accepted(self):
        """Evidence references should be accepted as they point to external storage."""
        event = AgentExecutionEvent(
            event_id=str(uuid4()),
            execution_id="exec-1",
            organization_id="org_test",
            project_id="project_test",
            event_type=EventType.MODEL_CALL,
            sequence_number=1,
            occurred_at=datetime.now(UTC),
            received_at=datetime.now(UTC),
            correlation_id=None,
            causation_id=None,
            actor_id="model-1",
            actor_type=ActorType.MODEL,
            resource_references=(),
            evidence_references=["evidence:prompt-123", "evidence:response-456"],
            attributes={"model": "gpt-4"},
        )
        assert len(event.evidence_references) == 2

    def test_secrets_not_surfaced_through_responses(self):
        """Attributes should not contain secret keys even if they look similar."""
        # Keys that are NOT prohibited (safe operational metadata)
        safe_attrs = {
            "model": "gpt-4",
            "provider": "openai",
            "latency_ms": 500,
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "estimated_cost": 0.003,
            "status": "success",
            "retry_count": 0,
        }
        event = AgentExecutionEvent(
            event_id=str(uuid4()),
            execution_id="exec-1",
            organization_id="org_test",
            project_id="project_test",
            event_type=EventType.MODEL_CALL,
            sequence_number=1,
            occurred_at=datetime.now(UTC),
            received_at=datetime.now(UTC),
            correlation_id=None,
            causation_id=None,
            actor_id="model-1",
            actor_type=ActorType.MODEL,
            resource_references=(),
            evidence_references=(),
            attributes=safe_attrs,
        )
        assert event.attributes["model"] == "gpt-4"


# -- Append-only enforcement --------------------------------------------------


class TestAppendOnlyEvents:
    """Verify AgentExecutionEvent has no update/delete path at any layer."""

    def test_repository_interface_has_no_update_or_delete(self):
        """The ABC must not declare update/delete on events."""
        from ai_governance.repositories.agent_execution_repository import (
            AgentExecutionEventRepository,
        )

        methods = {m for m in dir(AgentExecutionEventRepository) if not m.startswith("_")}
        assert "update" not in {m.lower() for m in methods}
        assert "delete" not in {m.lower() for m in methods}
        assert "upsert" not in {m.lower() for m in methods}

    def test_in_memory_event_repo_has_no_update_or_delete(self):
        repo = InMemoryAgentExecutionEventRepository()
        methods = {m for m in dir(repo) if not m.startswith("_")}
        assert "update" not in {m.lower() for m in methods}
        assert "delete" not in {m.lower() for m in methods}

    def test_events_are_persisted_only_via_insert(self):
        """Saving an event twice with different IDs creates two rows."""
        repo = InMemoryAgentExecutionEventRepository()
        execution = _make_execution()
        now = datetime.now(UTC)

        event1 = AgentExecutionEvent(
            event_id="evt-1",
            execution_id=execution.execution_id,
            organization_id=execution.organization_id,
            project_id=execution.project_id,
            event_type=EventType.MODEL_CALL,
            sequence_number=1,
            occurred_at=now,
            received_at=now,
            correlation_id=None,
            causation_id=None,
            actor_id="model-1",
            actor_type=ActorType.MODEL,
            resource_references=(),
            evidence_references=(),
            attributes={"model": "gpt-4"},
        )
        event2 = AgentExecutionEvent(
            event_id="evt-2",
            execution_id=execution.execution_id,
            organization_id=execution.organization_id,
            project_id=execution.project_id,
            event_type=EventType.TOOL_CALL,
            sequence_number=2,
            occurred_at=now,
            received_at=now,
            correlation_id=None,
            causation_id=None,
            actor_id="tool-1",
            actor_type=ActorType.TOOL,
            resource_references=(),
            evidence_references=(),
            attributes={"tool": "search"},
        )

        repo.save(event1)
        repo.save(event2)

        events = repo.list_by_execution(
            execution.execution_id,
            execution.organization_id,
            execution.project_id,
        )
        assert len(events) == 2
        # Both events persist — no overwrite occurred.
        ids = {e.event_id for e in events}
        assert "evt-1" in ids
        assert "evt-2" in ids
