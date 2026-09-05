"""Public extension points for provider-neutral causal outcome evaluation."""

from __future__ import annotations

from typing import Protocol

from ai_governance.domain.causal_audit import InterventionConfiguration, OutcomeScore


class OutcomeScorer(Protocol):
    """Score an observed or isolated counterfactual outcome without using logits."""

    evaluator_ref: str

    def score_baseline(self, execution_id: str, event) -> OutcomeScore: ...

    def score_counterfactual(self, execution_id: str, tool_event, sample_index: int, intervention: InterventionConfiguration) -> OutcomeScore: ...


__all__ = ["OutcomeScorer"]
