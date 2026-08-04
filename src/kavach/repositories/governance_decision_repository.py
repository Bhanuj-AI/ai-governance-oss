from __future__ import annotations

from typing import Protocol

from kavach.decisions import (
    DecisionAuditRecord,
    DecisionExplanation,
    DecisionStatus,
    DecisionTargetType,
    GovernanceDecision,
)


class GovernanceDecisionRepository(Protocol):
    """
    Persistence contract for authoritative governance decisions.
    """

    def save(self, decision: GovernanceDecision) -> GovernanceDecision: ...

    def save_with_explanation(
        self,
        decision: GovernanceDecision,
        explanation: DecisionExplanation,
    ) -> GovernanceDecision: ...

    def get(self, decision_id: str) -> GovernanceDecision | None: ...

    def get_explanation(
        self,
        decision_id: str,
    ) -> DecisionExplanation | None: ...

    def find_by_target(
        self,
        target_type: DecisionTargetType,
        target_id: str,
        *,
        limit: int = 50,
    ) -> tuple[GovernanceDecision, ...]: ...

    def find_by_status(
        self,
        status: DecisionStatus,
        *,
        limit: int = 50,
    ) -> tuple[GovernanceDecision, ...]: ...

    def find_by_correlation_id(
        self,
        correlation_id: str,
        *,
        limit: int = 50,
    ) -> tuple[GovernanceDecision, ...]: ...

    def find_by_request_id(
        self,
        request_id: str,
        *,
        limit: int = 50,
    ) -> tuple[GovernanceDecision, ...]: ...

    def list(
        self,
        *,
        limit: int = 50,
    ) -> tuple[GovernanceDecision, ...]: ...

    def save_audit(
        self,
        record: DecisionAuditRecord,
    ) -> DecisionAuditRecord: ...

    def find_audit_by_decision(
        self,
        decision_id: str,
        *,
        limit: int = 100,
    ) -> tuple[DecisionAuditRecord, ...]: ...

    def supersede(
        self,
        old_decision_id: str,
        new_decision: GovernanceDecision,
        *,
        reason: str,
    ) -> GovernanceDecision: ...

    def archive(
        self,
        decision_id: str,
        *,
        reason: str,
    ) -> GovernanceDecision: ...
