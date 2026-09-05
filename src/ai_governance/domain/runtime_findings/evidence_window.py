"""Deterministic finalization policy for Runtime Findings evidence windows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class EvidenceWindowFinalizationPolicy:
    """Defines when a closed evidence window is safe to reconcile.

    Events received after ``window_end + allowed_lateness`` are outside the
    finalized contract for that window and cannot contribute to its decision.
    """

    allowed_lateness_hours: int = 2

    def __post_init__(self) -> None:
        if not 0 <= self.allowed_lateness_hours <= 168:
            raise ValueError("allowed_lateness_hours must be between 0 and 168.")

    def finalizes_at(self, window_end: datetime) -> datetime:
        return window_end.astimezone(UTC) + timedelta(hours=self.allowed_lateness_hours)

    def is_finalized(self, window_end: datetime, now: datetime) -> bool:
        return now.astimezone(UTC) >= self.finalizes_at(window_end)
