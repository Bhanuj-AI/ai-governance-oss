from fastapi.testclient import TestClient

from ai_governance.api.app import create_app
from ai_governance.api.dependencies.evidence_intervention_policy import (
    get_evidence_intervention_policy_service,
)
from ai_governance.api.dependencies.repositories import (
    get_evidence_intervention_policy_repository,
)


def test_intervention_policy_lifecycle_is_versioned_and_tenant_scoped():
    _clear_dependencies()
    try:
        client = TestClient(create_app())
        created = client.post(
            "/api/v1/agents-runtime/causal-audit/intervention-policies",
            json={
                "tool_name": "risk.lookup",
                "schema_id": "risk-result",
                "schema_version": "1",
                "allowed_strategies": ["NULLIFY"],
                "strategy_configuration": {
                    "json_schema": {"type": "object"},
                    "neutral_value": {"records": []},
                },
            },
        )
        assert created.status_code == 201, created.text
        policy = created.json()
        base = (
            "/api/v1/agents-runtime/causal-audit/intervention-policies/"
            f"{policy['policy_id']}/versions/{policy['version']}"
        )
        assert client.post(f"{base}/validate").status_code == 200
        active = client.post(f"{base}/activate")
        assert active.status_code == 200
        assert active.json()["status"] == "ACTIVE"

        edited = client.post(
            f"{base}/edit",
            json={
                "strategy_configuration": {
                    "json_schema": {"type": "object"},
                    "neutral_value": {"records": ["new"]},
                }
            },
        )
        assert edited.status_code == 201
        assert edited.json()["version"] == 2
        assert edited.json()["status"] == "DRAFT"
        versions = client.get(
            "/api/v1/agents-runtime/causal-audit/intervention-policies/"
            f"{policy['policy_id']}"
        )
        assert versions.status_code == 200
        assert [item["version"] for item in versions.json()["items"]] == [1, 2]
    finally:
        _clear_dependencies()


def _clear_dependencies() -> None:
    get_evidence_intervention_policy_service.cache_clear()
    get_evidence_intervention_policy_repository.cache_clear()
