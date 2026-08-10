import pytest

from ai_governance.ontology import (
    DuplicateOntologyRelationshipError,
    EntityType,
    InMemoryOntologyGraphRepository,
    InvalidOntologyRelationshipError,
    OntologyEntityNotFoundError,
    OntologyService,
    RelationshipType,
)
from ai_governance.ontology.synchronization.synchronizer import sync_relationship


def _service() -> OntologyService:
    repository = InMemoryOntologyGraphRepository()
    service = OntologyService(repository)
    service.create_entity(
        entity_id="experiment-1",
        entity_type=EntityType.EXPERIMENT,
        owner="owner",
        lifecycle="DRAFT",
    )
    service.create_entity(
        entity_id="candidate-1",
        entity_type=EntityType.CANDIDATE,
        owner="owner",
        lifecycle="CREATED",
    )
    service.create_entity(
        entity_id="prompt-v1",
        entity_type=EntityType.PROMPT_VERSION,
        owner="owner",
        lifecycle="ACTIVE",
    )
    service.create_entity(
        entity_id="model-v1",
        entity_type=EntityType.MODEL_VERSION,
        owner="owner",
        lifecycle="ACTIVE",
    )
    return service


def test_service_creates_valid_relationship() -> None:
    service = _service()

    relationship = service.create_relationship(
        source_type="Candidate",
        source_id="candidate-1",
        relationship_type="USES",
        target_type="PromptVersion",
        target_id="prompt-v1",
        created_by="tester",
    )

    assert service.get_relationship(relationship.relationship_id) == relationship


def test_service_rejects_invalid_relationship() -> None:
    service = _service()

    with pytest.raises(InvalidOntologyRelationshipError):
        service.create_relationship(
            source_type="Candidate",
            source_id="candidate-1",
            relationship_type="HAS_VERSION",
            target_type="PromptVersion",
            target_id="prompt-v1",
            created_by="tester",
        )


def test_service_rejects_missing_relationship_endpoint() -> None:
    service = _service()

    with pytest.raises(OntologyEntityNotFoundError):
        service.create_relationship(
            source_type="Candidate",
            source_id="missing-candidate",
            relationship_type="USES",
            target_type="PromptVersion",
            target_id="prompt-v1",
            created_by="tester",
        )


def test_service_rejects_duplicate_relationship() -> None:
    service = _service()
    service.create_relationship(
        source_type="Candidate",
        source_id="candidate-1",
        relationship_type="USES",
        target_type="PromptVersion",
        target_id="prompt-v1",
        created_by="tester",
    )

    with pytest.raises(DuplicateOntologyRelationshipError):
        service.create_relationship(
            source_type="Candidate",
            source_id="candidate-1",
            relationship_type="USES",
            target_type="PromptVersion",
            target_id="prompt-v1",
            created_by="tester",
        )


def test_synchronizer_reuses_existing_semantic_relationship() -> None:
    service = _service()
    existing = service.create_relationship(
        relationship_id="legacy-seed-relationship",
        source_type="Candidate",
        source_id="candidate-1",
        relationship_type="USES",
        target_type="PromptVersion",
        target_id="prompt-v1",
        created_by="seed",
    )

    relationship_id = sync_relationship(
        service,
        source_type=EntityType.CANDIDATE,
        source_id="candidate-1",
        relationship_type=RelationshipType.USES,
        target_type=EntityType.PROMPT_VERSION,
        target_id="prompt-v1",
        created_by="synchronizer",
    )

    assert relationship_id == existing.relationship_id


def test_service_hides_tombstoned_entities_from_live_relationship_writes() -> None:
    service = _service()
    service.create_relationship(
        source_type=EntityType.CANDIDATE,
        source_id="candidate-1",
        relationship_type=RelationshipType.USES,
        target_type=EntityType.PROMPT_VERSION,
        target_id="prompt-v1",
        created_by="tester",
    )
    service.delete_entity(EntityType.PROMPT_VERSION.value, "prompt-v1")

    tombstoned = service.get_entity(EntityType.PROMPT_VERSION.value, "prompt-v1")
    assert tombstoned is not None
    assert tombstoned.is_deleted is True
    assert (
        service.find_relationships(
            EntityType.CANDIDATE.value,
            "candidate-1",
            direction="outgoing",
        )
        == []
    )
    with pytest.raises(OntologyEntityNotFoundError):
        service.create_relationship(
            source_type=EntityType.CANDIDATE,
            source_id="candidate-1",
            relationship_type=RelationshipType.USES,
            target_type=EntityType.PROMPT_VERSION,
            target_id="prompt-v1",
            created_by="tester",
        )


def test_service_enforces_obvious_cardinality() -> None:
    service = _service()
    service.create_entity(
        entity_id="prompt-v2",
        entity_type=EntityType.PROMPT_VERSION,
        owner="owner",
        lifecycle="ACTIVE",
    )
    service.create_relationship(
        source_type=EntityType.CANDIDATE,
        source_id="candidate-1",
        relationship_type=RelationshipType.USES,
        target_type=EntityType.PROMPT_VERSION,
        target_id="prompt-v1",
        created_by="tester",
    )

    with pytest.raises(DuplicateOntologyRelationshipError):
        service.create_relationship(
            source_type=EntityType.CANDIDATE,
            source_id="candidate-1",
            relationship_type=RelationshipType.USES,
            target_type=EntityType.PROMPT_VERSION,
            target_id="prompt-v2",
            created_by="tester",
        )


def test_service_traversal_resolves_lineage_and_impact() -> None:
    service = _service()
    service.create_relationship(
        source_type=EntityType.EXPERIMENT,
        source_id="experiment-1",
        relationship_type=RelationshipType.HAS_CANDIDATE,
        target_type=EntityType.CANDIDATE,
        target_id="candidate-1",
        created_by="tester",
    )
    service.create_relationship(
        source_type=EntityType.CANDIDATE,
        source_id="candidate-1",
        relationship_type=RelationshipType.USES,
        target_type=EntityType.PROMPT_VERSION,
        target_id="prompt-v1",
        created_by="tester",
    )

    upstream = service.find_upstream("PromptVersion", "prompt-v1", depth=2)
    downstream = service.find_downstream("Experiment", "experiment-1", depth=2)
    neighbors = service.find_neighbors("Candidate", "candidate-1")

    assert [entity.entity_id for entity in upstream] == [
        "candidate-1",
        "experiment-1",
    ]
    assert [entity.entity_id for entity in downstream] == [
        "candidate-1",
        "prompt-v1",
    ]
    assert {entity.entity_id for entity in neighbors} == {
        "experiment-1",
        "prompt-v1",
    }
