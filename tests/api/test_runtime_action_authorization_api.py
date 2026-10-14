"""Public contract tests for runtime action authorization."""

from __future__ import annotations

from datetime import UTC, datetime

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
from ai_governance.repositories.in_memory_policy_administration_repository import (
    InMemoryPolicyAdministrationRepository,
)
from ai_governance.services.agent_execution_service import AgentExecutionService
from ai_governance.services.runtime_action_authorization_service import (
    RUNTIME_ACTION_AUTHORIZATION_METADATA_KEY,
    RUNTIME_ACTION_AUTHORIZATION_PURPOSE,
    RuntimeActionAuthorizationService,
)
from ai_governance.tenancy.domain import TenantContext

CONTEXT = TenantContext("org-a", "project-a", "server-derived-actor", "request-a")


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


def _client() -> tuple[TestClient, str, InMemoryAgentExecutionEventRepository]:
    policies = InMemoryPolicyAdministrationRepository()
    executions = InMemoryAgentExecutionRepository()
    events = InMemoryAgentExecutionEventRepository()
    definition = PolicyDefinition(
        policy_id="claim-policy",
        organization_id=CONTEXT.organization_id,
        project_id=CONTEXT.project_id,
        name="Claim policy",
        description=None,
        category=PolicyCategory.SECURITY,
        owner="owner",
        created_by="owner",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
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
            policy_id=definition.policy_id,
            version="1",
            status=PolicyStatus.ACTIVE,
            target_types=(DecisionTargetType.AGENT_EXECUTION,),
            rules=(
                PolicyRule(
                    rule_id="allow-claim-update",
                    name="Allow claim update",
                    conditions=(
                        PolicyCondition(
                            "action.id",
                            PolicyConditionOperator.EQUALS,
                            "claims.update",
                        ),
                    ),
                    effect=PolicyEffect.APPROVE,
                    reason_template="Allow claim update.",
                    priority=10,
                ),
            ),
            created_by="owner",
            created_at=definition.created_at,
            activated_at=definition.created_at,
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
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_compatible_tenant_context] = _context_from_headers
    app.dependency_overrides[get_runtime_action_authorization_service] = lambda: (
        RuntimeActionAuthorizationService(
            policy_repository=policies,
            execution_repository=executions,
            event_repository=events,
        )
    )
    return TestClient(app), execution_id, events


def _headers(organization_id: str = "org-a") -> dict[str, str]:
    return {
        "X-AI-Governance-Organization-Id": organization_id,
        "X-AI-Governance-Project-Id": "project-a",
    }


def _payload(execution_id: str) -> dict[str, object]:
    return {
        "execution_id": execution_id,
        "action_id": "claims.update",
        "resource": {"resource_type": "sqlite.row", "resource_reference": "claims:42"},
        "context": {"risk": "low"},
        "idempotency_key": "claim-update-1",
    }


def test_endpoint_derives_actor_and_persists_authorization_evidence() -> None:
    client, execution_id, events = _client()

    response = client.post(
        "/api/v1/runtime-action-authorizations/authorize",
        headers=_headers(),
        json=_payload(execution_id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "ALLOW"
    assert body["actor_id"] == CONTEXT.actor_id
    assert body["policy_id"] == "claim-policy"
    event = events.list_by_execution(execution_id, "org-a", "project-a")[-1]
    assert event.event_type.value == "RUNTIME_ACTION_AUTHORIZATION"
    assert event.attributes["authorization_outcome"] == "ALLOW"


def test_endpoint_rejects_claims_and_hides_cross_tenant_execution() -> None:
    client, execution_id, _ = _client()
    payload = _payload(execution_id)
    payload["actor_id"] = "caller-controlled"
    payload["organization_id"] = "org-b"

    forged = client.post(
        "/api/v1/runtime-action-authorizations/authorize",
        headers=_headers(),
        json=payload,
    )
    foreign = client.post(
        "/api/v1/runtime-action-authorizations/authorize",
        headers=_headers("org-b"),
        json=_payload(execution_id),
    )

    assert forged.status_code == 422
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "RUNTIME_ACTION_EXECUTION_NOT_FOUND"


def test_endpoint_rejects_sensitive_or_excessive_context() -> None:
    client, execution_id, _ = _client()
    sensitive = _payload(execution_id)
    sensitive["context"] = {"prompt": "protected content"}
    excessive = _payload(execution_id)
    excessive["context"] = {f"fact_{index}": index for index in range(33)}

    sensitive_response = client.post(
        "/api/v1/runtime-action-authorizations/authorize",
        headers=_headers(),
        json=sensitive,
    )
    excessive_response = client.post(
        "/api/v1/runtime-action-authorizations/authorize",
        headers=_headers(),
        json=excessive,
    )

    assert sensitive_response.status_code == 422
    assert excessive_response.status_code == 422
