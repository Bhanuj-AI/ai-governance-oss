from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError
from starlette.middleware.base import BaseHTTPMiddleware

from ai_governance import __version__
from ai_governance.api.app import _configure_application_logging, create_app
from ai_governance.api.dependencies import (
    get_api_settings,
    get_governance_decision_repository,
    get_job_repository,
    get_mcp_audit_log,
    get_ontology_graph_query_service,
    get_ontology_graph_repository,
    get_policy_administration_repository,
    get_prompt_registry_service,
)
from ai_governance.api.logging import (
    ControlPlaneJsonFormatter,
    configure_sensitive_third_party_logging,
    request_logging_middleware,
)
from ai_governance.mcp.audit import MCPExecutionAuditLog
from ai_governance.ontology import (
    InMemoryOntologyGraphQueryRepository,
    InMemoryOntologyGraphRepository,
    OntologyGraphQueryService,
)
from ai_governance.providers.errors import (
    ProviderContractError,
    ProviderRegistryError,
)
from ai_governance.repositories import InMemoryPolicyAdministrationRepository
from ai_governance.repositories.in_memory import (
    InMemoryGovernanceDecisionRepository,
    InMemoryJobRepository,
)


def test_rest_app_starts_with_expected_metadata() -> None:
    app = create_app()

    assert isinstance(app, FastAPI)
    assert app.title == "AI Governance Control Plane REST API"
    assert app.description == ("AI Governance Control Plane for Enterprise LLMs")
    assert app.version == "v1"


def test_health_endpoint_returns_up() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "UP"}


def test_ready_endpoint_returns_up() -> None:
    client = TestClient(create_app())

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "UP"}


def test_metadata_endpoint_returns_versioned_api_metadata() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1")

    assert response.status_code == 200
    assert response.json() == {
        "name": "AI Governance Control Plane",
        "version": __version__,
        "api_version": "v1",
        "timezone": "UTC",
    }


def test_rest_api_allows_local_console_cors_origin() -> None:
    client = TestClient(create_app())

    response = client.get(
        "/api/v1",
        headers={"Origin": "http://127.0.0.1:3000"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ("http://127.0.0.1:3000")


def test_openapi_and_swagger_are_available() -> None:
    client = TestClient(create_app())

    openapi_response = client.get("/openapi.json")
    docs_response = client.get("/docs")
    redoc_response = client.get("/redoc")

    assert openapi_response.status_code == 200
    assert openapi_response.json()["info"]["title"] == "AI Governance Control Plane REST API"
    assert "/api/v1" in openapi_response.json()["paths"]
    assert docs_response.status_code == 200
    assert "Swagger UI" in docs_response.text
    assert redoc_response.status_code == 200
    assert "ReDoc" in redoc_response.text


def test_ready_endpoint_uses_fastapi_dependency_injection() -> None:
    app = create_app()
    calls: list[str] = []

    def fake_prompt_registry_service() -> object:
        calls.append("prompt_service")
        return object()

    app.dependency_overrides[get_prompt_registry_service] = fake_prompt_registry_service
    client = TestClient(app)

    response = client.get("/ready")

    assert response.status_code == 200
    assert calls == ["prompt_service"]


def test_exception_handlers_are_registered() -> None:
    app = create_app()

    assert RequestValidationError in app.exception_handlers
    assert ValidationError in app.exception_handlers
    assert ProviderRegistryError in app.exception_handlers
    assert ProviderContractError in app.exception_handlers
    assert ValueError in app.exception_handlers
    assert Exception in app.exception_handlers


def test_value_error_uses_common_error_schema() -> None:
    app = create_app()

    @app.get("/raise-value-error")
    def raise_value_error() -> None:
        raise ValueError("invalid value")

    client = TestClient(app)

    response = client.get("/raise-value-error")

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "value_error",
            "message": "invalid value",
            "details": None,
        }
    }


def test_validation_error_uses_common_error_schema() -> None:
    app = create_app()

    @app.get("/items/{item_id}")
    def get_item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    client = TestClient(app)

    response = client.get("/items/not-an-int")

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "validation_error"
    assert payload["error"]["message"] == "Request validation failed."
    assert payload["error"]["details"]


def test_generic_exception_does_not_expose_stack_trace() -> None:
    app = create_app()

    @app.get("/raise-runtime-error")
    def raise_runtime_error() -> None:
        raise RuntimeError("secret internals")

    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/raise-runtime-error")

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_server_error",
            "message": "An unexpected error occurred.",
            "details": None,
        }
    }
    assert "secret internals" not in response.text


def test_request_logging_middleware_is_registered() -> None:
    app = create_app()

    assert any(
        middleware.cls is BaseHTTPMiddleware
        and middleware.kwargs.get("dispatch") is request_logging_middleware
        for middleware in app.user_middleware
    )


def test_application_logging_routes_service_events_to_stderr() -> None:
    _configure_application_logging("debug", "json")

    application_logger = logging.getLogger("ai_governance")

    assert application_logger.level == logging.DEBUG
    assert application_logger.handlers
    assert application_logger.propagate is False


def test_application_json_logging_extracts_event_fields() -> None:
    record = logging.LogRecord(
        "ai_governance.services.candidate_execution_runtime",
        logging.INFO,
        __file__,
        1,
        "candidate_execution_completed run_id=%s latency_ms=%s",
        ("run-1", 2076),
        None,
    )

    payload = json.loads(ControlPlaneJsonFormatter().format(record))

    assert payload["event"] == "candidate_execution_completed"
    assert payload["component"] == "services.candidate_execution_runtime"
    assert payload["fields"] == {"latency_ms": "2076", "run_id": "run-1"}


