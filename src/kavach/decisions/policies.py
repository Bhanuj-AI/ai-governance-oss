from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from kavach.decisions.enums import DecisionTargetType
from kavach.decisions.exceptions import DecisionValidationError
from kavach.decisions.policy_enums import (
    PolicyConditionOperator,
    PolicyEffect,
    PolicyStatus,
)
from kavach.decisions.policy_validation import (
    require_condition_expected_value,
    require_non_negative,
)
from kavach.decisions.validation import (
    coerce_enum,
    copy_mapping,
    require_non_empty,
    require_timezone_aware,
)


_MISSING = object()


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class PolicyCondition:
    """
    Structured condition evaluated against flattened policy evidence.
    """

    field_path: str
    operator: PolicyConditionOperator | str
    expected_value: Any | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty("policy condition field_path", self.field_path)
        operator = coerce_enum(
            "policy condition operator",
            PolicyConditionOperator,
            self.operator,
        )
        require_condition_expected_value(operator, self.expected_value)

        object.__setattr__(self, "operator", operator)
        object.__setattr__(self, "metadata", copy_mapping(self.metadata))


@dataclass(frozen=True)
class PolicyRule:
    """
    Ordered policy rule with all-match structured conditions.
    """

    rule_id: str
    name: str
    conditions: Sequence[PolicyCondition]
    effect: PolicyEffect | str
    reason_template: str
    priority: int
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty("policy rule rule_id", self.rule_id)
        require_non_empty("policy rule name", self.name)
        require_non_empty("policy rule reason_template", self.reason_template)
        require_non_negative("policy rule priority", self.priority)

        conditions = tuple(self.conditions)
        if not conditions:
            raise DecisionValidationError(
                "Decision policy rule conditions must not be empty."
            )

        for condition in conditions:
            if not isinstance(condition, PolicyCondition):
                raise DecisionValidationError(
                    "Decision policy rule conditions must be "
                    "PolicyCondition instances."
                )

        object.__setattr__(
            self,
            "effect",
            coerce_enum("policy rule effect", PolicyEffect, self.effect),
        )
        object.__setattr__(self, "conditions", conditions)
        object.__setattr__(self, "metadata", copy_mapping(self.metadata))


@dataclass(frozen=True)
class GovernancePolicy:
    """
    Versioned deterministic policy definition for governance decisions.
    """

    policy_id: str
    version: str
    name: str
    description: str | None
    status: PolicyStatus | str
    target_types: Sequence[DecisionTargetType | str]
    rules: Sequence[PolicyRule]
    created_by: str
    created_at: datetime = field(default_factory=_now)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty("policy_id", self.policy_id)
        require_non_empty("policy version", self.version)
        require_non_empty("policy name", self.name)
        require_non_empty("policy created_by", self.created_by)
        require_timezone_aware("policy created_at", self.created_at)

        target_types = tuple(
            coerce_enum("policy target_type", DecisionTargetType, target_type)
            for target_type in self.target_types
        )
        if not target_types:
            raise DecisionValidationError(
                "Decision policy target_types must not be empty."
            )

        rules = tuple(self.rules)
        if not rules:
            raise DecisionValidationError(
                "Decision policy rules must not be empty."
            )

        for rule in rules:
            if not isinstance(rule, PolicyRule):
                raise DecisionValidationError(
                    "Decision policy rules must be PolicyRule instances."
                )

        object.__setattr__(
            self,
            "status",
            coerce_enum("policy status", PolicyStatus, self.status),
        )
        object.__setattr__(self, "target_types", target_types)
        object.__setattr__(self, "rules", rules)
        object.__setattr__(self, "metadata", copy_mapping(self.metadata))


@dataclass(frozen=True)
class PolicyEvaluationContext:
    """
    Flattened evidence available to governance policy evaluation.
    """

    target_type: DecisionTargetType | str
    target_id: str
    evidence: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty("policy evaluation target_id", self.target_id)
        object.__setattr__(
            self,
            "target_type",
            coerce_enum(
                "policy evaluation target_type",
                DecisionTargetType,
                self.target_type,
            ),
        )
        object.__setattr__(self, "evidence", copy_mapping(self.evidence))
        object.__setattr__(self, "metadata", copy_mapping(self.metadata))


