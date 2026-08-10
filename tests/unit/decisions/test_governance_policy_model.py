from datetime import UTC, datetime

import pytest

from ai_governance.decisions import (
    DecisionTargetType,
    DecisionValidationError,
    GovernancePolicy,
    PolicyCondition,
    PolicyConditionOperator,
    PolicyEffect,
    PolicyRule,
    PolicyStatus,
)


def _condition() -> PolicyCondition:
    return PolicyCondition(
        field_path="metrics.groundedness.score",
        operator=PolicyConditionOperator.GREATER_THAN_OR_EQUAL,
        expected_value=0.8,
    )


def _rule() -> PolicyRule:
    return PolicyRule(
        rule_id="rule-1",
        name="groundedness gate",
        conditions=(_condition(),),
        effect=PolicyEffect.APPROVE,
        reason_template="Groundedness score passed the gate.",
        priority=10,
    )


def test_create_valid_policy() -> None:
    policy = GovernancePolicy(
        policy_id="policy-1",
        version="2026-07-02",
        name="quality gate",
        description="Approve candidates that pass quality thresholds.",
        status=PolicyStatus.ACTIVE,
        target_types=(DecisionTargetType.CANDIDATE,),
        rules=(_rule(),),
        created_by="governance-admin",
        created_at=datetime(2026, 7, 2, tzinfo=UTC),
        metadata={"source": "unit-test"},
    )

    assert policy.policy_id == "policy-1"
    assert policy.status == PolicyStatus.ACTIVE
    assert policy.target_types == (DecisionTargetType.CANDIDATE,)
    assert policy.rules[0].rule_id == "rule-1"
    assert policy.metadata == {"source": "unit-test"}


def test_reject_empty_policy_id() -> None:
    with pytest.raises(DecisionValidationError):
        GovernancePolicy(
            policy_id=" ",
            version="2026-07-02",
            name="quality gate",
            description=None,
            status=PolicyStatus.ACTIVE,
            target_types=(DecisionTargetType.CANDIDATE,),
            rules=(_rule(),),
            created_by="governance-admin",
            created_at=datetime(2026, 7, 2, tzinfo=UTC),
        )


def test_reject_empty_policy_version() -> None:
    with pytest.raises(DecisionValidationError):
        GovernancePolicy(
            policy_id="policy-1",
            version=" ",
            name="quality gate",
            description=None,
            status=PolicyStatus.ACTIVE,
            target_types=(DecisionTargetType.CANDIDATE,),
            rules=(_rule(),),
            created_by="governance-admin",
            created_at=datetime(2026, 7, 2, tzinfo=UTC),
        )


def test_reject_policy_with_no_target_types() -> None:
    with pytest.raises(DecisionValidationError):
        GovernancePolicy(
            policy_id="policy-1",
            version="2026-07-02",
            name="quality gate",
            description=None,
            status=PolicyStatus.ACTIVE,
            target_types=(),
            rules=(_rule(),),
            created_by="governance-admin",
            created_at=datetime(2026, 7, 2, tzinfo=UTC),
        )


def test_reject_policy_with_no_rules() -> None:
    with pytest.raises(DecisionValidationError):
        GovernancePolicy(
            policy_id="policy-1",
            version="2026-07-02",
            name="quality gate",
            description=None,
            status=PolicyStatus.ACTIVE,
            target_types=(DecisionTargetType.CANDIDATE,),
            rules=(),
            created_by="governance-admin",
            created_at=datetime(2026, 7, 2, tzinfo=UTC),
        )


def test_create_valid_policy_rule() -> None:
    rule = _rule()

    assert rule.rule_id == "rule-1"
    assert rule.conditions == (_condition(),)
    assert rule.effect == PolicyEffect.APPROVE
    assert rule.priority == 10


def test_reject_rule_with_no_conditions() -> None:
    with pytest.raises(DecisionValidationError):
        PolicyRule(
            rule_id="rule-1",
            name="groundedness gate",
            conditions=(),
            effect=PolicyEffect.APPROVE,
            reason_template="Groundedness score passed the gate.",
            priority=10,
        )


def test_reject_empty_field_path() -> None:
    with pytest.raises(DecisionValidationError):
        PolicyCondition(
            field_path=" ",
            operator=PolicyConditionOperator.EXISTS,
        )


def test_reject_missing_expected_value_for_comparison_operator() -> None:
    with pytest.raises(DecisionValidationError):
        PolicyCondition(
            field_path="metrics.groundedness.score",
            operator=PolicyConditionOperator.GREATER_THAN,
            expected_value=None,
        )


def test_reject_negative_rule_priority() -> None:
    with pytest.raises(DecisionValidationError):
        PolicyRule(
            rule_id="rule-1",
            name="groundedness gate",
            conditions=(_condition(),),
            effect=PolicyEffect.APPROVE,
            reason_template="Groundedness score passed the gate.",
            priority=-1,
        )
