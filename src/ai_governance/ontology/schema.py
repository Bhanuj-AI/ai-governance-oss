from __future__ import annotations

from ai_governance.ontology.enums import RelationshipType


def _relationship_uniqueness_constraint(relationship_type: RelationshipType) -> str:
    """Return Neo4j's relationship-type-scoped uniqueness constraint."""

    constraint_name = f"ontology_relationship_unique_{relationship_type.value.lower()}"
    return f"""
    CREATE CONSTRAINT {constraint_name} IF NOT EXISTS
    FOR ()-[r:{relationship_type.value}]-()
    REQUIRE (r.organization_id, r.project_id, r.relationship_id) IS UNIQUE
    """


ONTOLOGY_RELATIONSHIP_UNIQUENESS_CYPHER = tuple(
    _relationship_uniqueness_constraint(relationship_type)
    for relationship_type in RelationshipType
)

ONTOLOGY_SCHEMA_CYPHER = (
    """
    CREATE CONSTRAINT ontology_entity_unique IF NOT EXISTS
    FOR (e:OntologyEntity)
    REQUIRE (e.organization_id, e.project_id, e.entity_type, e.entity_id) IS UNIQUE
    """,
    *ONTOLOGY_RELATIONSHIP_UNIQUENESS_CYPHER,
    """
    CREATE INDEX ontology_entity_type IF NOT EXISTS
    FOR (e:OntologyEntity)
    ON (e.entity_type)
    """,
    """
    CREATE INDEX ontology_entity_version IF NOT EXISTS
    FOR (e:OntologyEntity)
    ON (e.ontology_version)
    """,
    """
    CREATE INDEX ontology_entity_tenant IF NOT EXISTS
    FOR (e:OntologyEntity)
    ON (e.organization_id, e.project_id)
    """,
)


ENTITY_SEARCH_INDEX_NAME = "ontology_entity_search"
ENTITY_SEARCH_INDEX_PROPERTIES = (
    "entity_id",
    "entity_type",
    "owner",
    "immutable_attributes_json",
    "mutable_attributes_json",
    "metadata_json",
)
ONTOLOGY_ENTITY_SEARCH_INDEX_CYPHER = """
CREATE FULLTEXT INDEX ontology_entity_search IF NOT EXISTS
FOR (e:OntologyEntity)
ON EACH [
    e.entity_id,
    e.entity_type,
    e.owner,
    e.immutable_attributes_json,
    e.mutable_attributes_json,
    e.metadata_json
]
"""


def initialize_ontology_schema(repository: object) -> None:
    """
    Initialize ontology graph schema through a repository adapter.

    The helper keeps callers from reaching into repository internals. A
    repository that supports schema initialization exposes `initialize_schema`.
    """

    initializer = getattr(repository, "initialize_schema", None)
    if initializer is None:
        raise TypeError("Repository does not support schema initialization.")
    initializer()

    search_index_initializer = getattr(repository, "ensure_entity_search_index", None)
    if search_index_initializer is not None:
        search_index_initializer()