@dataclass(frozen=True)
class PolicyEvaluationOutcome:
    """
    Structured result of evaluating one governance policy.
    """

    policy_id: str
    policy_version: str
    matched_rule_id: str | None
    effect: PolicyEffect | str
    reason: str
    matched: bool
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty("policy outcome policy_id", self.policy_id)
        require_non_empty("policy outcome policy_version", self.policy_version)
        require_non_empty("policy outcome reason", self.reason)
        object.__setattr__(
            self,
            "effect",
            coerce_enum("policy outcome effect", PolicyEffect, self.effect),
        )
        object.__setattr__(self, "metadata", copy_mapping(self.metadata))


@dataclass(frozen=True)
class PolicyEvaluationTraceItem:
    """
    Diagnostic outcome for one policy condition evaluation.
    """

    rule_id: str
    rule_name: str
    condition_field_path: str
    operator: PolicyConditionOperator | str
    expected_value: Any | None
    actual_value: Any | None
    matched: bool
    reason: str | None = None

    def __post_init__(self) -> None:
        require_non_empty("policy trace rule_id", self.rule_id)
        require_non_empty("policy trace rule_name", self.rule_name)
        require_non_empty(
            "policy trace condition_field_path",
            self.condition_field_path,
        )
        object.__setattr__(
            self,
            "operator",
            coerce_enum(
                "policy trace operator",
                PolicyConditionOperator,
                self.operator,
            ),
        )


@dataclass(frozen=True)
class PolicyEvaluationTraceOutcome:
    """
    Final policy evaluation outcome plus condition-level trace.
    """

    outcome: PolicyEvaluationOutcome
    matched_conditions: Sequence[PolicyCondition]
    unmatched_conditions: Sequence[PolicyCondition]
    evaluation_trace: Sequence[PolicyEvaluationTraceItem]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "matched_conditions",
            tuple(self.matched_conditions),
        )
        object.__setattr__(
            self,
            "unmatched_conditions",
            tuple(self.unmatched_conditions),
        )
        object.__setattr__(
            self,
            "evaluation_trace",
            tuple(self.evaluation_trace),
        )


