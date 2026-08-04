import os
from uuid import uuid4

import pytest

from kavach.ontology import EntityType, OntologyService, RelationshipType

pytestmark = pytest.mark.integration


def _neo4j_available() -> bool:
    if os.getenv("KAVACH_RUN_NEO4J_TESTS") != "true":
        return False
    try:
        import neo4j  # type: ignore # noqa: F401
    except ImportError:
        return False
    return True


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _neo4j_available(),
        reason=(
            "Set KAVACH_RUN_NEO4J_TESTS=true and install/start Neo4j to run."
        ),
    ),
]


@pytest.fixture()
def ontology_service():
    from kavach.ontology.neo4j_repository import Neo4jOntologyGraphRepository

    repository = Neo4jOntologyGraphRepository.from_environment()
    repository.initialize_schema()
    suffix = str(uuid4())
    service = OntologyService(repository)
    yield service, repository, suffix
    repository.close()


def test_neo4j_repository_saves_entity_and_relationship(ontology_service):
    service, _repository, suffix = ontology_service
    candidate_id = f"candidate-{suffix}"
    prompt_id = f"prompt-{suffix}"

    service.create_entity(
        entity_id=candidate_id,
        entity_type=EntityType.CANDIDATE,
        owner="integration-test",
        lifecycle="CREATED",
    )
    service.create_entity(
        entity_id=prompt_id,
        entity_type=EntityType.PROMPT_VERSION,
        owner="integration-test",
        lifecycle="ACTIVE",
    )
    relationship = service.create_relationship(
        source_type=EntityType.CANDIDATE,
        source_id=candidate_id,
        relationship_type=RelationshipType.USES,
        target_type=EntityType.PROMPT_VERSION,
        target_id=prompt_id,
        created_by="integration-test",
    )

    assert service.get_entity("Candidate", candidate_id) is not None
    assert service.get_relationship(relationship.relationship_id) == relationship


def test_neo4j_repository_traversal(ontology_service):
    service, _repository, suffix = ontology_service
    experiment_id = f"experiment-{suffix}"
    candidate_id = f"candidate-{suffix}"
    prompt_id = f"prompt-{suffix}"

    service.create_entity(
        entity_id=experiment_id,
        entity_type=EntityType.EXPERIMENT,
        owner="integration-test",
        lifecycle="DRAFT",
    )
    service.create_entity(
        entity_id=candidate_id,
        entity_type=EntityType.CANDIDATE,
        owner="integration-test",
        lifecycle="CREATED",
    )
    service.create_entity(
        entity_id=prompt_id,
        entity_type=EntityType.PROMPT_VERSION,
        owner="integration-test",
        lifecycle="ACTIVE",
    )
    service.create_relationship(
        source_type=EntityType.EXPERIMENT,
        source_id=experiment_id,
        relationship_type=RelationshipType.HAS_CANDIDATE,
        target_type=EntityType.CANDIDATE,
        target_id=candidate_id,
        created_by="integration-test",
    )
    service.create_relationship(
        source_type=EntityType.CANDIDATE,
        source_id=candidate_id,
        relationship_type=RelationshipType.USES,
        target_type=EntityType.PROMPT_VERSION,
        target_id=prompt_id,
        created_by="integration-test",
    )

    assert {
        entity.entity_id for entity in service.find_downstream(
            "Experiment",
            experiment_id,
            depth=2,
        )
    } == {candidate_id, prompt_id}
    assert {
        entity.entity_id for entity in service.find_upstream(
            "PromptVersion",
            prompt_id,
            depth=2,
        )
    } == {candidate_id, experiment_id}
