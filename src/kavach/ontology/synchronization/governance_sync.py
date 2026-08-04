from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from kavach.decisions import GovernanceDecision
from kavach.decisions.enums import DecisionStatus as GovernanceDecisionStatus
from kavach.governance import EvaluationDrift
from kavach.ontology import EntityType, OntologyService, RelationshipType
from kavach.ontology.synchronization.synchronizer import (
    BaseOntologySynchronizer,
    SynchronizationResult,
    SynchronizationStats,
    sync_actor,
    sync_relationship,
)
from kavach.services.governance_insights import (
    GovernanceInsight,
    GovernanceReport,
)

ProjectionDecisionStatus = Literal[
    "PROPOSED",
    "APPROVED",
    "REJECTED",
    "BLOCKED",
    "SUPERSEDED",
    "ARCHIVED",
]


@dataclass(frozen=True)
class GovernanceDecisionProjection:
    """
    Synchronization projection for durable governance decisions.
    """

    decision_id: str
    decision_type: str
    target_entity_type: str
    target_entity_id: str
    status: ProjectionDecisionStatus
    reason: str
    created_by: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    evidence_refs: tuple[tuple[str, str], ...] = ()
    policy_refs: tuple[tuple[str, str], ...] = ()
    approved_by: str | None = None
    rejected_by: str | None = None
    blocked_by: tuple[tuple[str, str], ...] = ()
    supersedes_decision_id: str | None = None

    @classmethod
    def from_decision(
        cls,
        decision: GovernanceDecision,
    ) -> GovernanceDecisionProjection:
        actor_id = decision.provenance.actor_id
        approved_by = (
            actor_id if decision.status == GovernanceDecisionStatus.APPROVED else None
        )
        rejected_by = (
            actor_id if decision.status == GovernanceDecisionStatus.REJECTED else None
        )
        policy_refs = tuple(
            (EntityType.POLICY.value, reference.policy_id)
            for reference in decision.policies
        )
        blocked_by = (
            policy_refs if decision.status == GovernanceDecisionStatus.BLOCKED else ()
        )
        return cls(
            decision_id=decision.decision_id,
            decision_type=decision.decision_type.value,
            target_entity_type=decision.target.target_type.value,
            target_entity_id=decision.target.target_id,
            status=decision.status.value,  # type: ignore[arg-type]
            reason=decision.reason,
            created_by=decision.provenance.producer_id,
            created_at=decision.provenance.created_at,
            evidence_refs=tuple(
                (reference.evidence_type, reference.evidence_id)
                for reference in decision.evidence
            ),
            policy_refs=policy_refs,
            approved_by=approved_by,
            rejected_by=rejected_by,
            blocked_by=blocked_by,
            supersedes_decision_id=(decision.supersession.supersedes_decision_id),
        )


