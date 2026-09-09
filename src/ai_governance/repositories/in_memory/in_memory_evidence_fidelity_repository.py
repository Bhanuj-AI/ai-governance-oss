from __future__ import annotations

from threading import Lock

from ai_governance.domain.evidence_fidelity import EvidenceFidelityComparison
from ai_governance.repositories.evidence_fidelity_repository import (
    EvidenceFidelityComparisonRepository,
)


class InMemoryEvidenceFidelityComparisonRepository(EvidenceFidelityComparisonRepository):
    def __init__(self) -> None:
        self._items: dict[str, EvidenceFidelityComparison] = {}
        self._lock = Lock()

    def save(self, comparison: EvidenceFidelityComparison) -> EvidenceFidelityComparison:
        with self._lock:
            existing = self._items.get(comparison.comparison_id)
            if existing is not None and existing != comparison:
                raise ValueError("Evidence-fidelity comparisons are immutable.")
            duplicate = self.find_by_fingerprint(
                comparison.request_fingerprint,
                comparison.organization_id,
                comparison.project_id,
            )
            if duplicate is not None and duplicate.comparison_id != comparison.comparison_id:
                raise ValueError("Evidence-fidelity request fingerprint already exists.")
            self._items[comparison.comparison_id] = comparison
        return comparison

    def get(self, comparison_id: str, organization_id: str, project_id: str | None = None) -> EvidenceFidelityComparison | None:
        value = self._items.get(comparison_id)
        return value if value and value.organization_id == organization_id and value.project_id == project_id else None

    def find_by_fingerprint(self, fingerprint: str, organization_id: str, project_id: str | None = None) -> EvidenceFidelityComparison | None:
        return next((item for item in self._items.values() if item.request_fingerprint == fingerprint and item.organization_id == organization_id and item.project_id == project_id), None)

    def list_for_execution(self, execution_id: str, organization_id: str, project_id: str | None = None) -> list[EvidenceFidelityComparison]:
        return sorted((item for item in self._items.values() if item.source_execution_id == execution_id and item.organization_id == organization_id and item.project_id == project_id), key=lambda item: (item.created_at, item.comparison_id), reverse=True)
