"""Persistence boundary for immutable evidence-fidelity comparisons."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ai_governance.domain.evidence_fidelity import EvidenceFidelityComparison


class EvidenceFidelityComparisonRepository(ABC):
    @abstractmethod
    def save(self, comparison: EvidenceFidelityComparison) -> EvidenceFidelityComparison: ...

    @abstractmethod
    def get(
        self, comparison_id: str, organization_id: str, project_id: str | None = None
    ) -> EvidenceFidelityComparison | None: ...

    @abstractmethod
    def find_by_fingerprint(
        self, fingerprint: str, organization_id: str, project_id: str | None = None
    ) -> EvidenceFidelityComparison | None: ...

    @abstractmethod
    def list_for_execution(
        self, execution_id: str, organization_id: str, project_id: str | None = None
    ) -> list[EvidenceFidelityComparison]: ...
