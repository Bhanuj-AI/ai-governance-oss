from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from ai_governance.domain.replay import ReplayResult


@dataclass(frozen=True)
class ReplayResultListFilters:
    source_execution_id: str | None = None
    replay_execution_id: str | None = None
    drift_severity: str | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    limit: int = 100
    cursor: str | None = None


class ReplayResultRepository(ABC):
    @abstractmethod
    def save(self, result: ReplayResult) -> ReplayResult: ...

    @abstractmethod
    def get(
        self, result_id: str, organization_id: str, project_id: str
    ) -> ReplayResult | None: ...

    @abstractmethod
    def get_by_replay(
        self, replay_id: str, organization_id: str, project_id: str
    ) -> ReplayResult | None: ...

    @abstractmethod
    def list(
        self,
        filters: ReplayResultListFilters,
        organization_id: str,
        project_id: str,
    ) -> list[ReplayResult]: ...
