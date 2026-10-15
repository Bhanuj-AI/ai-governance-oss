"""Trust-boundary regressions for runtime action authorization."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from uuid import uuid4

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
from ai_governance.repositories.sqlite.sqlite_runtime_action_delegation_repository import (
    SQLiteRuntimeActionDelegationRepository,
)
from ai_governance.runtime_authorization import (
    LangGraphOperationAuthorizer,
    ProtectedOperationBlocked,
    RuntimeActionAuthorizationOutcome,
    RuntimeActionAuthorizationRequest,
    RuntimeActionDelegationPermission,
    RuntimeActionResource,
    canonical_tool_arguments_digest,
)
from ai_governance.runtime_authorization.delegation import (
    create_runtime_action_delegation,
)
from ai_governance.services.agent_execution_service import AgentExecutionService
from ai_governance.services.runtime_action_authorization_service import (
    RUNTIME_ACTION_AUTHORIZATION_METADATA_KEY,
    RUNTIME_ACTION_AUTHORIZATION_PURPOSE,
    RuntimeActionAuthorizationNotFoundError,
    RuntimeActionAuthorizationService,
)
from ai_governance.tenancy.domain import TenantContext

NOW = datetime(2026, 10, 15, 9, 0, tzinfo=UTC)
CONTEXT = TenantContext("org-a", "project-a", "runtime-agent", "request-a")
ARGUMENTS = {"record_id": "42", "status": "APPROVED"}


class Clock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def _policy_rule(effect: PolicyEffect, *, agent_context: bool = False) -> PolicyRule:
    conditions = [
        PolicyCondition("action.id", PolicyConditionOperator.EQUALS, "claims.update"),
        PolicyCondition("resource.type", PolicyConditionOperator.EQUALS, "sqlite.row"),
    ]
    if agent_context:
        conditions.append(
            PolicyCondition(
                "agent_context.claimed_authority",
                PolicyConditionOperator.EQUALS,
                "maintenance",
            )
        )
    return PolicyRule(
        rule_id=f"{effect.value.lower()}-claim-update",
        name=f"{effect.value.title()} claim update",
        conditions=tuple(conditions),
        effect=effect,
        reason_template=f"{effect.value} claim mutation.",
        priority=10,
    )


def _add_active_policy(
    repository: InMemoryPolicyAdministrationRepository,
    *,
    policy_id: str,
    effect: PolicyEffect,
    agent_context: bool = False,
) -> None:
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
    repository.save_version(
        PolicyVersion(
            policy_id=policy_id,
            version="1",
            status=PolicyStatus.ACTIVE,
            target_types=(DecisionTargetType.AGENT_EXECUTION,),
            rules=(_policy_rule(effect, agent_context=agent_context),),
            created_by="governance-admin",
            created_at=NOW,
            activated_at=NOW,
        )
    )


def _service(
    *, clock: Clock | None = None, executions=None, events=None, delegations=None
):
    policy_repository = InMemoryPolicyAdministrationRepository()
    executions = executions or InMemoryAgentExecutionRepository()
    events = events or InMemoryAgentExecutionEventRepository()
    delegations = delegations or InMemoryRuntimeActionDelegationRepository()
    return (
        RuntimeActionAuthorizationService(
            policy_repository=policy_repository,
            execution_repository=executions,
            event_repository=events,
            delegation_repository=delegations,
            clock=clock or Clock(),
        ),
        policy_repository,
        executions,
        events,
        delegations,
    )


def _start_execution(executions, events, *, context: TenantContext = CONTEXT) -> str:
    return (
        AgentExecutionService(executions, events)
        .ingest_start(
            agent_id="claims-agent",
            agent_name="Claims Agent",
            agent_version="1.0",
            external_execution_id=f"langgraph-run-{uuid4()}",
            runtime_provider="langgraph",
            correlation_id="correlation-1",
            context=context,
        )
        .execution_id
    )


def _delegate(
    repository,
    execution_id: str,
    *,
    action_id: str = "claims.update",
    reference: str = "claims:42",
    actor_id: str = CONTEXT.actor_id,
    expires_at: datetime = NOW + timedelta(hours=1),
    context: TenantContext = CONTEXT,
):
    return repository.save(
        create_runtime_action_delegation(
            delegation_id=f"delegation-{execution_id}",
            organization_id=context.organization_id,
            project_id=context.project_id,
            execution_id=execution_id,
            issuer_id="trusted-issuer",
            runtime_actor_id=actor_id,
            permissions=(
                RuntimeActionDelegationPermission(
                    action_id=action_id,
                    resource_type="sqlite.row",
                    resource_references=(reference,),
                ),
            ),
            issued_at=NOW,
            expires_at=expires_at,
            idempotency_key=f"issue-{execution_id}",
        )
    )


def _request(
    execution_id: str,
    delegation=None,
    *,
    idempotency_key: str = "claim-update-1",
    action_id: str = "claims.update",
    reference: str = "claims:42",
    context: dict[str, str] | None = None,
    policy_id: str | None = None,
) -> RuntimeActionAuthorizationRequest:
    return RuntimeActionAuthorizationRequest(
        execution_id=execution_id,
        action_id=action_id,
        resource=RuntimeActionResource("sqlite.row", reference),
        idempotency_key=idempotency_key,
        delegation_id=delegation.delegation_id if delegation else None,
        delegation_version=delegation.version if delegation else None,
        delegation_digest=delegation.contract_digest if delegation else None,
        tool_arguments_digest=canonical_tool_arguments_digest(ARGUMENTS),
        context=context or {},
        policy_id=policy_id,
    )


def test_valid_delegation_is_bound_to_operation_and_persisted() -> None:
    service, policies, executions, events, delegations = _service()
    _add_active_policy(policies, policy_id="allow-claims", effect=PolicyEffect.APPROVE)
    execution_id = _start_execution(executions, events)
    delegation = _delegate(delegations, execution_id)
    decision = service.authorize(_request(execution_id, delegation), CONTEXT)

    assert decision.outcome is RuntimeActionAuthorizationOutcome.ALLOW
    assert decision.delegation_digest == delegation.contract_digest
    assert decision.evaluated_policies == (("allow-claims", "1"),)
    event = events.list_by_execution(execution_id, "org-a", "project-a")[-1]
    assert event.attributes["delegation_id"] == delegation.delegation_id
    assert event.attributes["tool_arguments_digest"] == decision.tool_arguments_digest


def test_agent_controlled_purpose_cannot_broaden_a_read_only_delegation() -> None:
    """Required adversarial case: only the claimed purpose changes."""
    service, policies, executions, events, delegations = _service()
    _add_active_policy(policies, policy_id="allow-updates", effect=PolicyEffect.APPROVE)
    execution_id = _start_execution(executions, events)
    read_only = _delegate(delegations, execution_id, action_id="claims.read")
    legitimate = service.authorize(
        _request(
            execution_id,
            read_only,
            context={"claimed_authority": "read-only"},
            idempotency_key="read-only-description",
        ),
        CONTEXT,
    )
    forged = service.authorize(
        _request(
            execution_id,
            read_only,
            context={"claimed_authority": "maintenance"},
            idempotency_key="forged-maintenance-description",
        ),
        CONTEXT,
    )

    assert legitimate.reason_code == forged.reason_code == "DELEGATION_SCOPE_DENIED"
    assert forged.outcome is RuntimeActionAuthorizationOutcome.DENY


def test_context_only_allow_and_policy_selector_are_denied() -> None:
    service, policies, executions, events, delegations = _service()
    _add_active_policy(
        policies,
        policy_id="unsafe-context-allow",
        effect=PolicyEffect.APPROVE,
        agent_context=True,
    )
    _add_active_policy(policies, policy_id="safe-allow", effect=PolicyEffect.APPROVE)
    execution_id = _start_execution(executions, events)
    delegation = _delegate(delegations, execution_id)

    unsafe = service.authorize(
        _request(
            execution_id,
            delegation,
            context={"claimed_authority": "maintenance"},
        ),
        CONTEXT,
    )
    selected = service.authorize(
        _request(
            execution_id,
            delegation,
            idempotency_key="policy-selector",
            policy_id="safe-allow",
        ),
        CONTEXT,
    )

    assert unsafe.reason_code == "UNSUPPORTED_AUTHORIZATION_POLICY_EFFECT"
    assert selected.reason_code == "POLICY_SELECTION_NOT_ALLOWED"


def test_all_applicable_denies_override_allow_and_missing_grant_denies() -> None:
    service, policies, executions, events, delegations = _service()
    _add_active_policy(policies, policy_id="allow-claims", effect=PolicyEffect.APPROVE)
    _add_active_policy(policies, policy_id="block-claims", effect=PolicyEffect.BLOCK)
    execution_id = _start_execution(executions, events)
    delegation = _delegate(delegations, execution_id)
    denied = service.authorize(_request(execution_id, delegation), CONTEXT)
    missing = service.authorize(
        _request(execution_id, idempotency_key="missing-delegation"), CONTEXT
    )

    assert denied.reason_code == "DENY_OVERRIDES"
    assert denied.evaluated_policies == (("allow-claims", "1"), ("block-claims", "1"))
    assert missing.reason_code == "MISSING_DELEGATION"


def test_delegation_scope_expiry_revocation_and_cross_tenant_are_enforced() -> None:
    clock = Clock()
    service, policies, executions, events, delegations = _service(clock=clock)
    _add_active_policy(policies, policy_id="allow-claims", effect=PolicyEffect.APPROVE)
    execution_id = _start_execution(executions, events)
    other_execution = _start_execution(executions, events)
    delegation = _delegate(delegations, execution_id)

    assert (
        service.authorize(
            _request(other_execution, delegation, idempotency_key="other-execution"),
            CONTEXT,
        ).reason_code
        == "DELEGATION_SCOPE_DENIED"
    )
    assert (
        service.authorize(
            _request(
                execution_id,
                delegation,
                reference="claims:99",
                idempotency_key="other-resource",
            ),
            CONTEXT,
        ).reason_code
        == "DELEGATION_SCOPE_DENIED"
    )
    assert (
        service.authorize(
            _request(execution_id, delegation, idempotency_key="other-actor"),
            TenantContext("org-a", "project-a", "other-runtime", "request-b"),
        ).reason_code
        == "DELEGATION_SCOPE_DENIED"
    )
    delegations.revoke(
        delegation.delegation_id,
        "org-a",
        "project-a",
        revoked_at=NOW,
        revoked_by="trusted-issuer",
        revocation_reference="incident-1",
    )
    assert (
        service.authorize(
            _request(execution_id, delegation, idempotency_key="revoked"), CONTEXT
        ).reason_code
        == "DELEGATION_REVOKED"
    )

    expired = _delegate(
        delegations, other_execution, expires_at=NOW + timedelta(minutes=1)
    )
    clock.value += timedelta(minutes=2)
    assert (
        service.authorize(
            _request(other_execution, expired, idempotency_key="expired"), CONTEXT
        ).reason_code
        == "DELEGATION_EXPIRED"
    )
    with pytest.raises(RuntimeActionAuthorizationNotFoundError):
        service.authorize(
            _request(execution_id, delegation),
            TenantContext("org-b", "project-a", "runtime-agent", "request-b"),
        )


def test_unavailable_delegation_or_policy_resolution_persists_a_deny(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, policies, executions, events, delegations = _service()
    _add_active_policy(policies, policy_id="allow-claims", effect=PolicyEffect.APPROVE)
    execution_id = _start_execution(executions, events)
    delegation = _delegate(delegations, execution_id)
    monkeypatch.setattr(
        delegations,
        "get",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("delegation store down")),
    )
    assert (
        service.authorize(_request(execution_id, delegation), CONTEXT).reason_code
        == "DELEGATION_RESOLUTION_UNAVAILABLE"
    )

    service, policies, executions, events, delegations = _service()
    _add_active_policy(policies, policy_id="allow-claims", effect=PolicyEffect.APPROVE)
    execution_id = _start_execution(executions, events)
    delegation = _delegate(delegations, execution_id)
    monkeypatch.setattr(
        policies,
        "list_definitions",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("policy store down")),
    )
    assert (
        service.authorize(_request(execution_id, delegation), CONTEXT).reason_code
        == "POLICY_EVALUATION_FAILED"
    )


def test_pep_rejects_tool_argument_mutation_and_unavailable_pdp(tmp_path) -> None:
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
    delegation_repository = SQLiteRuntimeActionDelegationRepository(database)
    service, policies, _, _, _ = _service(
        clock=clock,
        executions=executions,
        events=events,
        delegations=delegation_repository,
    )
    _add_active_policy(policies, policy_id="allow-claims", effect=PolicyEffect.APPROVE)
    execution_id = _start_execution(executions, events)
    delegation = _delegate(delegation_repository, execution_id)
    request = _request(execution_id, delegation)

    class Client:
        def authorize(self, item):
            return service.authorize(item, CONTEXT)

    authorizer = LangGraphOperationAuthorizer(
        Client(), actor_id=CONTEXT.actor_id, clock=clock
    )
    with pytest.raises(ProtectedOperationBlocked, match="TOOL_ARGUMENTS_MISMATCH"):
        authorizer.require_allow(
            request,
            actual_tool_arguments_digest=canonical_tool_arguments_digest(
                {"record_id": "42", "status": "REJECTED"}
            ),
        )
    with database.connect() as connection:
        assert (
            connection.execute(
                "SELECT state FROM protected_claim WHERE claim_id='42'"
            ).fetchone()[0]
            == "PENDING"
        )

    authorizer.require_allow(
        request, actual_tool_arguments_digest=request.tool_arguments_digest
    )
    with database.connect() as connection:
        connection.execute(
            "UPDATE protected_claim SET state='APPROVED' WHERE claim_id='42'"
        )
        connection.commit()
        assert (
            connection.execute(
                "SELECT state FROM protected_claim WHERE claim_id='42'"
            ).fetchone()[0]
            == "APPROVED"
        )

    class Unavailable:
        def authorize(self, item):
            raise sqlite3.OperationalError("unavailable")

    with pytest.raises(ProtectedOperationBlocked, match="AUTHORIZATION_UNAVAILABLE"):
        LangGraphOperationAuthorizer(
            Unavailable(), actor_id=CONTEXT.actor_id
        ).require_allow(
            request, actual_tool_arguments_digest=request.tool_arguments_digest
        )