class GovernanceDecisionOntologySynchronizer(
    BaseOntologySynchronizer[GovernanceDecisionProjection | GovernanceDecision]
):
    """
    Synchronizes governance decision projections into the ontology.
    """

    def __init__(self, ontology_service: OntologyService) -> None:
        super().__init__(
            ontology_service,
            source_name="governance_decision",
        )

    def _synchronize(
        self,
        entity: GovernanceDecisionProjection | GovernanceDecision,
    ) -> SynchronizationResult:
        if isinstance(entity, GovernanceDecision):
            entity = GovernanceDecisionProjection.from_decision(entity)

        actor_id = sync_actor(self._ontology_service, entity.created_by)
        synchronized_entity_ids = {entity.decision_id, actor_id}
        self._ontology_service.create_entity(
            entity_id=entity.decision_id,
            entity_type=EntityType.GOVERNANCE_DECISION,
            owner=entity.created_by,
            lifecycle=entity.status,
            created_at=entity.created_at,
            immutable_attributes={
                "decision_id": entity.decision_id,
                "decision_type": entity.decision_type,
                "target_entity_type": entity.target_entity_type,
                "target_entity_id": entity.target_entity_id,
                "reason": entity.reason,
                "created_by": entity.created_by,
            },
            mutable_attributes={"status": entity.status},
            metadata={"synchronized_from": "governance_decision"},
        )

        relationship_ids = [
            sync_relationship(
                self._ontology_service,
                source_type=EntityType.GOVERNANCE_DECISION,
                source_id=entity.decision_id,
                relationship_type=RelationshipType.CREATED_BY,
                target_type=EntityType.ACTOR,
                target_id=actor_id,
                created_by=entity.created_by,
            )
        ]
        if self._ontology_service.get_entity(
            entity.target_entity_type,
            entity.target_entity_id,
        ):
            relationship_ids.append(
                sync_relationship(
                    self._ontology_service,
                    source_type=EntityType.GOVERNANCE_DECISION,
                    source_id=entity.decision_id,
                    relationship_type=RelationshipType.DECIDES_ON,
                    target_type=entity.target_entity_type,
                    target_id=entity.target_entity_id,
                    created_by=entity.created_by,
                )
            )

        for actor, relationship_type in (
            (entity.approved_by, RelationshipType.APPROVED_BY),
            (entity.rejected_by, RelationshipType.REJECTED_BY),
        ):
            if actor is None:
                continue
            review_actor_id = sync_actor(self._ontology_service, actor)
            synchronized_entity_ids.add(review_actor_id)
            relationship_ids.append(
                sync_relationship(
                    self._ontology_service,
                    source_type=EntityType.GOVERNANCE_DECISION,
                    source_id=entity.decision_id,
                    relationship_type=relationship_type,
                    target_type=EntityType.ACTOR,
                    target_id=review_actor_id,
                    created_by=entity.created_by,
                )
            )

        for policy_type, policy_id in entity.policy_refs:
            if self._ontology_service.get_entity(policy_type, policy_id):
                relationship_ids.append(
                    sync_relationship(
                        self._ontology_service,
                        source_type=EntityType.GOVERNANCE_DECISION,
                        source_id=entity.decision_id,
                        relationship_type=RelationshipType.GOVERNED_BY,
                        target_type=policy_type,
                        target_id=policy_id,
                        created_by=entity.created_by,
                    )
                )

        for evidence_type, evidence_id in entity.evidence_refs:
            if self._ontology_service.get_entity(evidence_type, evidence_id):
                relationship_ids.append(
                    sync_relationship(
                        self._ontology_service,
                        source_type=EntityType.GOVERNANCE_DECISION,
                        source_id=entity.decision_id,
                        relationship_type=RelationshipType.GENERATED_FROM,
                        target_type=evidence_type,
                        target_id=evidence_id,
                        created_by=entity.created_by,
                    )
                )

        for blocker_type, blocker_id in entity.blocked_by:
            if self._ontology_service.get_entity(blocker_type, blocker_id):
                relationship_ids.append(
                    sync_relationship(
                        self._ontology_service,
                        source_type=EntityType.GOVERNANCE_DECISION,
                        source_id=entity.decision_id,
                        relationship_type=RelationshipType.BLOCKED_BY,
                        target_type=blocker_type,
                        target_id=blocker_id,
                        created_by=entity.created_by,
                    )
                )

        if entity.supersedes_decision_id is not None and (
            self._ontology_service.get_entity(
                EntityType.GOVERNANCE_DECISION.value,
                entity.supersedes_decision_id,
            )
        ):
            relationship_ids.append(
                sync_relationship(
                    self._ontology_service,
                    source_type=EntityType.GOVERNANCE_DECISION,
                    source_id=entity.decision_id,
                    relationship_type=RelationshipType.SUPERSEDES,
                    target_type=EntityType.GOVERNANCE_DECISION,
                    target_id=entity.supersedes_decision_id,
                    created_by=entity.created_by,
                )
            )

        return SynchronizationResult(
            synchronized_entity_ids=tuple(sorted(synchronized_entity_ids)),
            synchronized_relationship_ids=tuple(relationship_ids),
            stats=SynchronizationStats(
                entities_synchronized=len(synchronized_entity_ids),
                relationships_synchronized=len(relationship_ids),
            ),
        )

    def _archive_target(
        self,
        entity: GovernanceDecisionProjection | GovernanceDecision,
    ) -> tuple[str, str]:
        if isinstance(entity, GovernanceDecision):
            entity = GovernanceDecisionProjection.from_decision(entity)
        return EntityType.GOVERNANCE_DECISION.value, entity.decision_id


