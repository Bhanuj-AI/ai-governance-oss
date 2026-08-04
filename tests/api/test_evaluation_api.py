from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from kavach.api.app import create_app
from kavach.api.dependencies import (
    get_evaluation_repository,
    get_job_repository,
    get_provider_registry,
)
from kavach.api.dependencies.provider_installations import (
    get_provider_installation_service,
)
from kavach.domain.evaluation_result import (
    EvaluationArtifact,
    EvaluationMetric,
    EvaluationResult,
)
from kavach.evaluation.evaluation_request import EvaluationRequest
from kavach.providers.provider_capabilities import ProviderCapabilities
from kavach.providers.provider_descriptor import ProviderDescriptor
from kavach.providers.provider_registry import EvaluationProviderRegistry
from kavach.repositories.in_memory_evaluation_repository import (
    InMemoryEvaluationRepository,
)
from kavach.repositories import InMemoryJobRepository
from kavach.repositories.settings_provider_installation_repository import (
    SettingsProviderInstallationRepository,
)
from kavach.services.provider_installation_service import ProviderInstallationService
from kavach.settings_control.repository import InMemorySettingsRepository
from kavach.tenancy.domain import TenantContext


class FakeEvaluationProvider:
    def __init__(
        self,
    ) -> None:
        self.last_request: EvaluationRequest | None = None

    @property
    def descriptor(
        self,
    ) -> ProviderDescriptor:
        return ProviderDescriptor(
            name="fake",
            display_name="Fake Provider",
            version="1.0.0",
            adapter_version="1.0.0",
            capabilities=ProviderCapabilities(
                supported_metrics=(
                    "answer_relevance",
                    "groundedness",
                ),
                supports_artifacts=True,
                supports_explanations=True,
            ),
            metadata={"region": "test"},
        )

    def evaluate(
        self,
        request: EvaluationRequest,
    ) -> EvaluationResult:
        self.last_request = request
        requested_metrics = [
            metric_spec.name for metric_spec in request.metric_specs
        ] or ["answer_relevance"]

        return EvaluationResult(
            evaluation_id=f"eval-{request.execution.execution_id}",
            execution_id=request.execution.execution_id,
            evaluator_type=self.descriptor.name,
            evaluator_version=self.descriptor.version,
            metrics=[
                EvaluationMetric(
                    metric_name=metric_name,
                    metric_value=0.91,
                    explanation=f"{metric_name} passed.",
                )
                for metric_name in requested_metrics
            ],
            artifacts=[
                EvaluationArtifact(
                    artifact_type="trace",
                    payload={"execution_id": request.execution.execution_id},
                    metadata={"source": "fake"},
                )
            ],
            provider_metadata={
                "visible": "ok",
                "api_key": "secret",
            },
            provider_descriptor_snapshot=request.provider_descriptor_snapshot,
            created_at=datetime(2026, 6, 27, tzinfo=UTC),
        )


def _client(
    provider: FakeEvaluationProvider | None = None,
    repository: InMemoryEvaluationRepository | None = None,
    job_repository: InMemoryJobRepository | None = None,
) -> tuple[TestClient, FakeEvaluationProvider, InMemoryEvaluationRepository]:
    fake_provider = provider or FakeEvaluationProvider()
    fake_repository = repository or InMemoryEvaluationRepository()
    fake_job_repository = job_repository or InMemoryJobRepository()
    registry = EvaluationProviderRegistry()
    registry.register(fake_provider)

    app = create_app()
    app.dependency_overrides[get_provider_registry] = lambda: registry
    app.dependency_overrides[get_evaluation_repository] = lambda: fake_repository
    app.dependency_overrides[get_job_repository] = lambda: fake_job_repository
    return TestClient(app), fake_provider, fake_repository


def _submit_payload(
    **overrides: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "provider_name": "fake",
        "workflow_id": "claim-validation",
        "execution_id": "exec-1",
        "workflow_name": "Claim Validation",
        "workflow_version": "1.0.0",
        "execution_status": "COMPLETED",
        "input": {"question": "Was the claim valid?"},
        "final_state": {
            "answer": "The claim appears valid.",
            "context": "Policy evidence.",
        },
        "events": [{"event_type": "WORKFLOW_COMPLETED"}],
        "metric_specs": [
            {"name": "answer_relevance"},
            {
                "name": "groundedness",
                "threshold": 0.8,
                "metadata": {"rubric": "strict"},
            },
        ],
        "provider_config": {"model": "judge-model", "api_key": "secret"},
    }
    payload.update(overrides)
    return payload


