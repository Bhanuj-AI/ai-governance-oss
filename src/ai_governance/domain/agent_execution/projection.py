"""Runtime ontology projection domain model.

Tracks the projection state of an AgentExecution into Neo4j and
captures unresolved references that need reconciliation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class ProjectionStatus(str, Enum):
    """Lifecycle of a runtime-to-graph projection."""

    PENDING = "PENDING"
    PROJECTED = "PROJECTED"
    FAILED = "FAILED"


class ProjectionVersion(str, Enum):
    """Projection schema version — evolves independently of event schema."""

    V1 = "1"


@dataclass(frozen=True)
class UnresolvedReference:
    """A reference found in events that could not be resolved to a graph entity."""

    reference_type: str  # e.g. "model", "tool", "governed_asset", "policy"
    reference_id: str
    source_event_id: str


@dataclass(frozen=True)
class RuntimeOntologyProjection:
    """Projection state for one AgentExecution in Neo4j.

    This aggregate tracks whether an execution has been projected,
    what version was used, and any unresolved references.

    Attributes:
        execution_id: Parent AgentExecution ID (graph node key).
        organization_id: Tenant scope.
        project_id: Project scope.
        status: Current projection lifecycle state.
        projection_version: Schema version used for this projection.
        source_version: Source execution version at time of projection.
        relationships_projected: Count of relationships written to graph.
        unresolved_references: References that could not be resolved.
        last_projected_at: When the projection was last written.
        created_at: First projection attempt timestamp.
        updated_at: Last state transition timestamp.
    """

    execution_id: str
    organization_id: str
    project_id: str | None = None
    status: ProjectionStatus = ProjectionStatus.PENDING
    projection_version: str = ProjectionVersion.V1.value
    source_version: int = 0
    relationships_projected: int = 0
    unresolved_references: tuple[UnresolvedReference, ...] = field(default_factory=tuple)
    last_projected_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.execution_id.strip():
            raise ValueError("execution_id must not be empty.")
        if not self.organization_id.strip():
            raise ValueError("organization_id must not be empty.")

    def mark_projected(
        self,
        relationships_projected: int,
        unresolved: tuple[UnresolvedReference, ...] | None = None,
        now: datetime | None = None,
    ) -> RuntimeOntologyProjection:
        """Transition to PROJECTED with counts."""
        now = now or datetime.now(UTC)
        return RuntimeOntologyProjection(
            execution_id=self.execution_id,
            organization_id=self.organization_id,
            project_id=self.project_id,
            status=ProjectionStatus.PROJECTED,
            projection_version=self.projection_version,
            source_version=self.source_version,
            relationships_projected=relationships_projected,
            unresolved_references=unresolved or self.unresolved_references,
            last_projected_at=now,
            created_at=self.created_at,
            updated_at=now,
        )

    def mark_failed(self, now: datetime | None = None) -> RuntimeOntologyProjection:
        """Transition to FAILED."""
        now = now or datetime.now(UTC)
        return RuntimeOntologyProjection(
            execution_id=self.execution_id,
            organization_id=self.organization_id,
            project_id=self.project_id,
            status=ProjectionStatus.FAILED,
            projection_version=self.projection_version,
            source_version=self.source_version,
            relationships_projected=self.relationships_projected,
            unresolved_references=self.unresolved_references,
            last_projected_at=None,
            created_at=self.created_at,
            updated_at=now,
        )

    def mark_pending(self, now: datetime | None = None) -> RuntimeOntologyProjection:
        """Reset to PENDING for retry."""
        now = now or datetime.now(UTC)
        return RuntimeOntologyProjection(
            execution_id=self.execution_id,
            organization_id=self.organization_id,
            project_id=self.project_id,
            status=ProjectionStatus.PENDING,
            projection_version=self.projection_version,
            source_version=self.source_version,
            relationships_projected=0,
            unresolved_references=(),
            last_projected_at=None,
            created_at=self.created_at,
            updated_at=now,
        )

    @property
    def is_terminal(self) -> bool:
        return self.status in (ProjectionStatus.PROJECTED, ProjectionStatus.FAILED)

    def is_stale(self, source_version: int) -> bool:
        """Whether the projection is stale relative to the source execution version."""
        return self.status == ProjectionStatus.PROJECTED and self.source_version < source_version

    @property
    def unresolved_count(self) -> int:
        return len(self.unresolved_references)
