"""Public contract tests for trust-bound runtime action authorization."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, Header
from fastapi.testclient import TestClient

from ai_governance.api.dependencies.runtime_action_authorization import (
    get_runtime_action_authorization_service,
)
from ai_governance.api.dependencies.tenancy import get_compatible_tenant_context
from ai_governance.api.routers.runtime_action_authorization import router
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
from ai_governance.runtime_authorization import (
    RuntimeActionDelegationPermission,
    canonical_tool_arguments_digest,
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

CONTEXT = TenantContext("org-a", "project-a", "server-derived-actor", "request-a")
ARGUMENT_DIGEST = canonical_tool_arguments_digest(
    {"record_id": "42", "status": "APPROVED"}
)


def _context_from_headers(
    x_ai_governance_organization_id: str = Header(...),
    x_ai_governance_project_id: str = Header(...),
) -> TenantContext:
    return TenantContext(
        x_ai_governance_organization_id,
        x_ai_governance_project_id,
        CONTEXT.actor_id,
        CONTEXT.request_id,
    )


def _client() -> tuple[TestClient, str, object, InMemoryAgentExecutionEventRepository]:
    policies = InMemoryPolicyAdministrationRepository()
    executions = InMemoryAgentExecutionRepository()
    events = InMemoryAgentExecutionEventRepository()
    delegations = InMemoryRuntimeActionDelegationRepository()
    now = datetime.now(UTC)
    definition = PolicyDefinition(
        policy_id="claim-policy",
        organization_id="org-a",
        project_id="project-a",
        name="Claim policy",
        description=None,
        category=PolicyCategory.SECURITY,
        owner="owner",
        created_by="owner",
        created_at=now,
        updated_at=now,
        metadata={
            RUNTIME_ACTION_AUTHORIZATION_METADATA_KEY: {
                "purpose": RUNTIME_ACTION_AUTHORIZATION_PURPOSE,
                "registered_actions": ["claims.update"],
                "registered_resource_types": ["sqlite.row"],
            }
        },
    )
    policies.save_definition(definition)
    policies.save_version(
        PolicyVersion(
            policy_id="claim-policy",
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
                    10,
                ),
            ),
            created_by="owner",
            created_at=now,
            activated_at=now,
        )
    )
    execution_id = (
        AgentExecutionService(executions, events)
        .ingest_start(
            agent_id="claims-agent",
            agent_name="Claims Agent",
            agent_version="1.0",
            external_execution_id="langgraph-run-1",
            runtime_provider="langgraph",
            context=CONTEXT,
        )
        .execution_id
    )
    delegation = delegations.save(
        create_runtime_action_delegation(
            delegation_id="delegation-1",
            organization_id="org-a",
            project_id="project-a",
            execution_id=execution_id,
            issuer_id="issuer",
            runtime_actor_id=CONTEXT.actor_id,
            permissions=(
                RuntimeActionDelegationPermission(
                    "claims.update", "sqlite.row", ("claims:42",)
                ),
            ),
            issued_at=now,
            expires_at=now + timedelta(hours=1),
            idempotency_key="issue-1",
        )
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_compatible_tenant_context] = _context_from_headers
    app.dependency_overrides[get_runtime_action_authorization_service] = lambda: (
        RuntimeActionAuthorizationService(
            policy_repository=policies,
            execution_repository=executions,
            event_repository=events,
            delegation_repository=delegations,
        )
    )
    return TestClient(app), execution_id, delegation, events


def _headers(organization_id: str = "org-a") -> dict[str, str]:
    return {
        "X-AI-Governance-Organization-Id": organization_id,
        "X-AI-Governance-Project-Id": "project-a",
    }


def _payload(execution_id: str, delegation) -> dict[str, object]:
    return {
        "execution_id": execution_id,
        "action_id": "claims.update",
        "resource": {"resource_type": "sqlite.row", "resource_reference": "claims:42"},
        "delegation_id": delegation.delegation_id,
        "delegation_version": delegation.version,
        "delegation_digest": delegation.contract_digest,
        "tool_arguments_digest": ARGUMENT_DIGEST,
        "context": {"claimed_authority": "maintenance"},
        "idempotency_key": "claim-update-1",
    }


def test_endpoint_derives_actor_and_returns_server_resolved_delegation() -> None:
    client, execution_id, delegation, events = _client()
    response = client.post(
        "/api/v1/runtime-action-authorizations/authorize",
        headers=_headers(),
        json=_payload(execution_id, delegation),
    )

    assert response.status_code == 200
    assert response.json()["outcome"] == "ALLOW"
    assert response.json()["actor_id"] == CONTEXT.actor_id
    assert response.json()["delegation_digest"] == delegation.contract_digest
    assert (
        events.list_by_execution(execution_id, "org-a", "project-a")[-1].attributes[
            "authorization_outcome"
        ]
        == "ALLOW"
    )


def test_endpoint_rejects_agent_claims_policy_choice_and_cross_tenant_execution() -> (
    None
):
    client, execution_id, delegation, _events = _client()
    forged = _payload(execution_id, delegation)
    forged["actor_id"] = "caller-controlled"
    selected = _payload(execution_id, delegation)
    selected["policy_id"] = "claim-policy"
    foreign = client.post(
        "/api/v1/runtime-action-authorizations/authorize",
        headers=_headers("org-b"),
        json=_payload(execution_id, delegation),
    )

    assert (
        client.post(
            "/api/v1/runtime-action-authorizations/authorize",
            headers=_headers(),
            json=forged,
        ).status_code
        == 422
    )
    selected_response = client.post(
        "/api/v1/runtime-action-authorizations/authorize",
        headers=_headers(),
        json=selected,
    )
    assert selected_response.json()["reason_code"] == "POLICY_SELECTION_NOT_ALLOWED"
    assert foreign.status_code == 404


def test_endpoint_rejects_sensitive_context_and_missing_tool_digest() -> None:
    client, execution_id, delegation, _events = _client()
    sensitive = _payload(execution_id, delegation)
    sensitive["context"] = {"prompt": "protected content"}
    missing_digest = _payload(execution_id, delegation)
    del missing_digest["tool_arguments_digest"]
    incomplete_delegation = _payload(execution_id, delegation)
    del incomplete_delegation["delegation_digest"]

    assert (
        client.post(
            "/api/v1/runtime-action-authorizations/authorize",
            headers=_headers(),
            json=sensitive,
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/runtime-action-authorizations/authorize",
            headers=_headers(),
            json=incomplete_delegation,
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/runtime-action-authorizations/authorize",
            headers=_headers(),
            json=missing_digest,
        ).status_code
        == 422
    )
