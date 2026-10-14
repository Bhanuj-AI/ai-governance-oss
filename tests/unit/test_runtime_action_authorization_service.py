"""Runtime action authorization service and fail-closed integration coverage."""

from __future__ import annotations

import sqlite3
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
from ai_governance.domain.agent_execution import EventType, ToolCallContext
from ai_governance.domain.agent_execution.agent_execution_event import ActorType
from ai_governance.repositories.in_memory.in_memory_agent_execution_repository import (
    InMemoryAgentExecutionEventRepository,
    InMemoryAgentExecutionRepository,
)
from ai_governance.repositories.in_memory_policy_administration_repository import (
    InMemoryPolicyAdministrationRepository,
)
from ai_governance.repositories.sqlite.sqlite_agent_execution_repository import (
    SQLiteAgentExecutionEventRepository,
    SQLiteAgentExecutionRepository,
)
from ai_governance.runtime_authorization import (
    LangGraphOperationAuthorizer,
    ProtectedOperationBlocked,
    RuntimeActionAuthorizationOutcome,
    RuntimeActionAuthorizationRequest,
    RuntimeActionResource,
)
from ai_governance.services.agent_execution_service import AgentExecutionService
from ai_governance.services.runtime_action_authorization_service import (
    RUNTIME_ACTION_AUTHORIZATION_METADATA_KEY,
    RUNTIME_ACTION_AUTHORIZATION_PURPOSE,
    RuntimeActionAuthorizationConflictError,
    RuntimeActionAuthorizationNotFoundError,
    RuntimeActionAuthorizationService,
)
from ai_governance.tenancy.domain import TenantContext

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
CONTEXT = TenantContext("org-a", "project-a", "runtime-agent", "request-a")


class Clock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def _policy_rule(effect: PolicyEffect, *, risk: str = "low") -> PolicyRule:
    return PolicyRule(
        rule_id=f"{effect.value.lower()}-claim-update",
        name=f"{effect.value.title()} claim update",
        conditions=(
            PolicyCondition(
                field_path="action.id",
                operator=PolicyConditionOperator.EQUALS,
                expected_value="claims.update",
            ),
            PolicyCondition(
                field_path="resource.type",
                operator=PolicyConditionOperator.EQUALS,
                expected_value="sqlite.row",
            ),
            PolicyCondition(
                field_path="context.risk",
                operator=PolicyConditionOperator.EQUALS,
                expected_value=risk,
            ),
        ),
        effect=effect,
        reason_template=f"{effect.value} claim mutation.",
        priority=10,
    )


