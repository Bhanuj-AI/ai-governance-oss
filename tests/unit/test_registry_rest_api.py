from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from ai_governance.api.app import create_app
from ai_governance.api.dependencies import (
    get_dataset_registry_service,
    get_model_registry_service,
    get_prompt_registry_service,
    get_provider_registry_service,
)
from ai_governance.domain.datasets import Dataset, DatasetStatus
from ai_governance.domain.assets import AssetProvenance
from ai_governance.domain.models import Model, ModelStatus
from ai_governance.domain.prompts import Prompt, PromptStatus
from ai_governance.providers.errors import ProviderNotFoundError
from ai_governance.providers.provider_capabilities import ProviderCapabilities
from ai_governance.providers.provider_descriptor import ProviderDescriptor
from ai_governance.services.datasets import DatasetNotFoundError
from ai_governance.services.models import ModelNotFoundError
from ai_governance.services.prompts import PromptNotFoundError, PromptVersionConflictError
from ai_governance.api.demo_seed import _demo_evaluation_dataset_jsonl


class FakeProviderRegistryService:
    def __init__(self) -> None:
        self.provider = ProviderDescriptor(
            name="TruLens",
            display_name="TruLens",
            version="1.0.0",
            adapter_version="1.0.0",
            capabilities=ProviderCapabilities(
                supported_metrics=(
                    "answer_relevance",
                    "groundedness",
                ),
                supports_artifacts=True,
            ),
            metadata={"judge_model": "fake-judge"},
        )

    def list_providers(self) -> list[ProviderDescriptor]:
        return [self.provider]

    def get_provider(
        self,
        provider_name: str,
    ) -> ProviderDescriptor:
        if provider_name.lower() != "trulens":
            raise ProviderNotFoundError(
                f"Provider '{provider_name}' is not registered."
            )

        return self.provider


class FakePromptRegistryService:
    def __init__(self) -> None:
        self.prompt = Prompt(
            prompt_id="prompt-1",
            name="claim-decision",
            version="1.0.0",
            template="Classify claim: {{claim_text}}",
            variables=("claim_text",),
            created_at=datetime(2026, 6, 27, tzinfo=UTC),
            created_by="governance-admin",
            status=PromptStatus.ACTIVE,
        )

    def list_visible_prompts(self) -> list[Prompt]:
        return [self.prompt]

    def list_prompt_versions(
        self,
        name: str,
    ) -> list[Prompt]:
        if name != self.prompt.name:
            raise PromptNotFoundError(f"Prompt '{name}' does not exist.")

        return [self.prompt]

    def get_prompt(
        self,
        prompt_id: str,
    ) -> Prompt:
        if prompt_id != self.prompt.prompt_id:
            raise PromptNotFoundError(f"Prompt '{prompt_id}' does not exist.")

        return self.prompt

    def observe_prompt(self, **kwargs: object) -> Prompt:
        self.prompt = Prompt(
            prompt_id="observed-prompt-1",
            name=str(kwargs["name"]),
            version=str(kwargs["version"]),
            template=kwargs["template"] if isinstance(kwargs["template"], str) else None,
            variables=tuple(kwargs["variables"]),  # type: ignore[arg-type]
            created_at=datetime(2026, 7, 20, tzinfo=UTC),
            created_by=str(kwargs["observed_by"]),
            status=PromptStatus.ACTIVE,
            provenance=AssetProvenance.OBSERVED,
            source_system=str(kwargs["source_system"]),
            source_reference=kwargs["source_reference"] if isinstance(kwargs["source_reference"], str) else None,
            content_hash=str(kwargs["content_hash"]),
            content_available=kwargs["template"] is not None,
        )
        return self.prompt


class FakeModelRegistryService:
    def __init__(self) -> None:
        self.model = Model(
            model_id="model-1",
            provider="OpenAI",
            model_name="GPT-4.1",
            version="2026-06-25",
            parameters={"temperature": 0.0},
            cost={"input_per_1k": 0.01},
            latency=0.42,
            context_window=128000,
            creator="governance-admin",
            created_at=datetime(2026, 6, 27, tzinfo=UTC),
            status=ModelStatus.ACTIVE,
        )

    def list_models(self) -> list[Model]:
        return [self.model]

    def get_model(
        self,
        model_id: str,
    ) -> Model:
        if model_id != self.model.model_id:
            raise ModelNotFoundError(f"Model '{model_id}' does not exist.")

        return self.model

    def observe_model(self, **kwargs: object) -> Model:
        self.model = Model(
            model_id="observed-model-1",
            provider=str(kwargs["provider"]),
            model_name=str(kwargs["model_name"]),
            version=str(kwargs["version"]),
            parameters=dict(kwargs["parameters"]),  # type: ignore[arg-type]
            cost=kwargs["cost"] if isinstance(kwargs["cost"], dict) else None,
            latency=kwargs["latency"] if isinstance(kwargs["latency"], float) else None,
            context_window=int(kwargs["context_window"]),
            creator=str(kwargs["observed_by"]),
            created_at=datetime(2026, 7, 20, tzinfo=UTC),
            status=ModelStatus.ACTIVE,
            provenance=AssetProvenance.OBSERVED,
            source_system=str(kwargs["source_system"]),
            source_reference=kwargs["source_reference"] if isinstance(kwargs["source_reference"], str) else None,
        )
        return self.model


