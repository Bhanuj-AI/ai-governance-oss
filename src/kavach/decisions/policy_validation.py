from __future__ import annotations

from typing import Any

from kavach.decisions.exceptions import DecisionValidationError
from kavach.decisions.policy_enums import PolicyConditionOperator


def require_non_negative(field_name: str, value: int) -> None:
    if value < 0:
        raise DecisionValidationError(
            f"Decision {field_name} must be greater than or equal to zero."
        )


def require_condition_expected_value(
    operator: PolicyConditionOperator,
    expected_value: Any | None,
) -> None:
    if (
        expected_value is None
        and operator
        not in {
            PolicyConditionOperator.EXISTS,
            PolicyConditionOperator.MISSING,
        }
    ):
        raise DecisionValidationError(
            "Decision policy condition expected_value may be None only for "
            "EXISTS and MISSING operators."
        )
