from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import Enum
from typing import Any, TypeVar

from ai_governance.decisions.exceptions import DecisionValidationError


TEnum = TypeVar("TEnum", bound=Enum)


def require_non_empty(field_name: str, value: str) -> None:
    if not value.strip():
        raise DecisionValidationError(f"Decision {field_name} must not be empty.")


def require_optional_non_empty(field_name: str, value: str | None) -> None:
    if value is not None and not value.strip():
        raise DecisionValidationError(f"Decision {field_name} must not be empty.")


def require_timezone_aware(field_name: str, value: datetime) -> None:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise DecisionValidationError(
            f"Decision {field_name} must be timezone-aware."
        )


def copy_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return dict(value)


def coerce_enum(
    field_name: str,
    enum_type: type[TEnum],
    value: TEnum | str,
) -> TEnum:
    try:
        return enum_type(value)
    except ValueError as exc:
        raise DecisionValidationError(
            f"Unknown decision {field_name}: {value!r}."
        ) from exc
