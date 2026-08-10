import os
from uuid import uuid4

import pytest

from ai_governance.ontology import EntityType, OntologyService, RelationshipType


def _neo4j_available() -> bool:
    if os.getenv("AI_GOVERNANCE_RUN_NEO4J_TESTS") != "true":
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
            "Set AI_GOVERNANCE_RUN_NEO4J_TESTS=true and install/start Neo4j to run."
        ),
    ),
]


def test_basic_graph_traversal_against_neo4j():
    from ai_governance.ontology.neo4j_repository import Neo4jOntologyGraphRepository

    repository = Neo4jOntologyGraphRepository.from_environment()
    suffix = str(uuid4())
    experiment_id = f"experiment-{suffix}"
    candidate_id = f"candidate-{suffix}"
    prompt_id = f"prompt-{suffix}"

    try:
        repository.initialize_schema()
        service = OntologyService(repository)
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

        neighbors = service.find_neighbors("Candidate", candidate_id)

        assert {entity.entity_id for entity in neighbors} == {
            experiment_id,
            prompt_id,
        }
    finally:
        repository.close()
