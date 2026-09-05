from __future__ import annotations

from abc import ABC, abstractmethod

from ai_governance.domain.causal_audit import EvidenceInterventionPolicy


class EvidenceInterventionPolicyRepository(ABC):
    @abstractmethod
    def save(
        self, policy: EvidenceInterventionPolicy
    ) -> EvidenceInterventionPolicy: ...

    @abstractmethod
    def get(
        self, policy_id: str, version: int, organization_id: str, project_id: str | None
    ) -> EvidenceInterventionPolicy | None: ...

    @abstractmethod
    def list(
        self, organization_id: str, project_id: str | None
    ) -> list[EvidenceInterventionPolicy]: ...
