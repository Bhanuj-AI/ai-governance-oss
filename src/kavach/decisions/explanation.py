from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from kavach.decisions.evidence import MissingEvidence
from kavach.decisions.models import (
    DecisionEvidenceReference,
    DecisionPolicyReference,
)
from kavach.decisions.validation import copy_mapping, require_non_empty


@dataclass(frozen=True)
class DecisionExplanation:
    """
    Deterministic explanation for a governance decision.
    """

    decision_id: str
    summary: str
    reasons: Sequence[str]
    evidence_references: Sequence[DecisionEvidenceReference]
    policy_references: Sequence[DecisionPolicyReference]
    missing_evidence: Sequence[MissingEvidence]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty("explanation decision_id", self.decision_id)
        require_non_empty("explanation summary", self.summary)
        object.__setattr__(self, "reasons", tuple(self.reasons))
        object.__setattr__(
            self,
            "evidence_references",
            tuple(self.evidence_references),
        )
        object.__setattr__(
            self,
            "policy_references",
            tuple(self.policy_references),
        )
        object.__setattr__(
            self,
            "missing_evidence",
            tuple(self.missing_evidence),
        )
        object.__setattr__(self, "metadata", copy_mapping(self.metadata))
