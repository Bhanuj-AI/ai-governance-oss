from __future__ import annotations


class OntologyError(Exception):
    """
    Base exception for ontology model, validation, and repository failures.
    """


class InvalidOntologyEntityError(OntologyError):
    """
    Raised when an ontology entity has an unknown type or invalid identity.
    """


class InvalidOntologyRelationshipError(OntologyError):
    """
    Raised when a relationship violates the ontology taxonomy.
    """


class DuplicateOntologyRelationshipError(OntologyError):
    """
    Raised when a relationship would duplicate an existing unique edge.
    """


class OntologyEntityNotFoundError(OntologyError):
    """
    Raised when a service operation references a missing ontology entity.
    """


class OntologyRepositoryError(OntologyError):
    """
    Raised when a graph repository cannot complete a persistence operation.
    """


class MissingNeo4jDriverError(OntologyRepositoryError):
    """
    Raised when the Neo4j adapter is used without the Neo4j Python driver.
    """
