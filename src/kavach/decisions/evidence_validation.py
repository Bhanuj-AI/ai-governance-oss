from __future__ import annotations

from kavach.decisions.exceptions import DecisionValidationError


MISSING_EVIDENCE_SEVERITIES = frozenset({"INFO", "WARNING", "CRITICAL"})


def require_missing_evidence_severity(value: str) -> None:
    if value not in MISSING_EVIDENCE_SEVERITIES:
        raise DecisionValidationError(
            f"Unknown missing evidence severity: {value!r}."
        )
