from __future__ import annotations

ONTOLOGY_SCHEMA_CYPHER = (
    """
    CREATE CONSTRAINT ontology_entity_unique IF NOT EXISTS
    FOR (e:OntologyEntity)
    REQUIRE (e.organization_id, e.project_id, e.entity_type, e.entity_id) IS UNIQUE
    """,
    """
    CREATE CONSTRAINT ontology_relationship_unique IF NOT EXISTS
    FOR ()-[r]-()
    REQUIRE (r.organization_id, r.project_id, r.relationship_id) IS UNIQUE
    """,
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
