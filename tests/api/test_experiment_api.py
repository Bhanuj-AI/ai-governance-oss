from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from ai_governance.api.app import create_app
from ai_governance.api.dependencies import (
    get_dataset_repository,
    get_evaluation_repository,
    get_evaluation_run_repository,
    get_experiment_candidate_repository,
    get_experiment_repository,
    get_job_repository,
    get_leaderboard_repository,
    get_model_repository,
    get_prompt_repository,
    get_provider_registry,
)
from ai_governance.domain.datasets import Dataset, DatasetStatus
from ai_governance.domain.evaluation_result import EvaluationMetric, EvaluationResult
from ai_governance.domain.models import Model, ModelStatus
from ai_governance.domain.prompts import Prompt, PromptStatus
from ai_governance.evaluation import EvaluationRequest
from ai_governance.providers.provider_capabilities import ProviderCapabilities
from ai_governance.providers.provider_descriptor import ProviderDescriptor
from ai_governance.providers.provider_registry import EvaluationProviderRegistry
from ai_governance.repositories.in_memory_dataset_repository import (
    InMemoryDatasetRepository,
)
from ai_governance.repositories.in_memory_evaluation_repository import (
    InMemoryEvaluationRepository,
)
from ai_governance.repositories.in_memory_evaluation_run_repository import (
    InMemoryEvaluationRunRepository,
)
from ai_governance.repositories.in_memory_experiment_candidate_repository import (
    InMemoryExperimentCandidateRepository,
)
from ai_governance.repositories.in_memory_experiment_repository import (
    InMemoryExperimentRepository,
)
from ai_governance.repositories.in_memory_leaderboard_repository import (
    InMemoryLeaderboardRepository,
)
from ai_governance.repositories import InMemoryJobRepository
from ai_governance.repositories.in_memory_model_repository import (
    InMemoryModelRepository,
)
from ai_governance.repositories.in_memory_prompt_repository import (
    InMemoryPromptRepository,
)


class FakeEvaluationProvider:
    def __init__(self) -> None:
        self.requests: list[EvaluationRequest] = []

    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            name="fake",
            display_name="Fake Provider",
            version="1.0.0",
            adapter_version="1.0.0",
            capabilities=ProviderCapabilities(
                supported_metrics=(
                    "answer_relevance",
                    "groundedness",
                )
            ),
        )

    def evaluate(
        self,
        request: EvaluationRequest,
    ) -> EvaluationResult:
        self.requests.append(request)
        metric_names = [
            metric_spec.name
            for metric_spec in request.metric_specs
        ] or ["answer_relevance"]
        return EvaluationResult(
            evaluation_id=f"eval-{request.execution_id}",
            execution_id=request.execution_id,
            evaluator_type="fake",
            evaluator_version="1.0.0",
            metrics=[
                EvaluationMetric(
                    metric_name=metric_name,
                    metric_value=0.9,
                    explanation="Passed.",
                )
                for metric_name in metric_names
            ],
        )


def _client(
    job_repository: InMemoryJobRepository | None = None,
) -> tuple[
    TestClient,
    FakeEvaluationProvider,
    InMemoryEvaluationRepository,
]:
    provider = FakeEvaluationProvider()
    provider_registry = EvaluationProviderRegistry()
    provider_registry.register(provider)

    experiment_repository = InMemoryExperimentRepository()
    candidate_repository = InMemoryExperimentCandidateRepository()
    evaluation_run_repository = InMemoryEvaluationRunRepository()
    evaluation_repository = InMemoryEvaluationRepository()
    resolved_job_repository = job_repository or InMemoryJobRepository()
    leaderboard_repository = InMemoryLeaderboardRepository()
    prompt_repository = InMemoryPromptRepository()
    model_repository = InMemoryModelRepository()
    dataset_repository = InMemoryDatasetRepository()
    _seed_registry_assets(
        prompt_repository=prompt_repository,
        model_repository=model_repository,
        dataset_repository=dataset_repository,
    )

    app = create_app()
    app.dependency_overrides[get_provider_registry] = lambda: provider_registry
    app.dependency_overrides[get_experiment_repository] = (
        lambda: experiment_repository
    )
    app.dependency_overrides[get_experiment_candidate_repository] = (
        lambda: candidate_repository
    )
    app.dependency_overrides[get_evaluation_run_repository] = (
        lambda: evaluation_run_repository
    )
    app.dependency_overrides[get_evaluation_repository] = (
        lambda: evaluation_repository
    )
    app.dependency_overrides[get_leaderboard_repository] = (
        lambda: leaderboard_repository
    )
    app.dependency_overrides[get_prompt_repository] = (
        lambda: prompt_repository
    )
    app.dependency_overrides[get_model_repository] = lambda: model_repository
    app.dependency_overrides[get_dataset_repository] = (
        lambda: dataset_repository
    )
    app.dependency_overrides[get_job_repository] = (
        lambda: resolved_job_repository
    )
    return TestClient(app), provider, evaluation_repository


