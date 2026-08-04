from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationSummary:
    """
    Compact governance summary for one execution's evaluation history.

    The summary is optimized for list views, dashboards, and "latest status"
    reads. evaluated_at is currently sourced from evaluation metadata when
    present because the persistence model does not yet store a dedicated
    timestamp column.
    """

    execution_id: str
    latest_score: float | None
    evaluation_count: int
    provider: str | None
    provider_version: str | None
    evaluated_at: str | None
