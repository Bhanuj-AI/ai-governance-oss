from datetime import UTC, datetime

from ai_governance.decisions import (
    DecisionTargetType,
    GovernancePolicy,
    GovernancePolicyEvaluator,
    PolicyCondition,
    PolicyConditionOperator,
    PolicyEffect,
    PolicyEvaluationContext,
    PolicyRule,
    PolicyStatus,
)


def _rule(
    *,
    rule_id: str,
    operator: PolicyConditionOperator,
    expected_value: object | None,
    effect: PolicyEffect = PolicyEffect.RECOMMEND,
    priority: int = 10,
    field_path: str = "metrics.groundedness.score",
    reason_template: str = "Policy rule matched.",
) -> PolicyRule:
    return PolicyRule(
        rule_id=rule_id,
        name=rule_id,
        conditions=(
            PolicyCondition(
                field_path=field_path,
                operator=operator,
                expected_value=expected_value,
            ),
        ),
        effect=effect,
        reason_template=reason_template,
        priority=priority,
    )


def _policy(*rules: PolicyRule) -> GovernancePolicy:
    return GovernancePolicy(
        policy_id="policy-1",
        version="2026-07-02",
        name="quality gate",
        description=None,
        status=PolicyStatus.ACTIVE,
        target_types=(DecisionTargetType.CANDIDATE,),
        rules=rules,
        created_by="governance-admin",
        created_at=datetime(2026, 7, 2, tzinfo=UTC),
    )


def _context(evidence: dict[str, object]) -> PolicyEvaluationContext:
    return PolicyEvaluationContext(
        target_type=DecisionTargetType.CANDIDATE,
        target_id="candidate-1",
        evidence=evidence,
    )


def test_evaluate_greater_than_condition() -> None:
    outcome = GovernancePolicyEvaluator().evaluate(
        _policy(
            _rule(
                rule_id="rule-1",
                operator=PolicyConditionOperator.GREATER_THAN,
                expected_value=0.8,
            )
        ),
        _context({"metrics": {"groundedness": {"score": 0.91}}}),
    )

    assert outcome.matched
    assert outcome.effect == PolicyEffect.RECOMMEND
    assert outcome.matched_rule_id == "rule-1"


def test_evaluate_less_than_condition() -> None:
    outcome = GovernancePolicyEvaluator().evaluate(
        _policy(
            _rule(
                rule_id="rule-1",
                operator=PolicyConditionOperator.LESS_THAN,
                expected_value=0.8,
            )
        ),
        _context({"metrics": {"groundedness": {"score": 0.72}}}),
    )

    assert outcome.matched


def test_evaluate_equals_condition() -> None:
    outcome = GovernancePolicyEvaluator().evaluate(
        _policy(
            _rule(
                rule_id="rule-1",
                field_path="drift.severity",
                operator=PolicyConditionOperator.EQUALS,
                expected_value="HIGH",
                effect=PolicyEffect.INVESTIGATE,
            )
        ),
        _context({"drift": {"severity": "HIGH"}}),
    )

    assert outcome.matched
    assert outcome.effect == PolicyEffect.INVESTIGATE


def test_evaluate_in_condition() -> None:
    outcome = GovernancePolicyEvaluator().evaluate(
        _policy(
            _rule(
                rule_id="rule-1",
                field_path="audit.status",
                operator=PolicyConditionOperator.IN,
                expected_value=("SUCCEEDED", "COMPLETED"),
            )
        ),
        _context({"audit": {"status": "SUCCEEDED"}}),
    )

    assert outcome.matched


def test_evaluate_exists_condition() -> None:
    outcome = GovernancePolicyEvaluator().evaluate(
        _policy(
            _rule(
                rule_id="rule-1",
                field_path="leaderboard.rank",
                operator=PolicyConditionOperator.EXISTS,
                expected_value=None,
            )
        ),
        _context({"leaderboard": {"rank": 1}}),
    )

    assert outcome.matched


def test_evaluate_missing_condition() -> None:
    outcome = GovernancePolicyEvaluator().evaluate(
        _policy(
            _rule(
                rule_id="rule-1",
                field_path="drift.severity",
                operator=PolicyConditionOperator.MISSING,
                expected_value=None,
            )
        ),
        _context({"metrics": {"groundedness": {"score": 0.91}}}),
    )

    assert outcome.matched


