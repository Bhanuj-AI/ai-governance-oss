import os

import pytest

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
        with repository._session() as session:
            rows = list(session.run("SHOW INDEXES YIELD name RETURN name"))
        names = {row["name"] for row in rows}
    finally:
        repository.close()

    assert "ontology_entity_unique" in names
    assert "ontology_entity_type" in names
    assert "ontology_entity_version" in names