def _seed_registry_assets(
    prompt_repository: InMemoryPromptRepository,
    model_repository: InMemoryModelRepository,
    dataset_repository: InMemoryDatasetRepository,
) -> None:
    created_at = datetime(2026, 6, 27, tzinfo=UTC)
    prompt_repository.save(
        Prompt(
            prompt_id="prompt",
            name="prompt",
            version="v1",
            template="Answer: {{question}}",
            variables=("question",),
            created_at=created_at,
            created_by="tester",
            status=PromptStatus.ACTIVE,
        )
    )
    model_repository.save(
        Model(
            model_id="model",
            provider="fake",
            model_name="model",
            version="v1",
            parameters={},
            cost={"input": 0.01},
            latency=0.2,
            context_window=4096,
            creator="tester",
            created_at=created_at,
            status=ModelStatus.ACTIVE,
        )
    )
    dataset_repository.save(
        Dataset(
            dataset_id="dataset",
            name="dataset",
            version="v1",
            description="Test dataset",
            storage_uri="memory://dataset",
            storage_type="memory",
            schema_version="1",
            record_count=1,
            checksum="sha256:test",
            creator="tester",
            created_at=created_at,
            status=DatasetStatus.ACTIVE,
        )
    )


def _create_experiment(
    client: TestClient,
    name: str = "claim-validation-v1",
) -> str:
    response = client.post(
        "/api/v1/experiments",
        json={
            "name": name,
            "description": "Compare claim validation configurations",
            "metadata": {"owner": "tester", "api_key": "secret"},
        },
    )
    assert response.status_code == 201
    return str(response.json()["experiment_id"])


def _add_candidate(
    client: TestClient,
    experiment_id: str,
    candidate_name: str = "candidate-a",
    temperature: float = 0.1,
) -> str:
    response = client.post(
        f"/api/v1/experiments/{experiment_id}/candidates",
        json={
            "candidate_name": candidate_name,
            "prompt_version": "prompt:v1",
            "model_version": "model:v1",
            "dataset_version": "dataset:v1",
            "provider_name": "fake",
            "runtime_parameters": {
                "temperature": temperature,
                "top_p": 0.9,
                "max_tokens": 256,
            },
            "metadata": {"answer": "Yes", "context": "Evidence."},
        },
    )
    assert response.status_code == 201
    return str(response.json()["candidate_id"])


def test_create_and_get_experiment() -> None:
    client, _provider, _evaluation_repository = _client()

    experiment_id = _create_experiment(client)
    response = client.get(f"/api/v1/experiments/{experiment_id}")

    assert response.status_code == 200
    assert response.json()["experiment_id"] == experiment_id
    assert response.json()["status"] == "DRAFT"
    assert response.json()["updated_at"] == response.json()["created_at"]


def test_list_experiments() -> None:
    client, _provider, _evaluation_repository = _client()

    experiment_id = _create_experiment(client)
    response = client.get("/api/v1/experiments")

    assert response.status_code == 200
    assert response.json()[0]["experiment_id"] == experiment_id
    assert response.json()[0]["name"] == "claim-validation-v1"


def test_create_experiment_scrubs_metadata_from_response() -> None:
    client, _provider, _evaluation_repository = _client()

    response = client.post(
        "/api/v1/experiments",
        json={
            "name": "claim-validation-v1",
            "description": "Compare claim validation configurations",
            "metadata": {"visible": "ok", "api_key": "secret"},
        },
    )

    assert response.status_code == 201
    assert response.json()["metadata"] == {"visible": "ok"}