class GovernanceInsightOntologySynchronizer(
    BaseOntologySynchronizer[GovernanceInsight]
):
    """
    Synchronizes governance insight read models into the ontology.
    """

    def __init__(self, ontology_service: OntologyService) -> None:
        super().__init__(
            ontology_service,
            source_name="governance_insight",
        )

    def _synchronize(
        self,
        entity: GovernanceInsight,
    ) -> SynchronizationResult:
        insight_id = governance_insight_id(entity)
        self._ontology_service.create_entity(
            entity_id=insight_id,
            entity_type=EntityType.GOVERNANCE_INSIGHT,
            owner="governance_intelligence",
            lifecycle=entity.status,
            created_at=entity.generated_at,
            immutable_attributes={
                "summary": entity.summary,
                "status": entity.status,
                "confidence": entity.confidence,
                "evidence": entity.evidence,
                "metrics": entity.metrics,
                "related_resources": entity.related_resources,
                "recommended_next_steps": entity.recommended_next_steps,
            },
            metadata={"synchronized_from": "governance_intelligence"},
        )
        relationship_ids = self._sync_governance_evidence(
            insight_id,
            entity.evidence,
        )
        relationship_ids.extend(
            self._sync_recommendations(insight_id, entity.related_resources)
        )
        return SynchronizationResult(
            synchronized_entity_ids=(insight_id,),
            synchronized_relationship_ids=tuple(relationship_ids),
            stats=SynchronizationStats(
                entities_synchronized=1,
                relationships_synchronized=len(relationship_ids),
            ),
        )

    def _archive_target(
        self,
        entity: GovernanceInsight,
    ) -> tuple[str, str]:
        return EntityType.GOVERNANCE_INSIGHT.value, governance_insight_id(entity)

    def _sync_governance_evidence(
        self,
        insight_id: str,
        evidence: list[dict[str, Any]],
    ) -> list[str]:
        relationship_ids = []
        for target in _evidence_targets(evidence):
            target_type, target_id = target
            if self._ontology_service.get_entity(target_type, target_id):
                relationship_ids.append(
                    sync_relationship(
                        self._ontology_service,
                        source_type=EntityType.GOVERNANCE_INSIGHT,
                        source_id=insight_id,
                        relationship_type=RelationshipType.GENERATED_FROM,
                        target_type=target_type,
                        target_id=target_id,
                        created_by="governance_intelligence",
                    )
                )
        return relationship_ids

    def _sync_recommendations(
        self,
        insight_id: str,
        related_resources: list[dict[str, Any]],
    ) -> list[str]:
        relationship_ids = []
        for resource in related_resources:
            candidate_id = resource.get("candidate_id")
            if not isinstance(candidate_id, str):
                continue
            if self._ontology_service.get_entity(
                EntityType.CANDIDATE.value,
                candidate_id,
            ):
                relationship_ids.append(
                    sync_relationship(
                        self._ontology_service,
                        source_type=EntityType.GOVERNANCE_INSIGHT,
                        source_id=insight_id,
                        relationship_type=RelationshipType.RECOMMENDS,
                        target_type=EntityType.CANDIDATE,
                        target_id=candidate_id,
                        created_by="governance_intelligence",
                    )
                )
        return relationship_ids