def _add_active_policy(
    repository: InMemoryPolicyAdministrationRepository,
    *,
    policy_id: str,
    effect: PolicyEffect,
    risk: str = "low",
    version: str = "1",
) -> PolicyVersion:
    definition = PolicyDefinition(
        policy_id=policy_id,
        organization_id=CONTEXT.organization_id,
        project_id=CONTEXT.project_id,
        name=policy_id,
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
    repository.save_definition(definition)
    policy_version = PolicyVersion(
        policy_id=policy_id,
        version=version,
        status=PolicyStatus.ACTIVE,
        target_types=(DecisionTargetType.AGENT_EXECUTION,),
        rules=(_policy_rule(effect, risk=risk),),
        created_by="governance-admin",
        created_at=NOW,
        activated_at=NOW,
    )
    repository.save_version(policy_version)
    return policy_version


def _request(
    execution_id: str,
    *,
    idempotency_key: str = "claim-update-1",
    risk: str = "low",
    action_id: str = "claims.update",
    resource_reference: str = "claims:42",
    policy_id: str | None = None,
    expected_policy_version: str | None = None,
) -> RuntimeActionAuthorizationRequest:
    return RuntimeActionAuthorizationRequest(
        execution_id=execution_id,
        action_id=action_id,
        resource=RuntimeActionResource("sqlite.row", resource_reference),
        context={"risk": risk},
        idempotency_key=idempotency_key,
        policy_id=policy_id,
        expected_policy_version=expected_policy_version,
    )


def _service(
    *,
    clock: Clock | None = None,
    execution_repository=None,
    event_repository=None,
) -> tuple[
    RuntimeActionAuthorizationService,
    InMemoryPolicyAdministrationRepository,
    object,
    object,
]:
    policy_repository = InMemoryPolicyAdministrationRepository()
    executions = execution_repository or InMemoryAgentExecutionRepository()
    events = event_repository or InMemoryAgentExecutionEventRepository()
    return (
        RuntimeActionAuthorizationService(
            policy_repository=policy_repository,
            execution_repository=executions,
            event_repository=events,
            clock=clock or Clock(),
        ),
        policy_repository,
        executions,
        events,
    )


def _start_execution(executions, events) -> str:
    service = AgentExecutionService(executions, events)
    return service.ingest_start(
        agent_id="claims-agent",
        agent_name="Claims Agent",
        agent_version="1.0",
        external_execution_id="langgraph-run-1",
        runtime_provider="langgraph",
        correlation_id="correlation-1",
        context=CONTEXT,
    ).execution_id


def test_persists_operation_bound_allow_and_replays_identically() -> None:
    service, policies, executions, events = _service()
    _add_active_policy(policies, policy_id="allow-claims", effect=PolicyEffect.APPROVE)
    execution_id = _start_execution(executions, events)
    request = _request(execution_id)

    first = service.authorize(request, CONTEXT)
    second = service.authorize(request, CONTEXT)

    assert first.outcome is RuntimeActionAuthorizationOutcome.ALLOW
    assert first.reason_code == "ALLOW_POLICY_MATCHED"
    assert first.policy_id == "allow-claims"
    assert second == first
    assert not first.is_valid_for(
        _request(execution_id, risk="high"),
        actor_id=CONTEXT.actor_id,
        now=NOW,
    )
    assert not first.is_valid_for(
        _request(execution_id, action_id="claims.delete"),
        actor_id=CONTEXT.actor_id,
        now=NOW,
    )
    assert not first.is_valid_for(
        _request(execution_id, resource_reference="claims:43"),
        actor_id=CONTEXT.actor_id,
        now=NOW,
    )
    assert not first.is_valid_for(
        request,
        actor_id="different-runtime-actor",
        now=NOW,
    )
    recorded = events.list_by_execution(
        execution_id, CONTEXT.organization_id, CONTEXT.project_id
    )
    assert recorded[-1].event_type is EventType.RUNTIME_ACTION_AUTHORIZATION
    assert recorded[-1].attributes["context_digest"] == request.context_digest()
    assert "risk" not in recorded[-1].attributes


def test_deny_overrides_conflicting_allow_policy() -> None:
    service, policies, executions, events = _service()
    _add_active_policy(policies, policy_id="allow-claims", effect=PolicyEffect.APPROVE)
    _add_active_policy(policies, policy_id="deny-claims", effect=PolicyEffect.BLOCK)
    execution_id = _start_execution(executions, events)

    decision = service.authorize(_request(execution_id), CONTEXT)

    assert decision.outcome is RuntimeActionAuthorizationOutcome.DENY
    assert decision.reason_code == "DENY_OVERRIDES"
    assert decision.policy_id == "deny-claims"


def test_no_matching_rule_denies_and_idempotency_conflicts_are_rejected() -> None:
    service, policies, executions, events = _service()
    _add_active_policy(
        policies, policy_id="allow-low-risk", effect=PolicyEffect.APPROVE
    )
    execution_id = _start_execution(executions, events)
    denied_request = _request(execution_id, risk="high")

    denied = service.authorize(denied_request, CONTEXT)

    assert denied.outcome is RuntimeActionAuthorizationOutcome.DENY
    assert denied.reason_code == "NO_APPLICABLE_POLICY"
    assert service.authorize(denied_request, CONTEXT) == denied
    with pytest.raises(RuntimeActionAuthorizationConflictError):
        service.authorize(
            _request(
                execution_id,
                risk="low",
                resource_reference="claims:43",
            ),
            CONTEXT,
        )


def test_unsupported_action_or_resource_is_an_explicit_deny() -> None:
    service, policies, executions, events = _service()
    _add_active_policy(policies, policy_id="allow-claims", effect=PolicyEffect.APPROVE)
    execution_id = _start_execution(executions, events)

    unsupported_action = service.authorize(
        _request(
            execution_id,
            idempotency_key="unsupported-action",
            action_id="claims.delete",
        ),
        CONTEXT,
    )
    unsupported_resource = service.authorize(
        RuntimeActionAuthorizationRequest(
            execution_id=execution_id,
            action_id="claims.update",
            resource=RuntimeActionResource("object.store", "claims:42"),
            context={"risk": "low"},
            idempotency_key="unsupported-resource",
        ),
        CONTEXT,
    )

    assert unsupported_action.reason_code == "UNSUPPORTED_ACTION"
    assert unsupported_resource.reason_code == "UNSUPPORTED_RESOURCE"


def test_cross_tenant_execution_and_stale_policy_version_fail_closed() -> None:
    service, policies, executions, events = _service()
    initial = _add_active_policy(
        policies, policy_id="claims-policy", effect=PolicyEffect.APPROVE
    )
    execution_id = _start_execution(executions, events)
    foreign = TenantContext("org-b", "project-a", "runtime-agent", "request-b")

    with pytest.raises(RuntimeActionAuthorizationNotFoundError):
        service.authorize(_request(execution_id), foreign)

    policies.save_version(
        replace(
            initial,
            version="2",
            status=PolicyStatus.ACTIVE,
            rules=(_policy_rule(PolicyEffect.BLOCK),),
            activated_at=NOW + timedelta(minutes=1),
        )
    )
    stale = service.authorize(
        _request(
            execution_id,
            idempotency_key="claim-update-stale",
            policy_id="claims-policy",
            expected_policy_version="1",
        ),
        CONTEXT,
    )
    assert stale.outcome is RuntimeActionAuthorizationOutcome.DENY
    assert stale.reason_code == "POLICY_VERSION_MISMATCH"


def test_expired_or_unavailable_authorization_cannot_reach_sqlite_mutation(
    tmp_path,
) -> None:
    database = SQLiteDatabase(tmp_path / "runtime-authorization.sqlite")
    database.initialize()
    with database.connect() as connection:
        connection.execute(
            "CREATE TABLE protected_claim (claim_id TEXT PRIMARY KEY, state TEXT)"
        )
        connection.execute("INSERT INTO protected_claim VALUES ('42', 'PENDING')")
        connection.commit()

    clock = Clock()
    executions = SQLiteAgentExecutionRepository(database)
    events = SQLiteAgentExecutionEventRepository(database)
    service, policies, _, _ = _service(
        clock=clock,
        execution_repository=executions,
        event_repository=events,
    )
    _add_active_policy(policies, policy_id="allow-claims", effect=PolicyEffect.APPROVE)
    execution_id = _start_execution(executions, events)
    request = _request(execution_id)

    class ServiceClient:
        def authorize(self, item: RuntimeActionAuthorizationRequest):
            return service.authorize(item, CONTEXT)

    authorizer = LangGraphOperationAuthorizer(
        ServiceClient(), actor_id=CONTEXT.actor_id, clock=clock
    )
    evidence_service = AgentExecutionService(executions, events, clock=clock)

    def update_claim(item: RuntimeActionAuthorizationRequest) -> None:
        decision = authorizer.require_allow(item)
        with database.connect() as connection:
            connection.execute(
                "UPDATE protected_claim SET state = 'APPROVED' WHERE claim_id = '42'"
            )
            connection.commit()
        evidence_service.ingest_event(
            execution_id=execution_id,
            event_type=EventType.TOOL_CALL,
            attributes={"tool": "claims.update"},
            context=CONTEXT,
            idempotency_key="claims-update-tool-evidence",
            causation_id=decision.decision_id,
            actor_id="claims.update",
            actor_type=ActorType.TOOL,
            tool_call_context=ToolCallContext(
                schema_version="1",
                runtime_tool_call_id="claims-update-42",
                tool_call_group_id="claims-mutation",
            ),
        )

    update_claim(request)
    with database.connect() as connection:
        assert (
            connection.execute(
                "SELECT state FROM protected_claim WHERE claim_id = '42'"
            ).fetchone()[0]
            == "APPROVED"
        )
    recorded = events.list_by_execution(execution_id, "org-a", "project-a")
    assert recorded[-1].event_type is EventType.TOOL_CALL
    assert recorded[-1].causation_id == recorded[-2].event_id

    with database.connect() as connection:
        connection.execute(
            "UPDATE protected_claim SET state = 'PENDING' WHERE claim_id = '42'"
        )
        connection.commit()
    clock.value += timedelta(minutes=6)
    with pytest.raises(
        ProtectedOperationBlocked, match="INVALID_AUTHORIZATION_DECISION"
    ):
        update_claim(request)
    with database.connect() as connection:
        assert (
            connection.execute(
                "SELECT state FROM protected_claim WHERE claim_id = '42'"
            ).fetchone()[0]
            == "PENDING"
        )

    active = policies.get_active_version("allow-claims")
    assert active is not None
    policies.save_version(
        replace(
            active,
            version="2",
            status=PolicyStatus.ACTIVE,
            rules=(_policy_rule(PolicyEffect.BLOCK),),
            activated_at=clock.value,
        )
    )
    with pytest.raises(ProtectedOperationBlocked, match="DENY_POLICY_MATCHED"):
        update_claim(_request(execution_id, idempotency_key="claim-update-blocked"))
    with database.connect() as connection:
        assert (
            connection.execute(
                "SELECT state FROM protected_claim WHERE claim_id = '42'"
            ).fetchone()[0]
            == "PENDING"
        )

    class UnavailableClient:
        def authorize(self, item: RuntimeActionAuthorizationRequest):
            raise sqlite3.OperationalError("authorization service unavailable")

    unavailable = LangGraphOperationAuthorizer(
        UnavailableClient(), actor_id=CONTEXT.actor_id, clock=clock
    )
    with pytest.raises(ProtectedOperationBlocked, match="AUTHORIZATION_UNAVAILABLE"):
        unavailable.require_allow(
            _request(execution_id, idempotency_key="claim-update-unavailable")
        )

    class MalformedClient:
        def authorize(self, item: RuntimeActionAuthorizationRequest):
            return object()

    malformed = LangGraphOperationAuthorizer(
        MalformedClient(), actor_id=CONTEXT.actor_id, clock=clock
    )
    with pytest.raises(
        ProtectedOperationBlocked, match="MALFORMED_AUTHORIZATION_RESPONSE"
    ):
        malformed.require_allow(
            _request(execution_id, idempotency_key="claim-update-malformed")
        )