class FakeDatasetRegistryService:
    def __init__(self) -> None:
        self.dataset = Dataset(
            dataset_id="dataset-1",
            name="support-faq",
            version="2026-06-26",
            description="Baseline evaluation dataset",
            storage_uri="s3://datasets/support-faq.parquet",
            storage_type="S3",
            schema_version="v1",
            record_count=1500,
            checksum="sha256:abc123",
            creator="dataset-owner",
            created_at=datetime(2026, 6, 27, tzinfo=UTC),
            status=DatasetStatus.ACTIVE,
        )

    def list_datasets(self) -> list[Dataset]:
        return [self.dataset]

    def get_dataset(
        self,
        dataset_id: str,
    ) -> Dataset:
        if dataset_id != self.dataset.dataset_id:
            raise DatasetNotFoundError(
                f"Dataset '{dataset_id}' does not exist."
            )

        return self.dataset

    def list_versions(self, name: str) -> list[Dataset]:
        return [self.dataset] if name == self.dataset.name else []

    def register_dataset(
        self,
        *,
        name: str,
        version: str,
        description: str,
        storage_uri: str,
        storage_type: str,
        schema_version: str,
        record_count: int,
        checksum: str,
        creator: str,
        organization_id: str,
        project_id: str,
        dataset_id: str,
    ) -> Dataset:
        self.dataset = Dataset(
            dataset_id=dataset_id,
            name=name,
            version=version,
            description=description,
            storage_uri=storage_uri,
            storage_type=storage_type,
            schema_version=schema_version,
            record_count=record_count,
            checksum=checksum,
            creator=creator,
            created_at=datetime(2026, 7, 1, tzinfo=UTC),
            status=DatasetStatus.DRAFT,
            organization_id=organization_id,
            project_id=project_id,
        )
        return self.dataset


def _client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_provider_registry_service] = (
        FakeProviderRegistryService
    )
    app.dependency_overrides[get_prompt_registry_service] = (
        FakePromptRegistryService
    )
    app.dependency_overrides[get_model_registry_service] = (
        FakeModelRegistryService
    )
    app.dependency_overrides[get_dataset_registry_service] = (
        FakeDatasetRegistryService
    )
    return TestClient(app)


def test_list_providers() -> None:
    response = _client().get("/api/v1/providers")

    assert response.status_code == 200
    assert response.json()[0]["name"] == "trulens"
    assert response.json()[0]["display_name"] == "TruLens"
    assert response.json()[0]["capabilities"]["supported_metrics"] == [
        "answer_relevance",
        "groundedness",
    ]


def test_get_provider_normalizes_provider_name() -> None:
    response = _client().get("/api/v1/providers/TruLens")

    assert response.status_code == 200
    assert response.json()["name"] == "trulens"


