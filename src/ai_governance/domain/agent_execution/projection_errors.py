"""Domain errors for runtime ontology projection."""

from __future__ import annotations


class ProjectionError(Exception):
    """Base error for projection failures."""


class ProjectionNotFound(ProjectionError):
    """Projection record does not exist for the given execution."""

    def __init__(self, execution_id: str) -> None:
        super().__init__(f"Projection not found for execution '{execution_id}'.")
        self.execution_id = execution_id


class ProjectionConflict(ProjectionError):
    """Projection state conflict — e.g. stale version mismatch."""

    def __init__(self, execution_id: str, message: str) -> None:
        super().__init__(f"Projection conflict for execution '{execution_id}': {message}")
        self.execution_id = execution_id


class Neo4jWriteError(ProjectionError):
    """Neo4j write failed — graph unavailable or Cypher error."""

    def __init__(self, execution_id: str, cause: Exception) -> None:
        super().__init__(f"Neo4j write failed for execution '{execution_id}': {cause}")
        self.execution_id = execution_id
        self.cause = cause
