from ai_governance.decisions import MissingEvidence, PolicyEvaluationOutcome
from ai_governance.decisions.enums import DecisionConfidenceLevel, DecisionStatus
from ai_governance.decisions.outcome_mapping import (
    map_policy_outcomes_to_confidence,
    map_policy_outcomes_to_status,
)
from ai_governance.decisions.policy_enums import PolicyEffect


def _outcome(effect: PolicyEffect, matched: bool = True) -> PolicyEvaluationOutcome:
    return PolicyEvaluationOutcome(
        policy_id=f"policy-{effect.value.lower()}",
        policy_version="1",
        matched_rule_id="rule-1" if matched else None,
        effect=effect,
        reason=f"{effect.value} reason",
        matched=matched,
    )


def test_block_takes_precedence_over_approve() -> None:
    assert (
        map_policy_outcomes_to_status(
            (
                _outcome(PolicyEffect.APPROVE),
                _outcome(PolicyEffect.BLOCK),
            )
        )
        == DecisionStatus.BLOCKED
    )


def test_reject_and_approve_map_to_final_statuses() -> None:
    assert (
        map_policy_outcomes_to_status((_outcome(PolicyEffect.REJECT),))
        == DecisionStatus.REJECTED
    )
    assert (
        map_policy_outcomes_to_status((_outcome(PolicyEffect.APPROVE),))
        == DecisionStatus.APPROVED
    )


def test_recommend_and_no_decision_map_to_proposed() -> None:
    assert (
        map_policy_outcomes_to_status((_outcome(PolicyEffect.RECOMMEND),))
        == DecisionStatus.PROPOSED
    )
    assert map_policy_outcomes_to_status(()) == DecisionStatus.PROPOSED


def test_confidence_mapping_uses_missing_evidence_and_matches() -> None:
    assert (
        map_policy_outcomes_to_confidence(
            (_outcome(PolicyEffect.APPROVE),),
            (),
        )
        == DecisionConfidenceLevel.HIGH
    )
    assert (
        map_policy_outcomes_to_confidence(
            (_outcome(PolicyEffect.APPROVE),),
            (
                MissingEvidence(
                    evidence_type="Metric",
                    reason="No metric evidence is connected.",
                    severity="WARNING",
                ),
            ),
        )
        == DecisionConfidenceLevel.MEDIUM
    )
    assert (
        map_policy_outcomes_to_confidence((), ())
        == DecisionConfidenceLevel.LOW
    )
    assert (
        map_policy_outcomes_to_confidence(
            (_outcome(PolicyEffect.APPROVE),),
            (
                MissingEvidence(
                    evidence_type="Target",
                    reason="Target entity was not found.",
                    severity="CRITICAL",
                ),
            ),
        )
        == DecisionConfidenceLevel.LOW
    )
