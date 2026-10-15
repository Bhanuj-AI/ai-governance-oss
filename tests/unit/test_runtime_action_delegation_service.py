"""Issuer authorization and immutable delegation registration regressions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

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
from ai_governance.runtime_authorization import RuntimeActionDelegationPermission
from ai_governance.services.agent_execution_service import AgentExecutionService
from ai_governance.services.runtime_action_delegation_service import (
    RUNTIME_ACTION_DELEGATION_ISSUANCE_METADATA_KEY,
    RUNTIME_ACTION_DELEGATION_ISSUANCE_PURPOSE,
    RuntimeActionDelegationConflictError,
    RuntimeActionDelegationDeniedError,
    RuntimeActionDelegationRegistration,
    RuntimeActionDelegationService,
)
from ai_governance.tenancy.domain import TenantContext

NOW = datetime(2026, 10, 15, 9, 0, tzinfo=UTC)
ISSUER = TenantContext("org-a", "project-a", "trusted-issuer", "issue-1")
RUNTIME = TenantContext("org-a", "project-a", "runtime-agent", "runtime-1")


class Clock:
    def __init__(self) -> None:
        self.value = NOW

    def __call__(self) -> datetime:
        return self.value


def _service():
    executions = InMemoryAgentExecutionRepository()
    events = InMemoryAgentExecutionEventRepository()
    policies = InMemoryPolicyAdministrationRepository()
    repository = InMemoryRuntimeActionDelegationRepository()
    clock = Clock()
    execution_id = (
        AgentExecutionService(executions, events)
        .ingest_start(
            agent_id="agent",
            agent_name="Agent",
            agent_version="1",
            external_execution_id="external-1",
            runtime_provider="langgraph",
            context=RUNTIME,
        )
        .execution_id
    )
    definition = PolicyDefinition(
        policy_id="issuer-policy",
        organization_id="org-a",
        project_id="project-a",
        name="Issuer policy",
        description=None,
        category=PolicyCategory.SECURITY,
        owner="owner",
        created_by="owner",
        created_at=NOW,
        updated_at=NOW,
        metadata={
            RUNTIME_ACTION_DELEGATION_ISSUANCE_METADATA_KEY: {
                "purpose": RUNTIME_ACTION_DELEGATION_ISSUANCE_PURPOSE
            }
        },
    )
    policies.save_definition(definition)
    policies.save_version(
        PolicyVersion(
            policy_id="issuer-policy",
            version="1",
            status=PolicyStatus.ACTIVE,
            target_types=(DecisionTargetType.AGENT_EXECUTION,),
            rules=(
                PolicyRule(
                    "allow-issuer",
                    "Allow issuer",
                    (
                        PolicyCondition(
                            "issuer.id", PolicyConditionOperator.EQUALS, ISSUER.actor_id
                        ),
                        PolicyCondition(
                            "runtime_actor.id",
                            PolicyConditionOperator.EQUALS,
                            RUNTIME.actor_id,
                        ),
                        PolicyCondition(
                            "action.id", PolicyConditionOperator.EQUALS, "claims.update"
                        ),
                        PolicyCondition(
                            "resource.reference",
                            PolicyConditionOperator.EQUALS,
                            "claims:42",
                        ),
                    ),
                    PolicyEffect.APPROVE,
                    "allow",
                    10,
                ),
            ),
            created_by="owner",
            created_at=NOW,
            activated_at=NOW,
        )
    )
    return (
        RuntimeActionDelegationService(
            repository=repository,
            execution_repository=executions,
            policy_repository=policies,
            clock=clock,
        ),
        execution_id,
        clock,
    )


def _registration(
    execution_id: str,
    *,
    reference: str = "claims:42",
    idempotency_key: str = "delegate-1",
) -> RuntimeActionDelegationRegistration:
    return RuntimeActionDelegationRegistration(
        execution_id=execution_id,
        runtime_actor_id=RUNTIME.actor_id,
        permissions=(
            RuntimeActionDelegationPermission(
                "claims.update", "sqlite.row", (reference,)
            ),
        ),
        expires_at=NOW + timedelta(hours=1),
        idempotency_key=idempotency_key,
    )


def test_only_policy_authorized_identity_can_issue_and_repeat_is_idempotent() -> None:
    service, execution_id, clock = _service()
    first = service.register(_registration(execution_id), ISSUER)
    clock.value += timedelta(minutes=1)

    assert service.register(_registration(execution_id), ISSUER) == first
    with pytest.raises(RuntimeActionDelegationDeniedError):
        service.register(
            _registration(execution_id, idempotency_key="runtime-issue"), RUNTIME
        )
    with pytest.raises(RuntimeActionDelegationDeniedError):
        service.register(
            RuntimeActionDelegationRegistration(
                execution_id=execution_id,
                runtime_actor_id=RUNTIME.actor_id,
                permissions=(
                    RuntimeActionDelegationPermission(
                        "claims.update", "sqlite.row", ("claims:42", "claims:43")
                    ),
                ),
                expires_at=NOW + timedelta(hours=1),
                idempotency_key="overbroad-issue",
            ),
            ISSUER,
        )
    with pytest.raises(RuntimeActionDelegationConflictError):
        service.register(_registration(execution_id, reference="claims:43"), ISSUER)
