"""Unit coverage for runtime-reported execution receipt invariants."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.decisions import (
    DecisionTargetType,
    PolicyCondition,
    PolicyConditionOperator,
    PolicyEffect,
    PolicyRule,
    PolicyStatus,
)
from ai_governance.decisions.policy_administration import (
    PolicyDefinition,
    PolicyVersion,
)
from ai_governance.decisions.policy_enums import PolicyCategory
from ai_governance.domain.agent_execution import (
    ActorType,
    AgentExecution,
    AgentExecutionEvent,
    AgentExecutionStatus,
    EventType,
)
from ai_governance.domain.agent_execution.errors import (
    AgentExecutionIdempotencyConflict,
    AgentExecutionInvalidTransition,
    AgentExecutionNotFound,
)
from ai_governance.repositories.in_memory.in_memory_agent_execution_repository import (
    InMemoryAgentExecutionEventRepository,
    InMemoryAgentExecutionRepository,
)
from ai_governance.repositories.in_memory.in_memory_runtime_action_delegation_repository import (
    InMemoryRuntimeActionDelegationRepository,
)
from ai_governance.repositories.in_memory_policy_administration_repository import (
    InMemoryPolicyAdministrationRepository,
)
from ai_governance.repositories.sqlite.sqlite_agent_execution_repository import (
    SQLiteAgentExecutionEventRepository,
    SQLiteAgentExecutionRepository,
)
from ai_governance.runtime_authorization import (
    RuntimeActionAuthorizationRequest,
    RuntimeActionDelegationPermission,
    RuntimeActionResource,
)
from ai_governance.runtime_authorization.delegation import (
    create_runtime_action_delegation,
)
from ai_governance.services.agent_execution_service import AgentExecutionService
from ai_governance.services.runtime_action_authorization_service import (
    RUNTIME_ACTION_AUTHORIZATION_METADATA_KEY,
    RUNTIME_ACTION_AUTHORIZATION_PURPOSE,
    RuntimeActionAuthorizationService,
)
from ai_governance.tenancy.domain import TenantContext

NOW = datetime(2026, 10, 25, 8, 0, tzinfo=UTC)
CONTEXT = TenantContext("org-a", "project-a", "runtime-a", "request-a")
ARGUMENT_DIGEST = "sha256:" + "a" * 64
RESULT_DIGEST = "sha256:" + "b" * 64
FINGERPRINT = "c" * 64


class Clock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def _setup(
    *,
    execution_repository: InMemoryAgentExecutionRepository
    | SQLiteAgentExecutionRepository
    | None = None,
    event_repository: InMemoryAgentExecutionEventRepository
    | SQLiteAgentExecutionEventRepository
    | None = None,
) -> tuple[
    AgentExecutionService,
    InMemoryAgentExecutionRepository | SQLiteAgentExecutionRepository,
    InMemoryAgentExecutionEventRepository | SQLiteAgentExecutionEventRepository,
    Clock,
]:
    clock = Clock()
    executions = execution_repository or InMemoryAgentExecutionRepository()
    events = event_repository or InMemoryAgentExecutionEventRepository()
    execution = AgentExecution(
        execution_id="execution-1",
        organization_id="org-a",
        project_id="project-a",
        agent_id="claims-agent",
        agent_name="Claims Agent",
        agent_version="1",
        external_execution_id="runtime-execution-1",
        runtime_provider="external-runtime",
        status=AgentExecutionStatus.RUNNING,
        started_at=NOW,
        completed_at=None,
        correlation_id="correlation-1",
        parent_execution_id=None,
        created_at=NOW,
        updated_at=NOW,
    )
    executions.save(execution)
    events.save(
        AgentExecutionEvent(
            event_id="decision-1",
            execution_id=execution.execution_id,
            organization_id=execution.organization_id,
            project_id=execution.project_id,
            event_type=EventType.RUNTIME_ACTION_AUTHORIZATION,
            sequence_number=1,
            occurred_at=NOW,
            received_at=NOW,
            correlation_id=execution.correlation_id,
            causation_id=None,
            actor_id=CONTEXT.actor_id,
            actor_type=ActorType.GOVERNANCE,
            attributes={
                "authorization_outcome": "ALLOW",
                "request_fingerprint": FINGERPRINT,
                "action_id": "claims.update",
                "actor_id": CONTEXT.actor_id,
                "tool_arguments_digest": ARGUMENT_DIGEST,
                # This time is intentionally short: receipt ingestion later
                # proves historical evidence, not a renewed authorization.
                "expires_at": (NOW + timedelta(minutes=5)).isoformat(),
                "delegation_id": "delegation-1",
            },
        )
    )
    return AgentExecutionService(executions, events, clock=clock), executions, events, clock


def _receipt_kwargs(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "execution_id": "execution-1",
        "decision_id": "decision-1",
        "request_fingerprint": FINGERPRINT,
        "action_id": "claims.update",
        "runtime_tool_call_id": "runtime-call-1",
        "tool_arguments_digest": ARGUMENT_DIGEST,
        "receipt_status": "SUCCEEDED",
        "reason_code": "RUNTIME_REPORTED_SUCCESS",
        "idempotency_key": "delivery-1",
        "result_reference": "artifact://claims/42/result",
        "result_digest": RESULT_DIGEST,
        "context": CONTEXT,
    }
    values.update(overrides)
    return values


def test_normal_execution_receipt_is_bound_to_allow_and_authenticated_runtime() -> None:
    service, _executions, _events, _clock = _setup()

    event = service.ingest_runtime_action_execution_receipt(**_receipt_kwargs())
    receipt = event.attributes["runtime_action_execution_receipt"]

    assert event.event_type is EventType.RUNTIME_ACTION_EXECUTION_RECEIPT
    assert event.causation_id == "decision-1"
    assert event.actor_id == CONTEXT.actor_id
    assert event.evidence_references == ("artifact://claims/42/result",)
    assert receipt["status"] == "SUCCEEDED"
    assert receipt["attested_by"] == CONTEXT.actor_id
    assert receipt["request_fingerprint"] == FINGERPRINT


def test_duplicate_receipt_is_idempotent_and_changed_submission_conflicts() -> None:
    service, _executions, events, _clock = _setup()

    original = service.ingest_runtime_action_execution_receipt(**_receipt_kwargs())
    duplicate = service.ingest_runtime_action_execution_receipt(
        **_receipt_kwargs(idempotency_key="delivery-retry")
    )

    assert duplicate.event_id == original.event_id
    assert len(events.list_by_execution("execution-1", "org-a", "project-a")) == 2
    with pytest.raises(AgentExecutionIdempotencyConflict, match="Conflicting"):
        service.ingest_runtime_action_execution_receipt(
            **_receipt_kwargs(
                receipt_status="FAILED",
                reason_code="RUNTIME_REPORTED_FAILURE",
                result_reference=None,
                result_digest=None,
            )
        )


def test_receipt_round_trips_through_sqlite_event_persistence(tmp_path) -> None:
    database_path = tmp_path / "runtime-action-receipts.sqlite"
    database = SQLiteDatabase(database_path)
    database.initialize()
    service, _executions, _events, _clock = _setup(
        execution_repository=SQLiteAgentExecutionRepository(database),
        event_repository=SQLiteAgentExecutionEventRepository(database),
    )

    recorded = service.ingest_runtime_action_execution_receipt(**_receipt_kwargs())

    # A fresh repository instance establishes that the typed receipt survives
    # the existing append-only JSON event persistence without a receipt table.
    restarted_events = SQLiteAgentExecutionEventRepository(SQLiteDatabase(database_path))
    stored = restarted_events.get_by_id(
        recorded.event_id,
        "execution-1",
        "org-a",
        "project-a",
    )

    assert stored is not None
    assert stored.attributes["runtime_action_execution_receipt"] == recorded.attributes[
        "runtime_action_execution_receipt"
    ]
    duplicate = AgentExecutionService(
        SQLiteAgentExecutionRepository(SQLiteDatabase(database_path)),
        restarted_events,
        clock=Clock(),
    ).ingest_runtime_action_execution_receipt(**_receipt_kwargs(idempotency_key="retry"))
    assert duplicate.event_id == recorded.event_id


def test_unknown_after_possible_mutation_is_reconciled_without_retry_after_expiry() -> None:
    service, executions, events, clock = _setup()
    unknown = service.ingest_runtime_action_execution_receipt(
        **_receipt_kwargs(
            receipt_status="UNKNOWN",
            reason_code="MUTATION_OUTCOME_UNKNOWN",
            result_reference=None,
            result_digest=None,
        )
    )

    # The runtime, not AIGP, resolves its own transaction state. AIGP merely
    # records the later attestation, even after the original ALLOW has expired
    # and the observed execution has completed.
    execution = executions.get("execution-1", "org-a", "project-a")
    assert execution is not None
    executions.update_status(
        "execution-1",
        "org-a",
        "project-a",
        AgentExecutionStatus.SUCCEEDED,
        NOW + timedelta(minutes=1),
        execution.version,
    )
    clock.value = NOW + timedelta(hours=1)
    reconciled = service.ingest_runtime_action_execution_receipt(
        **_receipt_kwargs(
            receipt_status="SUCCEEDED",
            supersedes_receipt_id=unknown.event_id,
            idempotency_key="reconciliation-1",
        )
    )

    assert reconciled.attributes["runtime_action_execution_receipt"][
        "supersedes_receipt_id"
    ] == unknown.event_id
    assert reconciled.received_at == clock.value
    with pytest.raises(AgentExecutionIdempotencyConflict, match="Conflicting"):
        service.ingest_runtime_action_execution_receipt(
            **_receipt_kwargs(
                receipt_status="FAILED",
                reason_code="RUNTIME_REPORTED_FAILURE",
                result_reference=None,
                result_digest=None,
                supersedes_receipt_id=unknown.event_id,
                idempotency_key="reconciliation-2",
            )
        )
    persisted = events.list_by_execution("execution-1", "org-a", "project-a")
    assert [event.event_type for event in persisted] == [
        EventType.RUNTIME_ACTION_AUTHORIZATION,
        EventType.RUNTIME_ACTION_EXECUTION_RECEIPT,
        EventType.RUNTIME_ACTION_EXECUTION_RECEIPT,
    ]


def test_receipt_rejects_cross_tenant_and_runtime_identity_forgery() -> None:
    service, _executions, _events, _clock = _setup()

    with pytest.raises(AgentExecutionNotFound):
        service.ingest_runtime_action_execution_receipt(
            **_receipt_kwargs(
                context=TenantContext("org-b", "project-a", "runtime-a", "request-b")
            )
        )
    with pytest.raises(AgentExecutionInvalidTransition, match="runtime identity"):
        service.ingest_runtime_action_execution_receipt(
            **_receipt_kwargs(
                context=TenantContext("org-a", "project-a", "runtime-forged", "request-c")
            )
        )


def test_historical_receipt_is_admissible_after_expiry_and_delegation_revocation() -> None:
    """A late receipt is evidence of an old ALLOW, never a new authorization."""

    clock = Clock()
    executions = InMemoryAgentExecutionRepository()
    events = InMemoryAgentExecutionEventRepository()
    delegations = InMemoryRuntimeActionDelegationRepository()
    policies = InMemoryPolicyAdministrationRepository()
    execution_service = AgentExecutionService(executions, events, clock=clock)
    execution = execution_service.ingest_start(
        agent_id="claims-agent",
        agent_name="Claims Agent",
        agent_version="1",
        external_execution_id="runtime-execution-1",
        runtime_provider="external-runtime",
        context=CONTEXT,
    )
    policies.save_definition(
        PolicyDefinition(
            policy_id="allow-claims",
            organization_id="org-a",
            project_id="project-a",
            name="Allow claims",
            description=None,
            category=PolicyCategory.SECURITY,
            owner="governance-admin",
            created_by="governance-admin",
            created_at=NOW,
            updated_at=NOW,
            metadata={
                RUNTIME_ACTION_AUTHORIZATION_METADATA_KEY: {
                    "purpose": RUNTIME_ACTION_AUTHORIZATION_PURPOSE,
                    "registered_actions": ["claims.update"],
                    "registered_resource_types": ["sqlite.row"],
                }
            },
        )
    )
    policies.save_version(
        PolicyVersion(
            policy_id="allow-claims",
            version="1",
            status=PolicyStatus.ACTIVE,
            target_types=(DecisionTargetType.AGENT_EXECUTION,),
            rules=(
                PolicyRule(
                    "allow-update",
                    "Allow update",
                    (
                        PolicyCondition(
                            "action.id", PolicyConditionOperator.EQUALS, "claims.update"
                        ),
                    ),
                    PolicyEffect.APPROVE,
                    "allow",
                    1,
                ),
            ),
            created_by="governance-admin",
            created_at=NOW,
            activated_at=NOW,
        )
    )
    delegation = delegations.save(
        create_runtime_action_delegation(
            delegation_id="delegation-1",
            organization_id="org-a",
            project_id="project-a",
            execution_id=execution.execution_id,
            issuer_id="issuer",
            runtime_actor_id=CONTEXT.actor_id,
            permissions=(
                RuntimeActionDelegationPermission(
                    "claims.update", "sqlite.row", ("claims:42",)
                ),
            ),
            issued_at=NOW,
            expires_at=NOW + timedelta(hours=1),
            idempotency_key="delegation-issue-1",
        )
    )
    authorization_service = RuntimeActionAuthorizationService(
        policy_repository=policies,
        execution_repository=executions,
        event_repository=events,
        delegation_repository=delegations,
        decision_ttl=timedelta(minutes=5),
        clock=clock,
    )
    authorization_request = RuntimeActionAuthorizationRequest(
        execution_id=execution.execution_id,
        action_id="claims.update",
        resource=RuntimeActionResource("sqlite.row", "claims:42"),
        idempotency_key="authorization-1",
        delegation_id=delegation.delegation_id,
        delegation_version=delegation.version,
        delegation_digest=delegation.contract_digest,
        tool_arguments_digest=ARGUMENT_DIGEST,
    )
    decision = authorization_service.authorize(authorization_request, CONTEXT)
    assert decision.outcome.value == "ALLOW"

    delegations.revoke(
        delegation.delegation_id,
        "org-a",
        "project-a",
        revoked_at=NOW + timedelta(minutes=1),
        revoked_by="issuer",
        revocation_reference="incident-1",
    )
    denied = authorization_service.authorize(
        replace(authorization_request, idempotency_key="authorization-2"),
        CONTEXT,
    )
    assert denied.outcome.value == "DENY"
    clock.value = NOW + timedelta(hours=2)
    late = execution_service.ingest_runtime_action_execution_receipt(
        execution_id=execution.execution_id,
        decision_id=decision.decision_id,
        request_fingerprint=decision.request_fingerprint,
        action_id=decision.action_id,
        runtime_tool_call_id="runtime-call-1",
        tool_arguments_digest=ARGUMENT_DIGEST,
        receipt_status="FAILED",
        reason_code="RUNTIME_REPORTED_FAILURE",
        idempotency_key="late-receipt-1",
        context=CONTEXT,
    )

    assert late.causation_id == decision.decision_id
    assert late.attributes["runtime_action_execution_receipt"]["status"] == "FAILED"