def test_return_no_decision_when_no_rule_matches() -> None:
    outcome = GovernancePolicyEvaluator().evaluate(
        _policy(
            _rule(
                rule_id="rule-1",
                operator=PolicyConditionOperator.GREATER_THAN,
                expected_value=0.95,
            )
        ),
        _context({"metrics": {"groundedness": {"score": 0.91}}}),
    )

    assert not outcome.matched
    assert outcome.effect == PolicyEffect.NO_DECISION
    assert outcome.matched_rule_id is None


def test_first_matching_rule_by_priority_wins() -> None:
    outcome = GovernancePolicyEvaluator().evaluate(
        _policy(
            _rule(
                rule_id="rule-low-priority",
                operator=PolicyConditionOperator.GREATER_THAN,
                expected_value=0.8,
                effect=PolicyEffect.RECOMMEND,
                priority=20,
            ),
            _rule(
                rule_id="rule-high-priority",
                operator=PolicyConditionOperator.GREATER_THAN,
                expected_value=0.8,
                effect=PolicyEffect.APPROVE,
                priority=1,
            ),
        ),
        _context({"metrics": {"groundedness": {"score": 0.91}}}),
    )

    assert outcome.matched_rule_id == "rule-high-priority"
    assert outcome.effect == PolicyEffect.APPROVE


def test_policy_evaluation_does_not_mutate_input_context() -> None:
    evidence = {"metrics": {"groundedness": {"score": 0.91}}}
    context = _context(evidence)
    before_evidence = dict(context.evidence)
    before_metadata = dict(context.metadata)

    GovernancePolicyEvaluator().evaluate(
        _policy(
            _rule(
                rule_id="rule-1",
                operator=PolicyConditionOperator.GREATER_THAN,
                expected_value=0.8,
            )
        ),
        context,
    )

    assert context.evidence == before_evidence
    assert context.metadata == before_metadata


def test_context_target_type_outside_policy_returns_no_decision() -> None:
    context = PolicyEvaluationContext(
        target_type=DecisionTargetType.EXPERIMENT,
        target_id="experiment-1",
        evidence={"metrics": {"groundedness": {"score": 0.91}}},
    )

    outcome = GovernancePolicyEvaluator().evaluate(
        _policy(
            _rule(
                rule_id="rule-1",
                operator=PolicyConditionOperator.GREATER_THAN,
                expected_value=0.8,
            )
        ),
        context,
    )

    assert not outcome.matched
    assert outcome.effect == PolicyEffect.NO_DECISION


def test_evaluate_with_trace_returns_matched_conditions() -> None:
    result = GovernancePolicyEvaluator().evaluate_with_trace(
        _policy(
            _rule(
                rule_id="rule-1",
                operator=PolicyConditionOperator.GREATER_THAN,
                expected_value=0.8,
            )
        ),
        _context({"metrics": {"groundedness": {"score": 0.91}}}),
    )

    assert result.outcome.matched
    assert result.matched_conditions[0].field_path == (
        "metrics.groundedness.score"
    )
    assert not result.unmatched_conditions
    assert result.evaluation_trace[0].actual_value == 0.91
    assert result.evaluation_trace[0].matched is True


def test_evaluate_with_trace_records_unmatched_conditions() -> None:
    result = GovernancePolicyEvaluator().evaluate_with_trace(
        _policy(
            _rule(
                rule_id="rule-1",
                operator=PolicyConditionOperator.GREATER_THAN,
                expected_value=0.95,
            )
        ),
        _context({"metrics": {"groundedness": {"score": 0.91}}}),
    )

    assert not result.outcome.matched
    assert not result.matched_conditions
    assert result.unmatched_conditions[0].field_path == (
        "metrics.groundedness.score"
    )
    assert result.evaluation_trace[0].matched is False


def test_evaluate_with_trace_handles_missing_field() -> None:
    result = GovernancePolicyEvaluator().evaluate_with_trace(
        _policy(
            _rule(
                rule_id="rule-1",
                operator=PolicyConditionOperator.GREATER_THAN,
                expected_value=0.95,
            )
        ),
        _context({"metrics": {}}),
    )

    assert result.evaluation_trace[0].actual_value is None
    assert result.evaluation_trace[0].matched is False
