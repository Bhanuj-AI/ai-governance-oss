from __future__ import annotations

from threading import Lock

from ai_governance.domain.causal_audit import CausalAudit
from ai_governance.repositories.causal_audit_repository import (
    CausalAuditListFilters,
    CausalAuditRepository,
)


class InMemoryCausalAuditRepository(CausalAuditRepository):
    def __init__(self) -> None:
        self._audits: dict[str, CausalAudit] = {}
        self._lock = Lock()

    def save(
        self, audit: CausalAudit, expected_version: int | None = None
    ) -> CausalAudit:
        with self._lock:
            previous = self._audits.get(audit.audit_id)
            if expected_version is not None and (
                previous is None or previous.version != expected_version
            ):
                raise ValueError("Causal audit version conflict.")
            if previous is not None and previous.is_terminal and previous != audit:
                raise ValueError("Completed causal audits are immutable.")
            duplicate = self.find_by_fingerprint(
                audit.request_fingerprint, audit.organization_id, audit.project_id
            )
            if duplicate is not None and duplicate.audit_id != audit.audit_id:
                raise ValueError("Causal audit request fingerprint already exists.")
            self._audits[audit.audit_id] = audit
        return audit

    def get(
        self, audit_id: str, organization_id: str, project_id: str | None = None
    ) -> CausalAudit | None:
        audit = self._audits.get(audit_id)
        return (
            audit
            if audit
            and audit.organization_id == organization_id
            and audit.project_id == project_id
            else None
        )

    def find_by_fingerprint(
        self, fingerprint: str, organization_id: str, project_id: str | None = None
    ) -> CausalAudit | None:
        return next(
            (
                audit
                for audit in self._audits.values()
                if audit.request_fingerprint == fingerprint
                and audit.organization_id == organization_id
                and audit.project_id == project_id
            ),
            None,
        )

    def list(
        self,
        filters: CausalAuditListFilters,
        organization_id: str,
        project_id: str | None = None,
        execution_id: str | None = None,
    ) -> list[CausalAudit]:
        items = [
            audit
            for audit in self._audits.values()
            if audit.organization_id == organization_id
            and audit.project_id == project_id
            and (execution_id is None or audit.execution_id == execution_id)
            and (filters.agent_id is None or audit.agent_id == filters.agent_id)
            and (
                filters.classification is None
                or audit.classification == filters.classification
            )
            and (filters.status is None or audit.status == filters.status)
            and (
                filters.evaluator_ref is None
                or audit.evaluator_ref == filters.evaluator_ref
            )
            and (
                filters.created_after is None
                or audit.created_at >= filters.created_after
            )
            and (
                filters.created_before is None
                or audit.created_at <= filters.created_before
            )
        ]
        items.sort(key=lambda audit: (audit.created_at, audit.audit_id), reverse=True)
        return items[filters.offset : filters.offset + filters.limit]