class GovernancePolicyEvaluator:
    """
    Deterministic evaluator for structured governance policies.
    """

    def evaluate(
        self,
        policy: GovernancePolicy,
        context: PolicyEvaluationContext,
    ) -> PolicyEvaluationOutcome:
        if context.target_type not in policy.target_types:
            return self._no_decision(
                policy,
                "Policy does not target this entity type.",
            )

        for rule in sorted(policy.rules, key=lambda item: item.priority):
            if self._rule_matches(rule, context):
                return PolicyEvaluationOutcome(
                    policy_id=policy.policy_id,
                    policy_version=policy.version,
                    matched_rule_id=rule.rule_id,
                    effect=rule.effect,
                    reason=rule.reason_template,
                    matched=True,
                    metadata={"rule_priority": rule.priority},
                )

        return self._no_decision(policy, "No policy rule matched.")

    def evaluate_with_trace(
        self,
        policy: GovernancePolicy,
        context: PolicyEvaluationContext,
    ) -> PolicyEvaluationTraceOutcome:
        if context.target_type not in policy.target_types:
            return PolicyEvaluationTraceOutcome(
                outcome=self._no_decision(
                    policy,
                    "Policy does not target this entity type.",
                ),
                matched_conditions=(),
                unmatched_conditions=(),
                evaluation_trace=(),
            )

        trace: list[PolicyEvaluationTraceItem] = []
        for rule in sorted(policy.rules, key=lambda item: item.priority):
            rule_trace = [
                self._trace_condition(rule, condition, context.evidence)
                for condition in rule.conditions
            ]
            trace.extend(rule_trace)

            if all(item.matched for item in rule_trace):
                return PolicyEvaluationTraceOutcome(
                    outcome=PolicyEvaluationOutcome(
                        policy_id=policy.policy_id,
                        policy_version=policy.version,
                        matched_rule_id=rule.rule_id,
                        effect=rule.effect,
                        reason=rule.reason_template,
                        matched=True,
                        metadata={"rule_priority": rule.priority},
                    ),
                    matched_conditions=rule.conditions,
                    unmatched_conditions=(),
                    evaluation_trace=trace,
                )

        return PolicyEvaluationTraceOutcome(
            outcome=self._no_decision(policy, "No policy rule matched."),
            matched_conditions=(),
            unmatched_conditions=tuple(
                condition
                for rule in sorted(policy.rules, key=lambda item: item.priority)
                for condition in rule.conditions
            ),
            evaluation_trace=trace,
        )

    def _rule_matches(
        self,
        rule: PolicyRule,
        context: PolicyEvaluationContext,
    ) -> bool:
        return all(
            self._condition_matches(condition, context.evidence)
            for condition in rule.conditions
        )

    def _condition_matches(
        self,
        condition: PolicyCondition,
        evidence: Mapping[str, Any],
    ) -> bool:
        actual_value = self._resolve_field_path(evidence, condition.field_path)
        exists = actual_value is not _MISSING

        match condition.operator:
            case PolicyConditionOperator.EXISTS:
                return exists
            case PolicyConditionOperator.MISSING:
                return not exists
            case _ if not exists:
                return False
            case PolicyConditionOperator.GREATER_THAN:
                return self._compare(actual_value, condition.expected_value, ">")
            case PolicyConditionOperator.GREATER_THAN_OR_EQUAL:
                return self._compare(
                    actual_value,
                    condition.expected_value,
                    ">=",
                )
            case PolicyConditionOperator.LESS_THAN:
                return self._compare(actual_value, condition.expected_value, "<")
            case PolicyConditionOperator.LESS_THAN_OR_EQUAL:
                return self._compare(
                    actual_value,
                    condition.expected_value,
                    "<=",
                )
            case PolicyConditionOperator.EQUALS:
                return actual_value == condition.expected_value
            case PolicyConditionOperator.NOT_EQUALS:
                return actual_value != condition.expected_value
            case PolicyConditionOperator.IN:
                return self._contains(condition.expected_value, actual_value)
            case PolicyConditionOperator.NOT_IN:
                return not self._contains(
                    condition.expected_value,
                    actual_value,
                )

    def _trace_condition(
        self,
        rule: PolicyRule,
        condition: PolicyCondition,
        evidence: Mapping[str, Any],
    ) -> PolicyEvaluationTraceItem:
        actual_value = self._resolve_field_path(evidence, condition.field_path)
        matched = self._condition_matches(condition, evidence)
        return PolicyEvaluationTraceItem(
            rule_id=rule.rule_id,
            rule_name=rule.name,
            condition_field_path=condition.field_path,
            operator=condition.operator,
            expected_value=condition.expected_value,
            actual_value=None if actual_value is _MISSING else actual_value,
            matched=matched,
            reason=None if matched else "Condition did not match.",
        )

    def _resolve_field_path(
        self,
        evidence: Mapping[str, Any],
        field_path: str,
    ) -> Any:
        current: Any = evidence
        for segment in field_path.split("."):
            if not isinstance(current, Mapping) or segment not in current:
                return _MISSING
            current = current[segment]
        return current

    def _compare(
        self,
        actual_value: Any,
        expected_value: Any,
        operator: str,
    ) -> bool:
        try:
            match operator:
                case ">":
                    return actual_value > expected_value
                case ">=":
                    return actual_value >= expected_value
                case "<":
                    return actual_value < expected_value
                case "<=":
                    return actual_value <= expected_value
        except TypeError:
            return False

        return False

    def _contains(
        self,
        expected_value: Any,
        actual_value: Any,
    ) -> bool:
        try:
            return actual_value in expected_value
        except TypeError:
            return False

    def _no_decision(
        self,
        policy: GovernancePolicy,
        reason: str,
    ) -> PolicyEvaluationOutcome:
        return PolicyEvaluationOutcome(
            policy_id=policy.policy_id,
            policy_version=policy.version,
            matched_rule_id=None,
            effect=PolicyEffect.NO_DECISION,
            reason=reason,
            matched=False,
            metadata={},
        )
