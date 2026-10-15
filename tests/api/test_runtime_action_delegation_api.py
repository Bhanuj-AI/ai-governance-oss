"""Public transport coverage for immutable runtime-action delegations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, Header
from fastapi.testclient import TestClient

from ai_governance.api.dependencies.runtime_action_delegation import (
    get_runtime_action_delegation_service,
)
from ai_governance.api.dependencies.tenancy import get_compatible_tenant_context
from ai_governance.api.routers.runtime_action_delegation import router
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
from ai_governance.services.agent_execution_service import AgentExecutionService
from ai_governance.services.runtime_action_delegation_service import (
    RUNTIME_ACTION_DELEGATION_ISSUANCE_METADATA_KEY,
    RUNTIME_ACTION_DELEGATION_ISSUANCE_PURPOSE,
    RuntimeActionDelegationService,
)
from ai_governance.tenancy.domain import TenantContext

ISSUER = TenantContext("org-a", "project-a", "issuer-service", "issue-request")
RUNTIME = TenantContext("org-a", "project-a", "runtime-service", "runtime-request")


def _context_from_headers(
    x_ai_governance_organization_id: str = Header(...),
    x_ai_governance_project_id: str = Header(...),
) -> TenantContext:
    return TenantContext(
        x_ai_governance_organization_id,
        x_ai_governance_project_id,
        ISSUER.actor_id,
        ISSUER.request_id,
    )


def _client() -> tuple[TestClient, str]:
    executions = InMemoryAgentExecutionRepository()
    events = InMemoryAgentExecutionEventRepository()
    policies = InMemoryPolicyAdministrationRepository()
    delegations = InMemoryRuntimeActionDelegationRepository()
    now = datetime.now(UTC)
    execution_id = (
        AgentExecutionService(executions, events)
        .ingest_start(
            agent_id="agent",
            agent_name="Agent",
            agent_version="1",
            external_execution_id="run-1",
            runtime_provider="langgraph",
            context=RUNTIME,
        )
        .execution_id
    )
    definition = PolicyDefinition(
        policy_id="issuer-policy",
        organization_id="org-a",
        project_id="project-a",
        name="issuer",
        description=None,
        category=PolicyCategory.SECURITY,
        owner="owner",
        created_by="owner",
        created_at=now,
        updated_at=now,
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
                    "issue",
                    "issue",
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
                            "action.id",
                            PolicyConditionOperator.EQUALS,
                            "operations.update_status",
                        ),
                        PolicyCondition(
                            "resource.reference",
                            PolicyConditionOperator.EQUALS,
                            "operational-record:OPS-001",
                        ),
                    ),
                    PolicyEffect.APPROVE,
                    "issue",
                    10,
                ),
            ),
            created_by="owner",
            created_at=now,
            activated_at=now,
        )
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_compatible_tenant_context] = _context_from_headers
    app.dependency_overrides[get_runtime_action_delegation_service] = lambda: (
        RuntimeActionDelegationService(
            repository=delegations,
            execution_repository=executions,
            policy_repository=policies,
        )
    )
    return TestClient(app), execution_id


def _payload(execution_id: str) -> dict[str, object]:
    return {
        "execution_id": execution_id,
        "runtime_actor_id": RUNTIME.actor_id,
        "permissions": [
            {
                "action_id": "operations.update_status",
                "resource_type": "sqlite.row",
                "resource_references": ["operational-record:OPS-001"],
            }
        ],
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "idempotency_key": "issue-1",
    }


def test_issue_and_revoke_delegation_without_caller_issuer_claim() -> None:
    client, execution_id = _client()
    payload = _payload(execution_id)
    payload["issuer_id"] = "forged-issuer"
    headers = {
        "X-AI-Governance-Organization-Id": "org-a",
        "X-AI-Governance-Project-Id": "project-a",
    }

    assert (
        client.post(
            "/api/v1/runtime-action-delegations", json=payload, headers=headers
        ).status_code
        == 422
    )
    del payload["issuer_id"]
    issued = client.post(
        "/api/v1/runtime-action-delegations", json=payload, headers=headers
    )
    assert issued.status_code == 201
    body = issued.json()
    assert body["issuer_id"] == ISSUER.actor_id
    assert body["runtime_actor_id"] == RUNTIME.actor_id
    revoked = client.post(
        f"/api/v1/runtime-action-delegations/{body['delegation_id']}/revoke",
        json={"revocation_reference": "incident-1"},
        headers=headers,
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "REVOKED"