def test_trulens_raw_response_warning_is_redacted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    configure_sensitive_third_party_logging()
    logger = logging.getLogger("trulens.feedback.generated")

    with caplog.at_level(logging.WARNING, logger=logger.name):
        logger.warning(
            "Multiple valid rating values found in the string: %s",
            '{"output":"protected provider response"}',
        )

    assert "trulens_ambiguous_score_response" in caplog.text
    assert "protected provider response" not in caplog.text


def test_request_logging_adds_request_id_header() -> None:
    client = TestClient(create_app())

    response = client.get("/health", headers={"X-Request-ID": "request-1"})

    assert response.headers["X-Request-ID"] == "request-1"


def test_api_settings_use_environment_defaults_and_overrides(
    monkeypatch,
) -> None:
    # Clear any previously set values and use explicit test values
    monkeypatch.delenv("AI_GOVERNANCE_API_HOST", raising=False)
    monkeypatch.delenv("AI_GOVERNANCE_API_PORT", raising=False)
    monkeypatch.delenv("AI_GOVERNANCE_API_LOG_LEVEL", raising=False)
    monkeypatch.delenv("AI_GOVERNANCE_API_LOG_FORMAT", raising=False)
    monkeypatch.delenv("AI_GOVERNANCE_AUTO_SEED_DEMO_DATA", raising=False)

    # Set explicit values for the "defaults" test
    monkeypatch.setenv("AI_GOVERNANCE_API_HOST", "127.0.0.1")
    monkeypatch.setenv("AI_GOVERNANCE_API_PORT", "8000")
    monkeypatch.setenv("AI_GOVERNANCE_API_LOG_LEVEL", "INFO")
    monkeypatch.setenv("AI_GOVERNANCE_AUTO_SEED_DEMO_DATA", "false")

    defaults = get_api_settings()

    assert defaults.host == "127.0.0.1"
    assert defaults.port == 8000
    assert defaults.log_level == "INFO"
    assert defaults.log_format == "json"
    assert defaults.auto_seed_demo_data is False

    monkeypatch.setenv("AI_GOVERNANCE_API_HOST", "0.0.0.0")
    monkeypatch.setenv("AI_GOVERNANCE_API_PORT", "9000")
    monkeypatch.setenv("AI_GOVERNANCE_API_LOG_LEVEL", "debug")
    monkeypatch.setenv("AI_GOVERNANCE_API_LOG_FORMAT", "text")
    monkeypatch.setenv("AI_GOVERNANCE_AUTO_SEED_DEMO_DATA", "true")

    overridden = get_api_settings()

    assert overridden.host == "0.0.0.0"
    assert overridden.port == 9000
    assert overridden.log_level == "debug"
    assert overridden.log_format == "text"
    assert overridden.auto_seed_demo_data is True


def test_local_startup_can_seed_demo_data(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AI_GOVERNANCE_AUTO_SEED_DEMO_DATA", "true")
    graph_repository = InMemoryOntologyGraphRepository()
    decision_repository = InMemoryGovernanceDecisionRepository()
    job_repository = InMemoryJobRepository()
    audit_log = MCPExecutionAuditLog.in_memory()
    policy_repository = InMemoryPolicyAdministrationRepository()

    def query_service() -> OntologyGraphQueryService:
        return OntologyGraphQueryService(
            InMemoryOntologyGraphQueryRepository(graph_repository)
        )

    app = create_app()
    app.dependency_overrides[get_ontology_graph_repository] = lambda: graph_repository
    app.dependency_overrides[get_ontology_graph_query_service] = query_service
    app.dependency_overrides[get_governance_decision_repository] = lambda: (
        decision_repository
    )
    app.dependency_overrides[get_policy_administration_repository] = lambda: (
        policy_repository
    )
    app.dependency_overrides[get_job_repository] = lambda: job_repository
    app.dependency_overrides[get_mcp_audit_log] = lambda: audit_log

    with TestClient(app) as client:
        response = client.get("/api/v1/dashboard")
        policies_response = client.get("/api/v1/policies")
        jobs_response = client.get("/api/v1/jobs")
        audit_response = client.get("/api/v1/audit")

    assert response.status_code == 200
    assert response.json()["governance_statistics"][0]["value"] == 4
    assert policies_response.status_code == 200
    policies = policies_response.json()
    assert policies[0]["policy_id"] == "policy-release-gate"
    assert policies[0]["status"] == "ACTIVE"
    assert jobs_response.status_code == 200
    jobs = jobs_response.json()["jobs"]
    assert len(jobs) == 13
    assert {job["status"] for job in jobs} == {
        "CANCELLED",
        "FAILED",
        "QUEUED",
        "SUCCEEDED",
    }
    assert audit_response.status_code == 200
    assert audit_response.json()["total"] == 8


def test_routers_do_not_import_repositories_directly() -> None:
    router_dir = Path("src/ai_governance/api/routers")

    for router_file in router_dir.glob("*.py"):
        source = router_file.read_text()

        assert "ai_governance.repositories" not in source
        assert "Repository" not in source


def test_openapi_includes_response_models() -> None:
    client = TestClient(create_app())

    schemas = client.get("/openapi.json").json()["components"]["schemas"]

    assert "HealthResponse" in schemas
    assert "JobResponse" in schemas
    assert "MetadataResponse" in schemas


def test_request_validation_handler_registered_for_request_models() -> None:
    app = create_app()

    class InputModel(BaseModel):
        value: int

    @app.post("/input")
    def post_input(
        payload: InputModel,
        marker: object = Depends(lambda: object()),
    ) -> dict[str, int]:
        return {"value": payload.value}

    client = TestClient(app)

    response = client.post("/input", json={"value": "not-an-int"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
