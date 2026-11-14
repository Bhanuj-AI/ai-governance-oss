from __future__ import annotations

import pytest

from ai_governance.settings_control.operational import duration_seconds


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ("15ms", 0.015),
        ("10s", 10),
        (" 2H ", 7200),
        ("3w", 1814400),
    ),
)
def test_duration_seconds_parses_positive_ascii_amounts(value: str, expected: float) -> None:
    assert duration_seconds(value) == expected


@pytest.mark.parametrize(
    "value",
    (
        "",
        "0s",
        "01s",
        "1.5s",
        "1minute",
        "١s",
        "1" * 10_000 + "x",
    ),
)
def test_duration_seconds_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError, match="Invalid duration"):
        duration_seconds(value)
