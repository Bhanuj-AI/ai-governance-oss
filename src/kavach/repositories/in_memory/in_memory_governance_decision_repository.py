from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from datetime import UTC, datetime

from kavach.decisions import (
    DecisionAuditAction,
    DecisionAuditRecord,
    DecisionExplanation,
    DecisionStatus,
    DecisionSupersession,
    DecisionTargetType,
    GovernanceDecision,
)
from kavach.decisions.events import (
    GOVERNANCE_DECISION_ARCHIVED,
    GOVERNANCE_DECISION_CREATED,
    GOVERNANCE_DECISION_SUPERSEDED,
)
from kavach.decisions.exceptions import DecisionValidationError
from kavach.ontology.enums import EntityType
from kavach.ontology.synchronization.events import (
    OntologySyncEventPublisherProtocol,
)
from kavach.repositories.governance_decision_repository import (
    GovernanceDecisionRepository,
)


class InMemoryGovernanceDecisionRepository(GovernanceDecisionRepository):
    """
    In-memory decision repository used by tests and local REST dependencies.
    """

    def __init__(
        self,
        *,
        ontology_event_publisher: OntologySyncEventPublisherProtocol | None = None,
    ) -> None:
        self._decisions: dict[str, GovernanceDecision] = {}
        self._explanations: dict[str, DecisionExplanation] = {}
        self._audit_records: dict[str, DecisionAuditRecord] = {}
        self._ontology_event_publisher = ontology_event_publisher

    def save(self, decision: GovernanceDecision) -> GovernanceDecision:
        return self._save(decision)

    def save_with_explanation(
        self,
        decision: GovernanceDecision,
        explanation: DecisionExplanation,
    ) -> GovernanceDecision:
        return self._save(decision, explanation=explanation)

    def get(self, decision_id: str) -> GovernanceDecision | None:
        return self._decisions.get(decision_id)

    def get_explanation(
        self,
        decision_id: str,
    ) -> DecisionExplanation | None:
        return self._explanations.get(decision_id)

    def find_by_target(
        self,
        target_type: DecisionTargetType,
        target_id: str,
        *,
        limit: int = 50,
    ) -> tuple[GovernanceDecision, ...]:
        return self._sorted(
            decision
            for decision in self._decisions.values()
            if decision.target.target_type == target_type
            and decision.target.target_id == target_id
        )[:limit]

    def find_by_status(
        self,
        status: DecisionStatus,
        *,
        limit: int = 50,
    ) -> tuple[GovernanceDecision, ...]:
        return self._sorted(
            decision
            for decision in self._decisions.values()
            if decision.status == status
        )[:limit]

    def find_by_correlation_id(
        self,
        correlation_id: str,
        *,
        limit: int = 50,
    ) -> tuple[GovernanceDecision, ...]:
        return self._sorted(
            decision
            for decision in self._decisions.values()
            if decision.provenance.correlation_id == correlation_id
        )[:limit]

    def find_by_request_id(
        self,
        request_id: str,
        *,
        limit: int = 50,
    ) -> tuple[GovernanceDecision, ...]:
        return self._sorted(
            decision
            for decision in self._decisions.values()
            if decision.provenance.request_id == request_id
        )[:limit]

    def list(
        self,
        *,
        limit: int = 50,
    ) -> tuple[GovernanceDecision, ...]:
        return self._sorted(self._decisions.values())[:limit]

    def save_audit(
        self,
        record: DecisionAuditRecord,
    ) -> DecisionAuditRecord:
        self._audit_records[record.audit_id] = record
        return record

    def find_audit_by_decision(
        self,
        decision_id: str,
        *,
        limit: int = 100,
    ) -> tuple[DecisionAuditRecord, ...]:
        return tuple(
            sorted(
                (
                    record
                    for record in self._audit_records.values()
                    if record.decision_id == decision_id
                ),
                key=lambda record: (record.created_at, record.audit_id),
            )
        )[:limit]

    def supersede(
        self,
        old_decision_id: str,
        new_decision: GovernanceDecision,
        *,
        reason: str,
    ) -> GovernanceDecision:
        old_decision = self.get(old_decision_id)
        if old_decision is None:
            raise DecisionValidationError(
                f"Governance decision {old_decision_id!r} does not exist."
            )
        if old_decision.supersession.superseded_by_decision_id is not None:
            raise DecisionValidationError(
                f"Governance decision {old_decision_id!r} is already superseded."
            )

        superseded_old = replace(
            old_decision,
            status=DecisionStatus.SUPERSEDED,
            supersession=DecisionSupersession(
                supersedes_decision_id=(
                    old_decision.supersession.supersedes_decision_id
                ),
                superseded_by_decision_id=new_decision.decision_id,
                supersession_reason=reason,
            ),
        )
        replacement = replace(
            new_decision,
            supersession=DecisionSupersession(
                supersedes_decision_id=old_decision_id,
                superseded_by_decision_id=(
                    new_decision.supersession.superseded_by_decision_id
                ),
                supersession_reason=reason,
            ),
        )
        self._save(superseded_old, publish_created=False, enforce_finalized=False)
        saved = self._save(replacement)
        self.save_audit(
            DecisionAuditRecord(
                decision_id=old_decision_id,
                action=DecisionAuditAction.SUPERSEDED,
                actor_id=replacement.provenance.actor_id,
                producer_id=replacement.provenance.producer_id,
                correlation_id=replacement.provenance.correlation_id,
                request_id=replacement.provenance.request_id,
                reason=reason,
                metadata={"superseded_by_decision_id": replacement.decision_id},
            )
        )
        self._publish(GOVERNANCE_DECISION_SUPERSEDED, superseded_old)
        return saved

    def archive(
        self,
        decision_id: str,
        *,
        reason: str,
    ) -> GovernanceDecision:
        decision = self.get(decision_id)
        if decision is None:
            raise DecisionValidationError(
                f"Governance decision {decision_id!r} does not exist."
            )
        if decision.status == DecisionStatus.ARCHIVED:
            return decision

        archived = replace(
            decision,
            status=DecisionStatus.ARCHIVED,
            archived_at=datetime.now(UTC),
        )
        saved = self._save(
            archived,
            publish_created=False,
            enforce_finalized=False,
        )
        self.save_audit(
            DecisionAuditRecord(
                decision_id=decision_id,
                action=DecisionAuditAction.ARCHIVED,
                actor_id=archived.provenance.actor_id,
                producer_id=archived.provenance.producer_id,
                correlation_id=archived.provenance.correlation_id,
                request_id=archived.provenance.request_id,
                reason=reason,
            )
        )
        self._publish(GOVERNANCE_DECISION_ARCHIVED, archived)
        return saved

    def _save(
        self,
        decision: GovernanceDecision,
        *,
        explanation: DecisionExplanation | None = None,
        publish_created: bool = True,
        enforce_finalized: bool = True,
    ) -> GovernanceDecision:
        existing = self.get(decision.decision_id)
        existing_explanation = self.get_explanation(decision.decision_id)
        if (
            existing is not None
            and enforce_finalized
            and existing.is_finalized()
        ):
            if existing == decision and (
                explanation is None or existing_explanation == explanation
            ):
                return decision
            raise DecisionValidationError(
                "Finalized governance decision cannot be mutated."
            )

        self._decisions[decision.decision_id] = decision
        if explanation is not None:
            self._explanations[decision.decision_id] = explanation
        if existing is None and publish_created:
            self._publish(GOVERNANCE_DECISION_CREATED, decision)
        return decision

    def _publish(
        self,
        event_type: str,
        decision: GovernanceDecision,
    ) -> None:
        if self._ontology_event_publisher is None:
            return

        self._ontology_event_publisher.publish_entity_event(
            event_type,
            entity_type=EntityType.GOVERNANCE_DECISION.value,
            entity_id=decision.decision_id,
            correlation_id=decision.provenance.correlation_id,
            payload={
                "decision_id": decision.decision_id,
                "status": decision.status.value,
                "target_type": decision.target.target_type.value,
                "target_id": decision.target.target_id,
            },
        )

    @staticmethod
    def _sorted(
        decisions: Iterable[GovernanceDecision],
    ) -> tuple[GovernanceDecision, ...]:
        return tuple(
            sorted(
                decisions,
                key=lambda decision: (
                    decision.provenance.created_at,
                    decision.decision_id,
                ),
                reverse=True,
            )
        )
