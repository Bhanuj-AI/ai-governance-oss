from __future__ import annotations

from collections.abc import Sequence

from ai_governance.decisions.enums import (
    DecisionConfidenceLevel,
    DecisionStatus,
    DecisionType,
)
from ai_governance.decisions.evidence import MissingEvidence
from ai_governance.decisions.policy_enums import PolicyEffect
from ai_governance.decisions.policies import PolicyEvaluationOutcome


FINAL_POLICY_EFFECTS = {
    PolicyEffect.BLOCK,
    PolicyEffect.REJECT,
    PolicyEffect.APPROVE,
}


def map_policy_outcomes_to_status(
    policy_outcomes: Sequence[PolicyEvaluationOutcome],
) -> DecisionStatus:
    effects = _matched_effects(policy_outcomes)
    if PolicyEffect.BLOCK in effects:
        return DecisionStatus.BLOCKED
    if PolicyEffect.REJECT in effects:
        return DecisionStatus.REJECTED
    if PolicyEffect.APPROVE in effects:
        return DecisionStatus.APPROVED
    if PolicyEffect.RECOMMEND in effects:
        return DecisionStatus.PROPOSED
    if PolicyEffect.INVESTIGATE in effects:
        return DecisionStatus.PROPOSED
    return DecisionStatus.PROPOSED


def map_status_to_decision_type(status: DecisionStatus) -> DecisionType:
    if status == DecisionStatus.BLOCKED:
        return DecisionType.BLOCK
    if status == DecisionStatus.REJECTED:
        return DecisionType.REJECT
    if status == DecisionStatus.APPROVED:
        return DecisionType.APPROVE
    return DecisionType.RECOMMEND


def map_policy_outcomes_to_confidence(
    policy_outcomes: Sequence[PolicyEvaluationOutcome],
    missing_evidence: Sequence[MissingEvidence],
) -> DecisionConfidenceLevel:
    if any(item.severity == "CRITICAL" for item in missing_evidence):
        return DecisionConfidenceLevel.LOW

    matched_outcomes = [outcome for outcome in policy_outcomes if outcome.matched]
    if not matched_outcomes:
        return DecisionConfidenceLevel.LOW

    if any(item.severity == "WARNING" for item in missing_evidence):
        return DecisionConfidenceLevel.MEDIUM

    if any(outcome.effect in FINAL_POLICY_EFFECTS for outcome in matched_outcomes):
        return DecisionConfidenceLevel.HIGH

    return DecisionConfidenceLevel.MEDIUM


def _matched_effects(
    policy_outcomes: Sequence[PolicyEvaluationOutcome],
) -> set[PolicyEffect]:
    return {outcome.effect for outcome in policy_outcomes if outcome.matched}
