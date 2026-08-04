from datetime import UTC, datetime

from kavach.decisions import (
    DecisionConfidenceLevel,
    DecisionEvidenceReference,
    DecisionPolicyReference,
    DecisionProducerType,
    DecisionProvenance,
    DecisionStatus,
    DecisionTarget,
    DecisionTargetType,
    DecisionType,
    GovernanceDecision,
)


def _target() -> DecisionTarget:
    return DecisionTarget(
        target_type=DecisionTargetType.CANDIDATE,
        target_id="candidate-1",
    )


def _evidence() -> tuple[DecisionEvidenceReference, ...]:
    return (
        DecisionEvidenceReference(
            evidence_type="EvaluationResult",
            evidence_id="evaluation-result-1",
            relationship_type="GENERATED_FROM",
            source="evaluation-service",
            metadata={"score": 0.96},
        ),
    )


def _policy() -> DecisionPolicyReference:
    return DecisionPolicyReference(
        policy_id="policy-1",
        policy_version="2026-07-02",
        policy_name="minimum-quality-gate",
    )


def _provenance() -> DecisionProvenance:
    return DecisionProvenance(
        producer_type=DecisionProducerType.POLICY_ENGINE,
        producer_id="policy-engine-1",
        actor_id="governance-admin",
        created_at=datetime(2026, 7, 2, tzinfo=UTC),
    )


def test_create_valid_proposed_decision() -> None:
    decision = GovernanceDecision(
        decision_id="decision-1",
        decision_type=DecisionType.RECOMMEND,
        status=DecisionStatus.PROPOSED,
        target=_target(),
        reason="Candidate has the strongest evaluation result.",
        confidence=DecisionConfidenceLevel.MEDIUM,
        evidence=_evidence(),
        policies=(_policy(),),
        provenance=_provenance(),
        metadata={"source": "unit-test"},
    )

    assert decision.decision_type == DecisionType.RECOMMEND
    assert decision.status == DecisionStatus.PROPOSED
    assert decision.target.target_type == DecisionTargetType.CANDIDATE
    assert decision.evidence_ids() == ("evaluation-result-1",)
    assert decision.policy_ids() == ("policy-1",)


def test_create_approved_decision() -> None:
    decision = GovernanceDecision.approved(
        decision_id="decision-1",
        target=_target(),
        reason="Candidate passed the quality gate.",
        evidence=_evidence(),
        policies=(_policy(),),
        provenance=_provenance(),
        finalized_at=datetime(2026, 7, 2, tzinfo=UTC),
    )

    assert decision.decision_type == DecisionType.APPROVE
    assert decision.status == DecisionStatus.APPROVED
    assert decision.is_finalized()


def test_value_objects_copy_metadata() -> None:
    evidence_metadata = {"score": 0.96}
    decision_metadata = {"source": "unit-test"}
    evidence = DecisionEvidenceReference(
        evidence_type="EvaluationResult",
        evidence_id="evaluation-result-1",
        metadata=evidence_metadata,
    )
    decision = GovernanceDecision.proposed(
        decision_id="decision-1",
        decision_type=DecisionType.RECOMMEND,
        target=_target(),
        reason="Candidate should be reviewed.",
        confidence=DecisionConfidenceLevel.LOW,
        evidence=(evidence,),
        provenance=_provenance(),
        metadata=decision_metadata,
    )

    evidence_metadata["score"] = 0.1
    decision_metadata["source"] = "changed"

    assert evidence.metadata == {"score": 0.96}
    assert decision.metadata == {"source": "unit-test"}


def test_is_finalized_behavior() -> None:
    proposed = GovernanceDecision.proposed(
        decision_id="decision-1",
        decision_type=DecisionType.INVESTIGATE,
        target=_target(),
        reason="Low confidence requires investigation.",
        evidence=_evidence(),
        provenance=_provenance(),
    )
    blocked = GovernanceDecision.blocked(
        decision_id="decision-2",
        target=_target(),
        reason="Candidate failed the safety gate.",
        evidence=_evidence(),
        provenance=_provenance(),
    )

    assert not proposed.is_finalized()
    assert blocked.is_finalized()


def test_requires_human_review_behavior() -> None:
    decision = GovernanceDecision.proposed(
        decision_id="decision-1",
        decision_type=DecisionType.INVESTIGATE,
        target=_target(),
        reason="Low confidence requires investigation.",
        confidence=DecisionConfidenceLevel.LOW,
        evidence=_evidence(),
        provenance=_provenance(),
    )

    assert decision.requires_human_review()


def test_factory_helpers_assign_expected_statuses() -> None:
    proposed = GovernanceDecision.proposed(
        decision_id="decision-1",
        decision_type=DecisionType.PROMOTE,
        target=_target(),
        reason="Candidate should be promoted.",
        evidence=_evidence(),
        provenance=_provenance(),
    )
    approved = GovernanceDecision.approved(
        decision_id="decision-2",
        target=_target(),
        reason="Candidate passed governance.",
        evidence=_evidence(),
        provenance=_provenance(),
    )
    rejected = GovernanceDecision.rejected(
        decision_id="decision-3",
        target=_target(),
        reason="Candidate failed governance.",
        evidence=_evidence(),
        provenance=_provenance(),
    )
    blocked = GovernanceDecision.blocked(
        decision_id="decision-4",
        target=_target(),
        reason="Candidate must not ship.",
        evidence=_evidence(),
        provenance=_provenance(),
    )

    assert proposed.status == DecisionStatus.PROPOSED
    assert approved.status == DecisionStatus.APPROVED
    assert rejected.status == DecisionStatus.REJECTED
    assert blocked.status == DecisionStatus.BLOCKED