def test_get_missing_experiment_returns_404() -> None:
    client, _provider, _evaluation_repository = _client()

    response = client.get("/api/v1/experiments/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "EXPERIMENT_NOT_FOUND"


def test_add_candidate() -> None:
    client, _provider, _evaluation_repository = _client()
    experiment_id = _create_experiment(client)

    candidate_id = _add_candidate(client, experiment_id)

    assert candidate_id


def test_list_candidates_and_runs() -> None:
    client, _provider, _evaluation_repository = _client()
    experiment_id = _create_experiment(client)
    _add_candidate(client, experiment_id)

    candidates_response = client.get(
        f"/api/v1/experiments/{experiment_id}/candidates"
    )
    run_response = client.get(f"/api/v1/experiments/{experiment_id}/runs")

    assert candidates_response.status_code == 200
    assert candidates_response.json()[0]["candidate_name"] == "candidate-a"
    assert run_response.status_code == 200
    assert run_response.json() == []

    assert client.post(
        f"/api/v1/experiments/{experiment_id}/run",
        json={"metric_specs": [{"name": "answer_relevance"}]},
    ).status_code == 200
    populated_runs_response = client.get(
        f"/api/v1/experiments/{experiment_id}/runs"
    )
    assert populated_runs_response.status_code == 200
    assert populated_runs_response.json()[0]["status"] == "COMPLETED"


def test_compare_candidates_returns_configuration_and_backend_metrics() -> None:
    client, _provider, _evaluation_repository = _client()
    experiment_id = _create_experiment(client)
    baseline_id = _add_candidate(client, experiment_id)
    comparison_id = _add_candidate(
        client,
        experiment_id,
        candidate_name="candidate-b",
        temperature=0.8,
    )

    run_response = client.post(
        f"/api/v1/experiments/{experiment_id}/run",
        json={
            "metric_specs": [
                {"name": "answer_relevance"},
                {"name": "groundedness"},
            ]
        },
    )
    assert run_response.status_code == 200

    response = client.get(
        f"/api/v1/experiments/{experiment_id}/comparison",
        params={
            "baseline_candidate_id": baseline_id,
            "comparison_candidate_id": comparison_id,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["baseline_candidate"]["candidate_id"] == baseline_id
    assert payload["comparison_candidate"]["candidate_id"] == comparison_id
    assert payload["comparison_candidate"]["runtime_parameters"]["temperature"] == 0.8
    assert {metric["metric_name"] for metric in payload["metric_comparisons"]} == {
        "answer_relevance",
        "groundedness",
    }


def test_compare_candidates_rejects_same_candidate_and_missing_runs() -> None:
    client, _provider, _evaluation_repository = _client()
    experiment_id = _create_experiment(client)
    candidate_id = _add_candidate(client, experiment_id)

    same_candidate_response = client.get(
        f"/api/v1/experiments/{experiment_id}/comparison",
        params={
            "baseline_candidate_id": candidate_id,
            "comparison_candidate_id": candidate_id,
        },
    )
    assert same_candidate_response.status_code == 400

    other_candidate_id = _add_candidate(
        client,
        experiment_id,
        candidate_name="candidate-b",
    )
    missing_run_response = client.get(
        f"/api/v1/experiments/{experiment_id}/comparison",
        params={
            "baseline_candidate_id": candidate_id,
            "comparison_candidate_id": other_candidate_id,
        },
    )
    assert missing_run_response.status_code == 400


def test_compare_candidates_does_not_cross_experiment_boundaries() -> None:
    client, _provider, _evaluation_repository = _client()
    first_experiment_id = _create_experiment(client)
    second_experiment_id = _create_experiment(client, "claim-validation-v2")
    first_candidate_id = _add_candidate(client, first_experiment_id)
    second_candidate_id = _add_candidate(client, second_experiment_id)

    response = client.get(
        f"/api/v1/experiments/{first_experiment_id}/comparison",
        params={
            "baseline_candidate_id": first_candidate_id,
            "comparison_candidate_id": second_candidate_id,
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CANDIDATE_NOT_FOUND"


def test_list_candidates_and_runs_require_the_same_tenant() -> None:
    client, _provider, _evaluation_repository = _client()
    experiment_id = _create_experiment(client)

    response = client.get(
        f"/api/v1/experiments/{experiment_id}/candidates",
        headers={"X-AI-Governance-Organization-Id": "other-org"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "TenantContextInvalid"


def test_add_candidate_requires_known_provider() -> None:
    client, _provider, _evaluation_repository = _client()
    experiment_id = _create_experiment(client)

    response = client.post(
        f"/api/v1/experiments/{experiment_id}/candidates",
        json={
            "candidate_name": "candidate-a",
            "prompt_version": "prompt:v1",
            "model_version": "model:v1",
            "dataset_version": "dataset:v1",
            "provider_name": "missing",
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROVIDER_NOT_FOUND"


def test_run_experiment_forwards_metric_specs_and_provider_config() -> None:
    client, provider, evaluation_repository = _client()
    experiment_id = _create_experiment(client)
    _add_candidate(client, experiment_id)

    response = client.post(
        f"/api/v1/experiments/{experiment_id}/run",
        json={
            "metric_specs": [
                {"name": "answer_relevance"},
                {"name": "groundedness"},
            ],
            "provider_config": {"model": "judge", "api_key": "secret"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["runs"][0]["status"] == "COMPLETED"
    assert payload["leaderboard"]["entries"][0]["rank"] == 1
    assert "provider_config" not in payload
    assert provider.requests
    assert [
        metric_spec.name
        for metric_spec in provider.requests[0].metric_specs
    ] == ["answer_relevance", "groundedness"]
    assert dict(provider.requests[0].provider_config) == {
        "model": "judge",
        "api_key": "secret",
    }
    assert evaluation_repository.find_by_evaluation_id(
        payload["runs"][0]["evaluation_result_id"]
    )


def test_get_leaderboard_after_run() -> None:
    client, _provider, _evaluation_repository = _client()
    experiment_id = _create_experiment(client)
    _add_candidate(client, experiment_id)
    client.post(
        f"/api/v1/experiments/{experiment_id}/run",
        json={"metric_specs": [{"name": "answer_relevance"}]},
    )

    response = client.get(f"/api/v1/experiments/{experiment_id}/leaderboard")

    assert response.status_code == 200
    assert response.json()["experiment_id"] == experiment_id
    assert response.json()["entries"][0]["candidate_id"]


def test_run_experiment_async_returns_queued_job() -> None:
    job_repository = InMemoryJobRepository()
    client, _provider, _evaluation_repository = _client(
        job_repository=job_repository
    )
    experiment_id = _create_experiment(client)

    response = client.post(
        f"/api/v1/experiments/{experiment_id}/run",
        json={
            "metric_specs": [{"name": "answer_relevance"}],
            "request_id": "request-1",
            "idempotency_key": "idem-1",
            "requested_by": "agent-1",
            "actor_type": "AGENT",
            "reason": "Run governed experiment",
            "submitted_by": "agent-1",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_type"] == "EXPERIMENT"
    assert payload["status"] == "QUEUED"
    assert payload["input_refs"]["operation"] == "experiment.run_async"
    assert payload["input_refs"]["experiment_id"] == experiment_id
    assert job_repository.find_by_id(payload["job_id"]) is not None


def test_run_experiment_without_candidates_returns_400() -> None:
    client, _provider, _evaluation_repository = _client()
    experiment_id = _create_experiment(client)

    response = client.post(
        f"/api/v1/experiments/{experiment_id}/run",
        json={},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_EXPERIMENT_REQUEST"


def test_run_experiment_with_unsupported_metric_returns_400() -> None:
    client, _provider, _evaluation_repository = _client()
    experiment_id = _create_experiment(client)
    _add_candidate(client, experiment_id)

    response = client.post(
        f"/api/v1/experiments/{experiment_id}/run",
        json={"metric_specs": [{"name": "toxicity"}]},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_METRIC"


def test_malformed_experiment_request_returns_422() -> None:
    client, _provider, _evaluation_repository = _client()

    response = client.post(
        "/api/v1/experiments",
        json={"name": "  ", "description": "description"},
    )

    assert response.status_code == 422


def test_experiment_endpoints_are_in_openapi() -> None:
    client, _provider, _evaluation_repository = _client()

    paths = client.get("/openapi.json").json()["paths"]

    assert "/api/v1/experiments" in paths
    assert "/api/v1/experiments/{experiment_id}" in paths
    assert "/api/v1/experiments/{experiment_id}/candidates" in paths
    assert "/api/v1/experiments/{experiment_id}/runs" in paths
    assert "/api/v1/experiments/{experiment_id}/run" in paths
    assert "/api/v1/experiments/{experiment_id}/leaderboard" in paths
    assert "/api/v1/experiments/{experiment_id}/comparison" in paths


def test_experiment_router_has_no_repository_or_provider_adapter_imports() -> None:
    source = Path("src/ai_governance/api/routers/experiments.py").read_text()

    assert "ai_governance.repositories" not in source
    assert "Repository" not in source
    assert "ai_governance.providers.trulens" not in source
    assert "import trulens" not in source
    assert "import openai" not in source
