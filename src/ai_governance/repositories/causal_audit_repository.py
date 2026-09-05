from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from ai_governance.domain.causal_audit import (
    CausalAudit,
    CausalAuditClassification,
    CausalAuditStatus,
)


@dataclass(frozen=True)
class CausalAuditListFilters:
    agent_id: str | None = None
    classification: CausalAuditClassification | None = None
    status: CausalAuditStatus | None = None
    evaluator_ref: str | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    limit: int = 50
    offset: int = 0


class CausalAuditRepository(ABC):
    @abstractmethod
    def save(
        self, audit: CausalAudit, expected_version: int | None = None
    ) -> CausalAudit: ...

    @abstractmethod
    def get(
        self, audit_id: str, organization_id: str, project_id: str | None = None
    ) -> CausalAudit | None: ...

    @abstractmethod
    def find_by_fingerprint(
        self, fingerprint: str, organization_id: str, project_id: str | None = None
    ) -> CausalAudit | None: ...

    @abstractmethod
    def list(
        self,
        filters: CausalAuditListFilters,
        organization_id: str,
        project_id: str | None = None,
        execution_id: str | None = None,
    ) -> list[CausalAudit]: ...