class GovernanceReportOntologySynchronizer(BaseOntologySynchronizer[GovernanceReport]):
    """
    Synchronizes governance reports into the ontology projection.
    """

    def __init__(self, ontology_service: OntologyService) -> None:
        super().__init__(
            ontology_service,
            source_name="governance_report",
        )

    def _synchronize(
        self,
        entity: GovernanceReport,
    ) -> SynchronizationResult:
        report_id = governance_report_id(entity)
        self._ontology_service.create_entity(
            entity_id=report_id,
            entity_type=EntityType.GOVERNANCE_REPORT,
            owner="governance_reporting",
            lifecycle="GENERATED",
            created_at=entity.generated_at,
            immutable_attributes={
                "report_type": entity.report_type,
                "report_format": entity.report_format,
                "content": entity.content,
            },
            metadata={"synchronized_from": "governance_reporting"},
        )
        evidence = (
            entity.content.get("evidence", [])
            if isinstance(entity.content, dict)
            else []
        )
        relationship_ids = []
        if isinstance(evidence, list):
            for target_type, target_id in _evidence_targets(evidence):
                if self._ontology_service.get_entity(target_type, target_id):
                    relationship_ids.append(
                        sync_relationship(
                            self._ontology_service,
                            source_type=EntityType.GOVERNANCE_REPORT,
                            source_id=report_id,
                            relationship_type=RelationshipType.GENERATED_FROM,
                            target_type=target_type,
                            target_id=target_id,
                            created_by="governance_reporting",
                        )
                    )
        return SynchronizationResult(
            synchronized_entity_ids=(report_id,),
            synchronized_relationship_ids=tuple(relationship_ids),
            stats=SynchronizationStats(
                entities_synchronized=1,
                relationships_synchronized=len(relationship_ids),
            ),
        )

    def _archive_target(
        self,
        entity: GovernanceReport,
    ) -> tuple[str, str]:
        return EntityType.GOVERNANCE_REPORT.value, governance_report_id(entity)


class DriftOntologySynchronizer(BaseOntologySynchronizer[EvaluationDrift]):
    """
    Synchronizes drift analysis output into the ontology projection.
    """

    def __init__(self, ontology_service: OntologyService) -> None:
        super().__init__(
            ontology_service,
            source_name="drift_analysis",
        )

    def _synchronize(
        self,
        entity: EvaluationDrift,
    ) -> SynchronizationResult:
        drift_id = drift_analysis_id(entity)
        self._ontology_service.create_entity(
            entity_id=drift_id,
            entity_type=EntityType.DRIFT_ANALYSIS,
            owner="governance_plane",
            lifecycle=entity.severity.value,
            immutable_attributes={
                "baseline_evaluation_id": entity.baseline_evaluation_id,
                "candidate_evaluation_id": entity.candidate_evaluation_id,
                "score_difference": entity.score_difference,
                "severity": entity.severity.value,
            },
            metadata={"synchronized_from": "drift_analysis"},
        )
        return SynchronizationResult(
            synchronized_entity_ids=(drift_id,),
            stats=SynchronizationStats(entities_synchronized=1),
        )

    def _archive_target(
        self,
        entity: EvaluationDrift,
    ) -> tuple[str, str]:
        return EntityType.DRIFT_ANALYSIS.value, drift_analysis_id(entity)


def governance_insight_id(entity: GovernanceInsight) -> str:
    return "insight:" + _digest(
        entity.summary,
        entity.status,
        entity.confidence,
        entity.generated_at.isoformat(),
    )


def governance_report_id(entity: GovernanceReport) -> str:
    return "report:" + _digest(
        entity.report_type,
        entity.report_format,
        entity.generated_at.isoformat(),
    )


def drift_analysis_id(entity: EvaluationDrift) -> str:
    return "drift:" + _digest(
        entity.baseline_evaluation_id,
        entity.candidate_evaluation_id,
        entity.severity.value,
    )


def _evidence_targets(
    evidence: list[dict[str, Any]],
) -> list[tuple[str, str]]:
    targets: list[tuple[str, str]] = []
    for item in evidence:
        for key, entity_type in (
            ("evaluation_id", EntityType.EVALUATION_RESULT.value),
            ("run_id", EntityType.EVALUATION_RUN.value),
            ("job_id", EntityType.JOB.value),
            ("candidate_id", EntityType.CANDIDATE.value),
            ("experiment_id", EntityType.EXPERIMENT.value),
            ("audit_id", EntityType.MCP_AUDIT_RECORD.value),
        ):
            value = item.get(key)
            if isinstance(value, str):
                targets.append((entity_type, value))
    return targets


def _digest(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]
