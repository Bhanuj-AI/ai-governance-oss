"""PostgreSQL persistence coverage for runtime action execution receipts."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier

from ai_governance.databases.postgres.database import PostgresDatabase
from ai_governance.domain.agent_execution import (
    ActorType,
    AgentExecution,
    AgentExecutionEvent,
    AgentExecutionStatus,
    EventType,
)
from ai_governance.domain.agent_execution.errors import (
    AgentExecutionIdempotencyConflict,
)
from ai_governance.repositories.postgres.postgres_agent_execution_repository import (
    PostgresAgentExecutionEventRepository,
    PostgresAgentExecutionRepository,
)
from ai_governance.services.agent_execution_service import AgentExecutionService
from ai_governance.tenancy.domain import TenantContext

NOW = datetime(2026, 10, 25, 8, 0, tzinfo=UTC)
CONTEXT = TenantContext("org-a", "project-a", "runtime-a", "request-a")
ARGUMENT_DIGEST = "sha256:" + "a" * 64
RESULT_DIGEST = "sha256:" + "b" * 64
FINGERPRINT = "c" * 64


def _authorized_service(
    postgres_database: PostgresDatabase,
    suffix: str = "1",
) -> AgentExecutionService:
    execution_id = f"execution-{suffix}"
    decision_id = f"decision-{suffix}"
    executions = PostgresAgentExecutionRepository(postgres_database)
    events = PostgresAgentExecutionEventRepository(postgres_database)
    executions.save(
        AgentExecution(
            execution_id=execution_id,
            organization_id="org-a",
            project_id="project-a",
            agent_id="claims-agent",
            agent_name="Claims Agent",
            agent_version="1",
            external_execution_id=f"runtime-execution-{suffix}",
            runtime_provider="external-runtime",
            status=AgentExecutionStatus.RUNNING,
            started_at=NOW,
            completed_at=None,
            correlation_id=f"correlation-{suffix}",
            parent_execution_id=None,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    events.save(
        AgentExecutionEvent(
            event_id=decision_id,
            execution_id=execution_id,
            organization_id="org-a",
            project_id="project-a",
            event_type=EventType.RUNTIME_ACTION_AUTHORIZATION,
            sequence_number=1,
            occurred_at=NOW,
            received_at=NOW,
            correlation_id=f"correlation-{suffix}",
            causation_id=None,
            actor_id=CONTEXT.actor_id,
            actor_type=ActorType.GOVERNANCE,
            attributes={
                "authorization_outcome": "ALLOW",
                "request_fingerprint": FINGERPRINT,
                "action_id": "claims.update",
                "actor_id": CONTEXT.actor_id,
                "tool_arguments_digest": ARGUMENT_DIGEST,
            },
        )
    )
    return AgentExecutionService(executions, events, clock=lambda: NOW)


def _submit_receipt(
    service: AgentExecutionService,
    *,
    suffix: str,
    status: str,
    idempotency_key: str,
    supersedes_receipt_id: str | None = None,
):
    result = (
        {
            "result_reference": "artifact://claims/42/result",
            "result_digest": RESULT_DIGEST,
        }
        if status == "SUCCEEDED"
        else {}
    )
    return service.ingest_runtime_action_execution_receipt(
        execution_id=f"execution-{suffix}",
        decision_id=f"decision-{suffix}",
        request_fingerprint=FINGERPRINT,
        action_id="claims.update",
        runtime_tool_call_id=f"runtime-call-{suffix}",
        tool_arguments_digest=ARGUMENT_DIGEST,
        receipt_status=status,
        reason_code=f"RUNTIME_REPORTED_{status}",
        idempotency_key=idempotency_key,
        supersedes_receipt_id=supersedes_receipt_id,
        context=CONTEXT,
        **result,
    )


def test_postgres_round_trips_and_deduplicates_execution_receipts(
    postgres_database: PostgresDatabase,
) -> None:
    """Use the existing event JSONB store; a receipt has no table of its own."""

    service = _authorized_service(postgres_database)
    recorded = _submit_receipt(
        service,
        suffix="1",
        status="SUCCEEDED",
        idempotency_key="delivery-1",
    )

    reopened = PostgresAgentExecutionEventRepository(postgres_database)
    stored = reopened.get_by_id(
        recorded.event_id,
        "execution-1",
        "org-a",
        "project-a",
    )
    assert stored is not None
    assert stored.attributes["runtime_action_execution_receipt"] == recorded.attributes[
        "runtime_action_execution_receipt"
    ]

    duplicate = _submit_receipt(
        AgentExecutionService(
            PostgresAgentExecutionRepository(postgres_database),
            reopened,
            clock=lambda: NOW,
        ),
        suffix="1",
        status="SUCCEEDED",
        idempotency_key="delivery-retry",
    )

    assert duplicate.event_id == recorded.event_id


def test_postgres_concurrent_receipts_preserve_deduplication_and_supersession(
    postgres_database: PostgresDatabase,
) -> None:
    """Database races cannot create duplicate receipts or two reconciliations."""

    duplicate_service = _authorized_service(postgres_database, "duplicate")
    duplicate_barrier = Barrier(2)

    def submit_duplicate(idempotency_key: str) -> AgentExecutionEvent:
        duplicate_barrier.wait(timeout=5)
        return _submit_receipt(
            duplicate_service,
            suffix="duplicate",
            status="SUCCEEDED",
            idempotency_key=idempotency_key,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        duplicate_results = list(
            executor.map(submit_duplicate, ("delivery-a", "delivery-b"))
        )

    assert {event.event_id for event in duplicate_results} == {
        duplicate_results[0].event_id
    }
    duplicate_receipts = [
        event
        for event in PostgresAgentExecutionEventRepository(
            postgres_database
        ).list_by_execution("execution-duplicate", "org-a", "project-a")
        if event.event_type is EventType.RUNTIME_ACTION_EXECUTION_RECEIPT
    ]
    assert len(duplicate_receipts) == 1

    reconciliation_service = _authorized_service(postgres_database, "reconcile")
    unknown = _submit_receipt(
        reconciliation_service,
        suffix="reconcile",
        status="UNKNOWN",
        idempotency_key="unknown-delivery",
    )
    reconciliation_barrier = Barrier(2)

    def submit_conflicting_reconciliation(
        status: str,
        idempotency_key: str,
    ) -> AgentExecutionEvent | AgentExecutionIdempotencyConflict:
        reconciliation_barrier.wait(timeout=5)
        try:
            return _submit_receipt(
                reconciliation_service,
                suffix="reconcile",
                status=status,
                idempotency_key=idempotency_key,
                supersedes_receipt_id=unknown.event_id,
            )
        except AgentExecutionIdempotencyConflict as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        reconciliation_results = list(
            executor.map(
                lambda item: submit_conflicting_reconciliation(*item),
                (
                    ("SUCCEEDED", "reconciliation-success"),
                    ("FAILED", "reconciliation-failure"),
                ),
            )
        )

    accepted = [
        result for result in reconciliation_results if isinstance(result, AgentExecutionEvent)
    ]
    conflicts = [
        result
        for result in reconciliation_results
        if isinstance(result, AgentExecutionIdempotencyConflict)
    ]
    assert len(accepted) == 1
    assert len(conflicts) == 1

    persisted = PostgresAgentExecutionEventRepository(postgres_database).list_by_execution(
        "execution-reconcile",
        "org-a",
        "project-a",
    )
    superseding = [
        event
        for event in persisted
        if event.event_type is EventType.RUNTIME_ACTION_EXECUTION_RECEIPT
        and event.attributes["runtime_action_execution_receipt"].get(
            "supersedes_receipt_id"
        )
        == unknown.event_id
    ]
    assert len(superseding) == 1
    assert superseding[0].event_id == accepted[0].event_id
    assert (
        unknown.attributes["runtime_action_execution_receipt"]["status"]
        == "UNKNOWN"
    )
