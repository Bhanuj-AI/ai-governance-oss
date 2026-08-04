from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from kavach.domain.replay import Replay, ReplayStatus


@dataclass(frozen=True)
class ReplayListFilters:
    status: ReplayStatus | None = None
    source_execution_id: str | None = None
    requested_by: str | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    limit: int = 100


class ReplayRepository(ABC):
    """Tenant-scoped persistence boundary for Replay aggregates."""

    @abstractmethod
    def save(self, replay: Replay, expected_version: int | None = None) -> Replay:
        pass

    @abstractmethod
    def get(
        self, replay_id: str, organization_id: str, project_id: str
    ) -> Replay | None:
        pass

    @abstractmethod
    def list(
        self,
        filters: ReplayListFilters,
        organization_id: str,
        project_id: str,
    ) -> list[Replay]:
        pass

    @abstractmethod
    def find_by_idempotency(
        self,
        idempotency_key: str,
        organization_id: str,
        project_id: str,
    ) -> Replay | None:
        pass

    @abstractmethod
    def update(self, replay: Replay, expected_version: int) -> Replay:
        pass

    @abstractmethod
    def archive(self, replay: Replay, expected_version: int) -> Replay:
        pass
