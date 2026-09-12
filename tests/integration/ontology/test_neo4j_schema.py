import os
from uuid import uuid4

import pytest

from ai_governance.ontology import RelationshipType

pytestmark = pytest.mark.integration


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


def test_neo4j_schema_initialization_creates_indexes_and_constraints():
    from ai_governance.ontology.neo4j_repository import Neo4jOntologyGraphRepository

    repository = Neo4jOntologyGraphRepository.from_environment()
    try:
        repository.initialize_schema()
        repository.ensure_entity_search_index()
        with repository._session() as session:
            rows = list(session.run("SHOW INDEXES YIELD name RETURN name"))
        names = {row["name"] for row in rows}
    finally:
        repository.close()

    assert "ontology_entity_unique" in names
    for relationship_type in RelationshipType:
        assert (
            f"ontology_relationship_unique_{relationship_type.value.lower()}" in names
        )
    assert "ontology_entity_type" in names
    assert "ontology_entity_version" in names
    assert "ontology_entity_search" in names


def test_entity_search_index_finds_a_node_persisted_before_the_index_migration():
    from ai_governance.ontology import EntityType, OntologyEntity
    from ai_governance.ontology.neo4j_repository import (
        Neo4jOntologyGraphQueryRepository,
        Neo4jOntologyGraphRepository,
    )

    repository = Neo4jOntologyGraphRepository.from_environment()
    entity_id = f"searchable-model-{uuid4()}"
    try:
        repository.save_entity(
            OntologyEntity(
                entity_id=entity_id,
                entity_type=EntityType.MODEL_VERSION,
                owner="integration-test",
                lifecycle="ACTIVE",
                metadata={"display_name": "Searchable Risk Model"},
            )
        )
        repository.ensure_entity_search_index()

        page = Neo4jOntologyGraphQueryRepository(repository).search_entities(
            "Searchable Risk Model",
            entity_types=(EntityType.MODEL_VERSION.value,),
        )
    finally:
        repository.close()

    assert entity_id in [entity.entity_id for entity in page.items]
