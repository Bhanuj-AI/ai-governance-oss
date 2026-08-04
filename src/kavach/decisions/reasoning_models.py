from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from kavach.decisions.enums import DecisionTargetType, DecisionType
from kavach.decisions.evidence import (
    DecisionEvidenceGraph,
    MissingEvidence,
)
from kavach.decisions.explanation import DecisionExplanation
from kavach.decisions.models import GovernanceDecision
from kavach.decisions.policies import PolicyEvaluationOutcome
from kavach.decisions.validation import (
    coerce_enum,
    copy_mapping,
    require_non_empty,
    require_optional_non_empty,
)


DEFAULT_REASONING_PRODUCER_ID = "kavach-governance-reasoning-engine"


@dataclass(frozen=True)
class GovernanceReasoningRequest:
    """
    Request to reason over one governance target.
    """

    target_type: DecisionTargetType | str
    target_id: str
    decision_type: DecisionType | str
    policy_ids: Sequence[str] = ()
    correlation_id: str | None = None
    request_id: str | None = None
    producer_id: str = DEFAULT_REASONING_PRODUCER_ID
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty("reasoning request target_id", self.target_id)
        require_non_empty("reasoning request producer_id", self.producer_id)
        require_optional_non_empty(
            "reasoning request correlation_id",
            self.correlation_id,
        )
        require_optional_non_empty(
            "reasoning request request_id",
            self.request_id,
        )
        policy_ids = tuple(self.policy_ids)
        for policy_id in policy_ids:
            require_non_empty("reasoning request policy_id", policy_id)

        object.__setattr__(
            self,
            "target_type",
            coerce_enum(
                "reasoning request target_type",
                DecisionTargetType,
                self.target_type,
            ),
        )
        object.__setattr__(
            self,
            "decision_type",
            coerce_enum(
                "reasoning request decision_type",
                DecisionType,
                self.decision_type,
            ),
        )
        object.__setattr__(self, "policy_ids", policy_ids)
        object.__setattr__(self, "metadata", copy_mapping(self.metadata))


@dataclass(frozen=True)
class ReasoningEvidenceSummary:
    """
    Deterministic summary of decision-ready evidence.
    """

    target_type: DecisionTargetType | str
    target_id: str
    metric_scores: Mapping[str, float] = field(default_factory=dict)
    metric_failures: Sequence[str] = ()
    threshold_breaches: Sequence[str] = ()
    drift_severity: str | None = None
    latest_job_status: str | None = None
    latest_audit_status: str | None = None
    evaluation_result_ids: Sequence[str] = ()
    metric_ids: Sequence[str] = ()
    drift_analysis_ids: Sequence[str] = ()
    leaderboard_ids: Sequence[str] = ()
    job_ids: Sequence[str] = ()
    mcp_audit_ids: Sequence[str] = ()
    policy_ids: Sequence[str] = ()
    missing_evidence: Sequence[MissingEvidence] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty("reasoning evidence summary target_id", self.target_id)
        object.__setattr__(
            self,
            "target_type",
            coerce_enum(
                "reasoning evidence summary target_type",
                DecisionTargetType,
                self.target_type,
            ),
        )
        object.__setattr__(
            self,
            "metric_scores",
            {
                metric_name: self.metric_scores[metric_name]
                for metric_name in sorted(self.metric_scores)
            },
        )
        for field_name in (
            "metric_failures",
            "threshold_breaches",
            "evaluation_result_ids",
            "metric_ids",
            "drift_analysis_ids",
            "leaderboard_ids",
            "job_ids",
            "mcp_audit_ids",
            "policy_ids",
        ):
            object.__setattr__(
                self,
                field_name,
                tuple(sorted(getattr(self, field_name))),
            )
        object.__setattr__(
            self,
            "missing_evidence",
            tuple(self.missing_evidence),
        )
        object.__setattr__(self, "metadata", copy_mapping(self.metadata))


@dataclass(frozen=True)
class GovernanceReasoningOutcome:
    """
    Complete deterministic reasoning result for one governance target.
    """

    decision: GovernanceDecision
    evidence_graph: DecisionEvidenceGraph
    evidence_summary: ReasoningEvidenceSummary
    policy_outcomes: Sequence[PolicyEvaluationOutcome]
    explanation: DecisionExplanation

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "policy_outcomes",
            tuple(self.policy_outcomes),
        )
