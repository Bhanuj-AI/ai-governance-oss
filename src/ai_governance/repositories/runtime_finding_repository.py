"""Repository interfaces for runtime findings."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from ai_governance.domain.runtime_findings.finding import (
    FindingSeverity,
    FindingStatus,
    ReconciliationWindow,
    RuntimeFinding,
)


@dataclass(frozen=True)
class RuntimeFindingListFilters:
    """Filters for listing runtime findings."""

    finding_type: str | None = None
    subject_type: str | None = None
    subject_id: str | None = None
    severity: FindingSeverity | None = None
    status: FindingStatus | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    limit: int = 100


@dataclass(frozen=True)
class RuntimeFindingCursor:
    """Stable cursor for bounded scans of a finding lifecycle state."""

    created_at: datetime
    finding_id: str


@dataclass(frozen=True)
class RuntimeFindingPage:
    items: tuple[RuntimeFinding, ...]
    next_cursor: RuntimeFindingCursor | None


class RuntimeFindingRepository(ABC):
    """Persistence boundary for runtime findings."""

    @abstractmethod
    def save(self, finding: RuntimeFinding) -> RuntimeFinding:
        """Save or update a finding."""

    @abstractmethod
    def get(
        self,
        finding_id: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> RuntimeFinding | None:
        """Retrieve one finding by ID."""

    @abstractmethod
    def list(
        self,
        filters: RuntimeFindingListFilters,
        organization_id: str,
        project_id: str | None = None,
    ) -> list[RuntimeFinding]:
        """List findings matching filters."""

    @abstractmethod
    def find_by_dedup_key(
        self,
        dedup_key: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> RuntimeFinding | None:
        """Find an existing finding by deduplication key."""

    @abstractmethod
    def list_by_status(
        self,
        status: FindingStatus,
        organization_id: str,
        project_id: str | None = None,
        limit: int = 100,
    ) -> list[RuntimeFinding]:
        """List findings by status."""

    @abstractmethod
    def page_by_status(
        self,
        status: FindingStatus,
        organization_id: str,
        project_id: str | None = None,
        cursor: RuntimeFindingCursor | None = None,
        limit: int = 100,
    ) -> RuntimeFindingPage:
        """Read a stable, bounded lifecycle-state page within tenant scope."""

    @abstractmethod
    def finalized_windows_covering(
        self,
        occurred_at: datetime,
        organization_id: str,
        project_id: str | None = None,
    ) -> tuple[ReconciliationWindow, ...]:
        """Return persisted finalized decision windows covering an event in tenant scope.

        These are immutable historical decision contracts.  Callers must use
        their recorded cutoff rather than current settings; a legacy window
        without a snapshot must be handled conservatively, never as on-time.
        """

    @abstractmethod
    def count_by_subject(
        self,
        subject_type: str,
        subject_id: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> int:
        """Count findings for a subject."""
