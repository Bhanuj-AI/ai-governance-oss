from datetime import UTC, datetime

import pytest

from ai_governance.decisions import (
    DecisionConfidenceLevel,
    DecisionEvidenceReference,
    DecisionPolicyReference,
    DecisionProducerType,
    DecisionProvenance,
    DecisionStatus,
    DecisionSupersession,
    DecisionTarget,
    DecisionTargetType,
    DecisionType,
    DecisionValidationError,
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
        ),
    )


def _provenance() -> DecisionProvenance:
    return DecisionProvenance(
        producer_type=DecisionProducerType.SYSTEM,
        producer_id="system",
        created_at=datetime(2026, 7, 2, tzinfo=UTC),
    )


def _decision(**overrides: object) -> GovernanceDecision:
    values: dict[str, object] = {
        "decision_id": "decision-1",
        "decision_type": DecisionType.RECOMMEND,
        "status": DecisionStatus.PROPOSED,
        "target": _target(),
        "reason": "Candidate should be reviewed.",
        "confidence": DecisionConfidenceLevel.MEDIUM,
        "evidence": _evidence(),
        "policies": (),
        "provenance": _provenance(),
    }
    values.update(overrides)
    return GovernanceDecision(**values)


def test_reject_empty_decision_id() -> None:
    with pytest.raises(DecisionValidationError):
        _decision(decision_id=" ")


def test_reject_empty_reason() -> None:
    with pytest.raises(DecisionValidationError):
        _decision(reason=" ")


def test_reject_missing_evidence() -> None:
    with pytest.raises(DecisionValidationError):
        _decision(evidence=())


def test_reject_empty_target_id() -> None:
    with pytest.raises(DecisionValidationError):
        DecisionTarget(
            target_type=DecisionTargetType.CANDIDATE,
            target_id=" ",
        )


def test_reject_unknown_target_type() -> None:
    with pytest.raises(DecisionValidationError):
        DecisionTarget(
            target_type="UnknownEntity",
            target_id="candidate-1",
        )


def test_reject_empty_policy_id_and_version() -> None:
    with pytest.raises(DecisionValidationError):
        DecisionPolicyReference(
            policy_id=" ",
            policy_version="2026-07-02",
        )

    with pytest.raises(DecisionValidationError):
        DecisionPolicyReference(
            policy_id="policy-1",
            policy_version=" ",
        )


def test_reject_empty_evidence_type_and_id() -> None:
    with pytest.raises(DecisionValidationError):
        DecisionEvidenceReference(
            evidence_type=" ",
            evidence_id="evaluation-result-1",
        )

    with pytest.raises(DecisionValidationError):
        DecisionEvidenceReference(
            evidence_type="EvaluationResult",
            evidence_id=" ",
        )


def test_reject_empty_producer_id() -> None:
    with pytest.raises(DecisionValidationError):
        DecisionProvenance(
            producer_type=DecisionProducerType.SYSTEM,
            producer_id=" ",
            created_at=datetime(2026, 7, 2, tzinfo=UTC),
        )


def test_reject_naive_provenance_timestamp() -> None:
    with pytest.raises(DecisionValidationError):
        DecisionProvenance(
            producer_type=DecisionProducerType.SYSTEM,
            producer_id="system",
            created_at=datetime(2026, 7, 2),  # noqa: DTZ001 - this test requires a naive timestamp.
        )


def test_is_superseded_behavior() -> None:
    by_status = _decision(status=DecisionStatus.SUPERSEDED)
    by_reference = _decision(
        supersession=DecisionSupersession(
            superseded_by_decision_id="decision-2",
        )
    )

    assert by_status.is_superseded()
    assert by_reference.is_superseded()


def test_decision_cannot_supersede_itself() -> None:
    with pytest.raises(DecisionValidationError):
        _decision(
            supersession=DecisionSupersession(
                supersedes_decision_id="decision-1",
            )
        )


def test_decision_cannot_be_superseded_by_itself() -> None:
    with pytest.raises(DecisionValidationError):
        _decision(
            supersession=DecisionSupersession(
                superseded_by_decision_id="decision-1",
            )
        )


def test_reject_empty_supersession_references() -> None:
    with pytest.raises(DecisionValidationError):
        DecisionSupersession(supersedes_decision_id=" ")

    with pytest.raises(DecisionValidationError):
        DecisionSupersession(superseded_by_decision_id=" ")
