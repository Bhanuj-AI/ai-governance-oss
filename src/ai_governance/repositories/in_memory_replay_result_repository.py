from __future__ import annotations

from ai_governance.domain.replay import ReplayResult
from ai_governance.domain.replay.errors import ReplayResultConflict
from ai_governance.repositories.replay_result_repository import (
    ReplayResultListFilters,
    ReplayResultRepository,
)


class InMemoryReplayResultRepository(ReplayResultRepository):
    def __init__(self) -> None:
        self._results: dict[str, ReplayResult] = {}

    def save(self, result: ReplayResult) -> ReplayResult:
        existing = self._results.get(result.result_id)
        if existing is not None:
            if existing == result:
                return existing
            raise ReplayResultConflict("Replay result ID is already bound to other evidence.")
        replay_result = self.get_by_replay(
            result.replay_id, result.organization_id, result.project_id
        )
        if replay_result is not None:
            if replay_result == result:
                return replay_result
            raise ReplayResultConflict("A finalized ReplayResult already exists for replay.")
        self._results[result.result_id] = result
        return result

    def get(self, result_id: str, organization_id: str, project_id: str) -> ReplayResult | None:
        result = self._results.get(result_id)
        return result if result and result.organization_id == organization_id and result.project_id == project_id else None

    def get_by_replay(self, replay_id: str, organization_id: str, project_id: str) -> ReplayResult | None:
        return next((result for result in self._results.values() if result.replay_id == replay_id and result.organization_id == organization_id and result.project_id == project_id), None)

    def list(self, filters: ReplayResultListFilters, organization_id: str, project_id: str) -> list[ReplayResult]:
        results = [
            result for result in self._results.values()
            if result.organization_id == organization_id and result.project_id == project_id
            and (filters.source_execution_id is None or result.source_execution_id == filters.source_execution_id)
            and (filters.replay_execution_id is None or result.replay_execution_id == filters.replay_execution_id)
            and (filters.drift_severity is None or result.drift_summary.severity == filters.drift_severity)
            and (filters.created_after is None or result.created_at >= filters.created_after)
            and (filters.created_before is None or result.created_at <= filters.created_before)
        ]
        results.sort(key=lambda result: (result.created_at, result.result_id), reverse=True)
        if filters.cursor:
            results = [result for result in results if result.result_id < filters.cursor]
        return results[: filters.limit]