def test_submit_evaluation_persists_and_returns_response() -> None:
    client, provider, repository = _client()

    response = client.post(
        "/api/v1/evaluations",
        json=_submit_payload(),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["evaluation_id"] == "eval-exec-1"
    assert payload["execution_id"] == "exec-1"
    assert payload["provider_name"] == "fake"
    assert payload["provider_version"] == "1.0.0"
    assert [metric["name"] for metric in payload["metrics"]] == [
        "answer_relevance",
        "groundedness",
    ]
    assert payload["artifacts"][0]["artifact_type"] == "trace"
    assert payload["provider_metadata"] == {"visible": "ok"}
    assert "provider_config" not in payload
    assert repository.find_by_evaluation_id("eval-exec-1") is not None
    assert provider.last_request is not None


def test_submit_evaluation_forwards_metric_specs_and_provider_config() -> None:
    client, provider, _repository = _client()

    response = client.post(
        "/api/v1/evaluations",
        json=_submit_payload(),
    )

    assert response.status_code == 201
    assert provider.last_request is not None
    assert [metric_spec.name for metric_spec in provider.last_request.metric_specs] == [
        "answer_relevance",
        "groundedness",
    ]
    assert provider.last_request.metric_specs[1].threshold == 0.8
    assert dict(provider.last_request.metric_specs[1].metadata) == {"rubric": "strict"}
    assert dict(provider.last_request.provider_config) == {
        "model": "judge-model",
        "api_key": "secret",
    }


def test_submit_evaluation_uses_requested_provider_from_registry() -> None:
    client, provider, _repository = _client()

    response = client.post(
        "/api/v1/evaluations",
        json=_submit_payload(provider_name="Fake"),
    )

    assert response.status_code == 201
    assert provider.last_request is not None
    assert response.json()["provider_name"] == "fake"


def test_submit_evaluation_resolves_tenant_provider_installation() -> None:
    client, provider, _repository = _client()
    registry = EvaluationProviderRegistry()
    registry.register(provider)
    installations = ProviderInstallationService(
        SettingsProviderInstallationRepository(InMemorySettingsRepository()), registry
    )
    installation = installations.create(
        provider_type="fake",
        display_name="Fake production judge",
        settings={"model": "configured-judge"},
        secret_refs={},
        enabled=True,
        context=TenantContext("org_default", "project_default", "local-admin", "req-1"),
    )
    client.app.dependency_overrides[get_provider_installation_service] = (
        lambda: installations
    )

    response = client.post(
        "/api/v1/evaluations",
        json=_submit_payload(
            provider_name=None,
            provider_installation_id=installation.installation_id,
            provider_config={},
        ),
    )

    assert response.status_code == 201
    assert response.json()["provider_name"] == "fake"
    assert provider.last_request is not None
    assert dict(provider.last_request.provider_config) == {"model": "configured-judge"}


def test_submit_evaluation_rejects_unknown_provider_installation() -> None:
    client, _provider, _repository = _client()

    response = client.post(
        "/api/v1/evaluations",
        json=_submit_payload(provider_name=None, provider_installation_id="missing"),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROVIDER_INSTALLATION_NOT_FOUND"


def test_get_evaluation_returns_existing_result() -> None:
    client, _provider, _repository = _client()
    client.post("/api/v1/evaluations", json=_submit_payload())

    response = client.get("/api/v1/evaluations/eval-exec-1")

    assert response.status_code == 200
    assert response.json()["evaluation_id"] == "eval-exec-1"


def test_get_evaluation_returns_404_for_missing_result() -> None:
    client, _provider, _repository = _client()

    response = client.get("/api/v1/evaluations/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "EVALUATION_NOT_FOUND"
    assert response.json()["error"]["details"]["evaluation_id"] == "missing"


def test_get_history_returns_existing_and_empty_results() -> None:
    client, _provider, _repository = _client()
    client.post("/api/v1/evaluations", json=_submit_payload())

    found_response = client.get("/api/v1/evaluations/history/exec-1")
    empty_response = client.get("/api/v1/evaluations/history/missing")

    assert found_response.status_code == 200
    assert found_response.json()["execution_id"] == "exec-1"
    assert found_response.json()["evaluations"][0]["evaluation_id"] == ("eval-exec-1")
    assert empty_response.status_code == 200
    assert empty_response.json() == {
        "execution_id": "missing",
        "evaluations": [],
    }


def test_get_latest_returns_newest_result() -> None:
    repository = InMemoryEvaluationRepository()
    repository.save(
        EvaluationResult(
            evaluation_id="older",
            execution_id="exec-1",
            evaluator_type="fake",
            evaluator_version="1.0.0",
            metrics=[],
            created_at=datetime(2026, 6, 26, tzinfo=UTC),
        )
    )
    repository.save(
        EvaluationResult(
            evaluation_id="newer",
            execution_id="exec-1",
            evaluator_type="fake",
            evaluator_version="1.0.0",
            metrics=[],
            created_at=datetime(2026, 6, 27, tzinfo=UTC),
        )
    )
    client, _provider, _repository = _client(repository=repository)

    response = client.get("/api/v1/evaluations/latest/exec-1")

    assert response.status_code == 200
    assert response.json()["evaluation_id"] == "newer"


def test_get_latest_returns_404_for_missing_execution() -> None:
    client, _provider, _repository = _client()

    response = client.get("/api/v1/evaluations/latest/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "EVALUATION_NOT_FOUND"
    assert response.json()["error"]["details"]["execution_id"] == "missing"


def test_unknown_provider_returns_404() -> None:
    client, _provider, _repository = _client()

    response = client.post(
        "/api/v1/evaluations",
        json=_submit_payload(provider_name="missing"),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROVIDER_NOT_FOUND"
    assert response.json()["error"]["details"] == {"provider_name": "missing"}


def test_unsupported_metric_returns_400() -> None:
    client, _provider, _repository = _client()

    response = client.post(
        "/api/v1/evaluations",
        json=_submit_payload(metric_specs=[{"name": "toxicity"}]),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_METRIC"
    assert response.json()["error"]["details"] == {
        "metric": "toxicity",
        "provider_name": "fake",
    }


def test_missing_provider_uses_configured_default() -> None:
    client, _provider, _repository = _client()
    payload = _submit_payload()
    payload.pop("provider_name")

    response = client.post("/api/v1/evaluations", json=payload)

    # The registry default is "mock" in production; this isolated test registry
    # intentionally does not contain it, proving the configured default was used.
    assert response.status_code == 404
    assert response.json()["error"]["details"]["provider_name"] == "mock"


def test_evaluation_endpoints_are_in_openapi() -> None:
    client, _provider, _repository = _client()

    paths = client.get("/openapi.json").json()["paths"]

    assert "/api/v1/evaluations" in paths
    assert "/api/v1/evaluations/{evaluation_id}" in paths
    assert "/api/v1/evaluations/history/{execution_id}" in paths
    assert "/api/v1/evaluations/latest/{execution_id}" in paths
    assert "/api/v1/evaluations/jobs" in paths


def test_submit_evaluation_job_returns_queued_job() -> None:
    job_repository = InMemoryJobRepository()
    client, _provider, _repository = _client(job_repository=job_repository)
    payload = {
        **_submit_payload(),
        "request_id": "request-1",
        "idempotency_key": "idem-1",
        "requested_by": "agent-1",
        "actor_type": "AGENT",
        "reason": "Governance evaluation",
        "submitted_by": "agent-1",
    }

    response = client.post("/api/v1/evaluations/jobs", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["job_type"] == "EVALUATION"
    assert body["status"] == "QUEUED"
    assert body["input_refs"]["operation"] == "evaluation.submit_async"
    assert body["input_refs"]["execution_id"] == "exec-1"
    assert job_repository.find_by_id(body["job_id"]) is not None


def test_submit_evaluation_job_snapshots_provider_installation_type() -> None:
    job_repository = InMemoryJobRepository()
    client, provider, _repository = _client(job_repository=job_repository)
    registry = EvaluationProviderRegistry()
    registry.register(provider)
    installations = ProviderInstallationService(
        SettingsProviderInstallationRepository(InMemorySettingsRepository()), registry
    )
    installation = installations.create(
        provider_type="fake",
        display_name="Fake queued judge",
        settings={"model": "queued-judge"},
        secret_refs={},
        enabled=True,
        context=TenantContext("org_default", "project_default", "local-admin", "req-1"),
    )
    client.app.dependency_overrides[get_provider_installation_service] = (
        lambda: installations
    )

    response = client.post(
        "/api/v1/evaluations/jobs",
        json={
            **_submit_payload(provider_name=None, provider_installation_id=installation.installation_id),
            "request_id": "request-installation",
            "idempotency_key": "idem-installation",
            "requested_by": "agent-1",
            "actor_type": "AGENT",
            "reason": "Governance evaluation",
            "submitted_by": "agent-1",
        },
    )

    assert response.status_code == 201
    refs = response.json()["input_refs"]
    assert refs["provider_name"] == "fake"
    assert refs["provider_installation_id"] == installation.installation_id


def test_api_layer_does_not_import_provider_adapters() -> None:
    api_files = [
        *Path("src/kavach/api/routers").rglob("*.py"),
        *Path("src/kavach/api/mappers").rglob("*.py"),
        *Path("src/kavach/api/models").rglob("*.py"),
    ]

    for api_file in api_files:
        source = api_file.read_text()

        assert "kavach.providers.trulens" not in source
        assert "import trulens" not in source
        assert "import openai" not in source
