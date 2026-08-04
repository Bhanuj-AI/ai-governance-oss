from datetime import UTC, datetime

from kavach.decisions import (
    DecisionAuditAction,
    DecisionAuditRecord,
    DecisionEvidenceReference,
    DecisionExplanation,
    DecisionPolicyReference,
    DecisionProducerType,
    DecisionProvenance,
    DecisionTarget,
    DecisionTargetType,
    GovernanceDecision,
    MissingEvidence,
)
from kavach.repositories.mappers.governance_decision_persistence_mapper import (
    GovernanceDecisionPersistenceMapper,
)


def test_governance_decision_round_trips_through_persistence_record() -> None:
    decision = _decision()

    record = GovernanceDecisionPersistenceMapper.to_persistence_record(
        decision
    )

    assert (
        GovernanceDecisionPersistenceMapper.from_persistence_record(record)
        == decision
    )


def test_decision_explanation_round_trips_from_persistence_record() -> None:
    explanation = _explanation()
    record = GovernanceDecisionPersistenceMapper.to_persistence_record(
        _decision(),
        explanation,
    )

    assert (
        GovernanceDecisionPersistenceMapper.explanation_from_persistence_record(
            record
        )
        == explanation
    )


def test_decision_audit_record_round_trips_through_persistence_record() -> None:
    audit_record = DecisionAuditRecord(
        audit_id="audit-1",
        decision_id="decision-1",
        action=DecisionAuditAction.SUPERSEDED,
        producer_id="policy-engine-1",
        actor_id="governance-admin",
        correlation_id="correlation-1",
        request_id="request-1",
        reason="Replacement has fresher evidence.",
        created_at=datetime(2026, 7, 2, 1, 2, 3, tzinfo=UTC),
        metadata={"superseded_by_decision_id": "decision-2"},
    )

    record = GovernanceDecisionPersistenceMapper.audit_to_persistence_record(
        audit_record
    )

    assert (
        GovernanceDecisionPersistenceMapper.audit_from_persistence_record(record)
        == audit_record
    )


def _decision(decision_id: str = "decision-1") -> GovernanceDecision:
    return GovernanceDecision.approved(
        decision_id=decision_id,
        target=DecisionTarget(
            target_type=DecisionTargetType.CANDIDATE,
            target_id="candidate-1",
        ),
        reason="Candidate passed governance.",
        evidence=(
            DecisionEvidenceReference(
                evidence_type="EvaluationResult",
                evidence_id="evaluation-result-1",
                relationship_type="GENERATED_FROM",
                source="evaluation-service",
                metadata={"score": 0.96},
            ),
        ),
        policies=(
            DecisionPolicyReference(
                policy_id="policy-1",
                policy_version="2026-07-02",
                policy_name="minimum-quality-gate",
            ),
        ),
        provenance=DecisionProvenance(
            producer_type=DecisionProducerType.POLICY_ENGINE,
            producer_id="policy-engine-1",
            actor_id="governance-admin",
            correlation_id="correlation-1",
            request_id="request-1",
            created_at=datetime(2026, 7, 2, tzinfo=UTC),
        ),
        finalized_at=datetime(2026, 7, 2, 1, tzinfo=UTC),
        metadata={"source": "unit-test"},
    )


def _explanation() -> DecisionExplanation:
    return DecisionExplanation(
        decision_id="decision-1",
        summary="Candidate passed governance.",
        reasons=("quality policy passed",),
        evidence_references=(
            DecisionEvidenceReference(
                evidence_type="EvaluationResult",
                evidence_id="evaluation-result-1",
            ),
        ),
        policy_references=(
            DecisionPolicyReference(
                policy_id="policy-1",
                policy_version="2026-07-02",
                policy_name="minimum-quality-gate",
            ),
        ),
        missing_evidence=(
            MissingEvidence(
                evidence_type="HumanApproval",
                reason="No manual approval was attached.",
                severity="WARNING",
            ),
        ),
        metadata={"reasoning_engine": "unit-test"},
    )
