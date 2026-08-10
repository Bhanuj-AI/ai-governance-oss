from datetime import UTC, datetime

from ai_governance.domain.datasets import Dataset, DatasetStatus
from ai_governance.domain.models import Model, ModelStatus
from ai_governance.domain.prompts import Prompt, PromptStatus
from ai_governance.ontology import (
    EntityType,
    InMemoryOntologyGraphRepository,
    OntologyService,
    RelationshipType,
)
from ai_governance.ontology.synchronization import (
    DatasetOntologySynchronizer,
    ModelOntologySynchronizer,
    PromptOntologySynchronizer,
)
from ai_governance.ontology.synchronization.synchronizer import (
    logical_prompt_id,
)
from ai_governance.repositories.in_memory_dataset_repository import (
    InMemoryDatasetRepository,
)
from ai_governance.repositories.in_memory_model_repository import (
    InMemoryModelRepository,
)
from ai_governance.repositories.in_memory_prompt_repository import (
    InMemoryPromptRepository,
)


def test_prompt_synchronization_is_idempotent_and_projects_relationships() -> None:
    repository = InMemoryPromptRepository()
    prompt = Prompt(
        prompt_id="prompt-1",
        name="support",
        version="v1",
        template="Hello {name}",
        variables=("name",),
        created_at=datetime(2026, 6, 30, tzinfo=UTC),
        created_by="prompt-owner",
        status=PromptStatus.DRAFT,
    )
    repository.save(prompt)
    service = OntologyService(InMemoryOntologyGraphRepository())
    synchronizer = PromptOntologySynchronizer(service, repository)

    first = synchronizer.synchronize(prompt)
    second = synchronizer.synchronize(prompt)

    assert first.succeeded is True
    assert second.succeeded is True
    assert service.get_entity("PromptVersion", "prompt-1") is not None
    assert service.get_entity("Prompt", logical_prompt_id("support")) is not None
    relationships = service.find_relationships(
        "PromptVersion",
        "prompt-1",
        direction="outgoing",
    )
    assert {
        relationship.relationship_type for relationship in relationships
    } == {
        RelationshipType.VERSION_OF.value,
        RelationshipType.CREATED_BY.value,
        RelationshipType.OWNED_BY.value,
    }


def test_prompt_delete_archives_projection_without_hard_delete() -> None:
    prompt = Prompt(
        prompt_id="prompt-1",
        name="support",
        version="v1",
        template="Hello",
        variables=(),
        created_at=datetime(2026, 6, 30, tzinfo=UTC),
        created_by="prompt-owner",
        status=PromptStatus.ACTIVE,
    )
    service = OntologyService(InMemoryOntologyGraphRepository())
    synchronizer = PromptOntologySynchronizer(service)
    synchronizer.synchronize(prompt)

    result = synchronizer.delete(prompt)

    entity = service.get_entity("PromptVersion", "prompt-1")
    assert result.succeeded is True
    assert entity is not None
    assert entity.lifecycle == "ARCHIVED"


def test_model_and_dataset_synchronizers_project_version_entities() -> None:
    service = OntologyService(InMemoryOntologyGraphRepository())
    model_repository = InMemoryModelRepository()
    dataset_repository = InMemoryDatasetRepository()
    model = Model(
        model_id="model-1",
        provider="mock",
        model_name="answerer",
        version="v1",
        parameters={"temperature": 0},
        cost=None,
        latency=None,
        context_window=8192,
        creator="model-owner",
        created_at=datetime(2026, 6, 30, tzinfo=UTC),
        status=ModelStatus.ACTIVE,
    )
    dataset = Dataset(
        dataset_id="dataset-1",
        name="support-eval",
        version="v1",
        description="baseline",
        storage_uri="file://dataset.jsonl",
        storage_type="jsonl",
        schema_version="v1",
        record_count=10,
        checksum="sha256:abc",
        creator="dataset-owner",
        created_at=datetime(2026, 6, 30, tzinfo=UTC),
        status=DatasetStatus.FROZEN,
    )
    model_repository.save(model)
    dataset_repository.save(dataset)

    model_result = ModelOntologySynchronizer(
        service,
        model_repository,
    ).synchronize(model)
    dataset_result = DatasetOntologySynchronizer(
        service,
        dataset_repository,
    ).synchronize(dataset)

    assert model_result.succeeded is True
    assert dataset_result.succeeded is True
    assert service.get_entity(EntityType.MODEL_VERSION.value, "model-1")
    assert service.get_entity(EntityType.DATASET_VERSION.value, "dataset-1")