def test_provider_not_found_returns_404() -> None:
    response = _client().get("/api/v1/providers/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_list_prompts_returns_metadata_without_template() -> None:
    response = _client().get("/api/v1/prompts")

    assert response.status_code == 200
    payload = response.json()[0]
    assert payload["prompt_id"] == "prompt-1"
    assert payload["name"] == "claim-decision"
    assert payload["variables"] == ["claim_text"]
    assert "template" not in payload


def test_list_prompt_versions_by_name() -> None:
    response = _client().get("/api/v1/prompts/claim-decision")

    assert response.status_code == 200
    assert response.json()[0]["version"] == "1.0.0"


def test_get_prompt_version_returns_template_for_registry_detail() -> None:
    response = _client().get("/api/v1/prompts/versions/prompt-1")

    assert response.status_code == 200
    assert response.json()["prompt_id"] == "prompt-1"
    assert response.json()["template"] == "Classify claim: {{claim_text}}"


def test_observe_prompt_accepts_hash_when_content_is_withheld() -> None:
    response = _client().post(
        "/api/v1/prompts/observations",
        json={
            "name": "support-assistant",
            "version": "v7",
            "source_system": "evaluation-sdk",
            "source_reference": "run-123",
            "content_hash": "sha256:abc123",
            "variables": ["question"],
        },
    )

    assert response.status_code == 201
    assert response.json()["provenance"] == "OBSERVED"
    assert response.json()["content_available"] is False
    assert response.json()["source_system"] == "evaluation-sdk"


def test_observe_prompt_requires_hash_when_content_is_withheld() -> None:
    response = _client().post(
        "/api/v1/prompts/observations",
        json={
            "name": "support-assistant",
            "version": "v7",
            "source_system": "evaluation-sdk",
        },
    )

    assert response.status_code == 422


def test_observe_prompt_conflict_returns_409() -> None:
    class ConflictPromptService:
        def observe_prompt(self, **kwargs: object) -> Prompt:
            raise PromptVersionConflictError("conflicting prompt evidence")

    app = create_app()
    app.dependency_overrides[get_prompt_registry_service] = ConflictPromptService
    client = TestClient(app)

    response = client.post(
        "/api/v1/prompts/observations",
        json={
            "name": "support-assistant",
            "version": "v7",
            "source_system": "evaluation-sdk",
            "content_hash": "sha256:abc123",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PromptVersionConflict"


def test_missing_prompt_version_returns_404() -> None:
    response = _client().get("/api/v1/prompts/versions/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_prompt_not_found_returns_404() -> None:
    response = _client().get("/api/v1/prompts/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_list_models() -> None:
    response = _client().get("/api/v1/models")

    assert response.status_code == 200
    assert response.json()[0]["model_id"] == "model-1"
    assert response.json()[0]["provider"] == "OpenAI"


def test_get_model() -> None:
    response = _client().get("/api/v1/models/model-1")

    assert response.status_code == 200
    assert response.json()["context_window"] == 128000


def test_observe_model_records_runtime_configuration() -> None:
    response = _client().post(
        "/api/v1/models/observations",
        json={
            "provider": "OpenAI",
            "model_name": "gpt-5",
            "version": "2026-06",
            "source_system": "evaluation-sdk",
            "parameters": {"temperature": 0.2},
            "context_window": 128000,
        },
    )

    assert response.status_code == 201
    assert response.json()["provenance"] == "OBSERVED"
    assert response.json()["parameters"] == {"temperature": 0.2}


def test_model_not_found_returns_404() -> None:
    response = _client().get("/api/v1/models/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_list_datasets() -> None:
    response = _client().get("/api/v1/datasets")

    assert response.status_code == 200
    assert response.json()[0]["dataset_id"] == "dataset-1"
    assert response.json()[0]["record_count"] == 1500


def test_get_dataset() -> None:
    response = _client().get("/api/v1/datasets/dataset-1")

    assert response.status_code == 200
    assert response.json()["storage_uri"] == "s3://datasets/support-faq.parquet"


def test_upload_dataset_writes_content_and_registers_draft(
    monkeypatch,
) -> None:
    class FakeObjectStore:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []
            self.deleted: list[tuple[str, str]] = []

        def put_stream(self, **kwargs: object):
            body = kwargs["body"]
            kwargs["uploaded_body"] = body.read()
            body.seek(0)
            self.calls.append(kwargs)
            from ai_governance.datasets import ObjectWriteResult

            return ObjectWriteResult(created=True)

        def delete_object(self, *, bucket: str, key: str) -> None:
            self.deleted.append((bucket, key))

    store = FakeObjectStore()
    monkeypatch.setattr(
        "ai_governance.api.routers.datasets.dataset_object_store_from_environment",
        lambda: store,
    )
    monkeypatch.setenv("AI_GOVERNANCE_DATASET_S3_BUCKET", "uploaded-datasets")

    response = _client().post(
        "/api/v1/datasets/upload",
        data={
            "name": "support-upload",
            "version": "v1.0",
            "description": "Uploaded support evaluation set",
            "schema_version": "1.0",
        },
        files={
            "file": ("support.jsonl", b'{"question":"How do I reset?"}\n', "application/x-ndjson"),
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["name"] == "support-upload"
    assert payload["status"] == "DRAFT"
    assert payload["record_count"] == 1
    assert payload["storage_uri"].startswith("s3://uploaded-datasets/datasets/")
    assert payload["checksum"].startswith("sha256:")
    assert store.calls[0]["bucket"] == "uploaded-datasets"
    assert store.calls[0]["uploaded_body"] == b'{"question":"How do I reset?"}\n'
    assert store.calls[0]["metadata"]["dataset_id"] == payload["dataset_id"]
    assert payload["storage_uri"].endswith(f"/{payload['checksum'].removeprefix('sha256:')}.jsonl")


def test_upload_dataset_requires_configured_object_store() -> None:
    response = _client().post(
        "/api/v1/datasets/upload",
        data={
            "name": "support-upload",
            "version": "v1.0",
            "description": "Uploaded support evaluation set",
        },
        files={"file": ("support.csv", b"question\nHow do I reset?\n", "text/csv")},
    )

    assert response.status_code == 503


def test_upload_dataset_rejects_duplicate_content_for_new_version(
    monkeypatch,
) -> None:
    class FakeObjectStore:
        def put_stream(self, **kwargs: object):
            from ai_governance.datasets import ObjectWriteResult

            return ObjectWriteResult(created=True)

        def delete_object(self, *, bucket: str, key: str) -> None:
            raise AssertionError("duplicate uploads should not write an object")

    monkeypatch.setattr(
        "ai_governance.api.routers.datasets.dataset_object_store_from_environment",
        lambda: FakeObjectStore(),
    )
    app = create_app()
    registry_service = FakeDatasetRegistryService()
    app.dependency_overrides[get_dataset_registry_service] = lambda: registry_service
    client = TestClient(app)
    fields = {"name": "support-upload", "description": "Uploaded support evaluation set"}
    file = {"file": ("support.jsonl", b'{"question":"How do I reset?"}\n', "application/x-ndjson")}

    assert client.post("/api/v1/datasets/upload", data={**fields, "version": "v1.0"}, files=file).status_code == 201
    response = client.post("/api/v1/datasets/upload", data={**fields, "version": "v1.1"}, files=file)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DatasetVersionConflict"


def test_upload_dataset_deletes_new_object_when_registry_registration_fails(
    monkeypatch,
) -> None:
    class FakeObjectStore:
        def __init__(self) -> None:
            self.deleted: list[tuple[str, str]] = []

        def put_stream(self, **kwargs: object):
            from ai_governance.datasets import ObjectWriteResult

            return ObjectWriteResult(created=True)

        def delete_object(self, *, bucket: str, key: str) -> None:
            self.deleted.append((bucket, key))

    class FailingRegistry:
        def list_versions(self, name: str) -> list[Dataset]:
            return []

        def register_dataset(self, **kwargs: object) -> Dataset:
            from ai_governance.services.datasets import DatasetVersionConflictError

            raise DatasetVersionConflictError("Concurrent dataset version registration.")

    store = FakeObjectStore()
    monkeypatch.setattr(
        "ai_governance.api.routers.datasets.dataset_object_store_from_environment",
        lambda: store,
    )
    app = create_app()
    app.dependency_overrides[get_dataset_registry_service] = FailingRegistry
    response = TestClient(app).post(
        "/api/v1/datasets/upload",
        data={"name": "support-upload", "version": "v1.0", "description": "Upload"},
        files={"file": ("support.csv", b"question\nHow do I reset?\n", "text/csv")},
    )

    assert response.status_code == 409
    assert len(store.deleted) == 1
    assert store.deleted[0][0] == "ai-governance-datasets"
    assert store.deleted[0][1].startswith("datasets/org-default/project-default/")


def test_dataset_not_found_returns_404() -> None:
    response = _client().get("/api/v1/datasets/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_registry_resources_are_in_openapi() -> None:
    response = _client().get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/providers" in paths
    assert "/api/v1/providers/{provider_name}" in paths
    assert "/api/v1/prompts" in paths
    assert "/api/v1/prompts/{name}" in paths
    assert "/api/v1/prompts/versions/{prompt_id}" in paths
    assert "/api/v1/models" in paths
    assert "/api/v1/models/{model_id}" in paths
    assert "/api/v1/datasets" in paths
    assert "/api/v1/datasets/{dataset_id}" in paths


def test_seeded_evaluation_dataset_content_has_expected_record_count() -> None:
    rows = _demo_evaluation_dataset_jsonl().decode().splitlines()

    assert len(rows) == 120
    assert '"question": "Demo support question 1"' in rows[0]


def test_registry_routers_do_not_import_repositories_directly() -> None:
    router_dir = Path("src/ai_governance/api/routers")

    for router_file in router_dir.glob("*.py"):
        source = router_file.read_text()

        assert "ai_governance.repositories" not in source
        assert "Repository" not in source
