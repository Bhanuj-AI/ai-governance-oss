from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient

from ai_governance.api.app import create_app
from ai_governance.api.dependencies import get_api_settings
from ai_governance.api.dependencies.agent_execution import get_agent_execution_service
from ai_governance.api.dependencies.repositories import (
    get_agent_execution_repository,
    get_causal_audit_repository,
)
from ai_governance.api.dependencies.runtime_finding_repo import (
    get_runtime_finding_repository,
)
from ai_governance.api.dependencies.runtime_findings import (
    get_runtime_finding_service,
)


def test_local_demo_seed_is_idempotent() -> None:
    client = TestClient(create_app())

    first = client.post("/api/v1/local/demo/seed")
    second = client.post("/api/v1/local/demo/seed")

    assert first.status_code == 200
    assert first.json()["seeded"] is True
    assert first.json()["decision_ids"]
    assert second.status_code == 200
    assert second.json()["decision_ids"] == first.json()["decision_ids"]


def test_local_demo_seed_is_unavailable_outside_development() -> None:
    app = create_app()
    settings = get_api_settings()
    app.dependency_overrides[get_api_settings] = lambda: replace(
        settings, environment="staging"
    )

    response = TestClient(app).post("/api/v1/local/demo/seed")

    assert response.status_code == 403


def test_agent_runtime_demo_seed_is_idempotent() -> None:
    get_agent_execution_service.cache_clear()
    get_agent_execution_repository.cache_clear()
    get_causal_audit_repository.cache_clear()
    get_runtime_finding_repository.cache_clear()
    get_runtime_finding_service.cache_clear()
    try:
        client = TestClient(create_app())

        before_seed = client.get("/api/v1/local/demo/agent-runtime/status")
        assert before_seed.status_code == 200
        assert before_seed.json() == {"seeded": False}

        first = client.post("/api/v1/local/demo/agent-runtime")
        second = client.post("/api/v1/local/demo/agent-runtime")
        observed_agents = client.get("/api/v1/agent-executions/agents?limit=2")
        next_agent_page = client.get("/api/v1/agent-executions/agents?limit=2&offset=2")
        open_findings = client.get("/api/v1/runtime-findings?status=OPEN&limit=50")
        causal_audits = client.get("/api/v1/agents-runtime/causal-audits?limit=10")
        after_seed = client.get("/api/v1/local/demo/agent-runtime/status")

        assert first.status_code == 200
        assert first.json()["seeded"] is True
        assert first.json()["decision_ids"]
        assert second.status_code == 200
        assert second.json()["decision_ids"] == []
        assert observed_agents.status_code == 200
        assert len(observed_agents.json()["items"]) == 2
        assert observed_agents.json()["items"][0]["execution_count"] > 0
        assert observed_agents.json()["next_offset"] == 2
        assert next_agent_page.status_code == 200
        assert next_agent_page.json()["items"]
        assert open_findings.status_code == 200
        assert open_findings.json()["items"]
        assert {item["status"] for item in open_findings.json()["items"]} == {"OPEN"}
        assert causal_audits.status_code == 200
        audits_by_classification = {
            item["classification"]: item for item in causal_audits.json()["items"]
        }
        assert (
            len(audits_by_classification["NO_TOOL_EVIDENCE"]["tool_call_results"]) == 0
        )
        assert (
            len(audits_by_classification["EVIDENCE_IGNORED"]["tool_call_results"]) == 1
        )
        assert (
            audits_by_classification["EVIDENCE_IGNORED"]["tool_call_results"][0][
                "influence_score"
            ]
            == 0.004
        )
        over_extended = audits_by_classification["OVER_EXTENDED"]["tool_call_results"]
        assert len(over_extended) == 3
        assert max(item["influence_score"] for item in over_extended) == 0.6
        assert sum(item["post_saturation"] for item in over_extended) == 2
        evidence_aligned = audits_by_classification["EVIDENCE_ALIGNED"][
            "tool_call_results"
        ]
        assert len(evidence_aligned) == 1
        assert evidence_aligned[0]["influence_score"] == 0.7
        assert after_seed.json() == {"seeded": True}
    finally:
        get_agent_execution_service.cache_clear()
        get_agent_execution_repository.cache_clear()
        get_causal_audit_repository.cache_clear()
        get_runtime_finding_repository.cache_clear()
        get_runtime_finding_service.cache_clear()


def test_runtime_finding_actions_are_post_routes() -> None:
    get_agent_execution_service.cache_clear()
    get_agent_execution_repository.cache_clear()
    get_runtime_finding_repository.cache_clear()
    get_runtime_finding_service.cache_clear()
    try:
        client = TestClient(create_app())

        detection = client.post("/api/v1/runtime-findings/detect")
        reconciliation = client.post("/api/v1/runtime-findings/reconcile")

        assert detection.status_code == 202
        assert detection.json()["status"] == "accepted"
        assert reconciliation.status_code == 200
    finally:
        get_agent_execution_service.cache_clear()
        get_agent_execution_repository.cache_clear()
        get_runtime_finding_repository.cache_clear()
        get_runtime_finding_service.cache_clear()
