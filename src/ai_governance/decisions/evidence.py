from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ai_governance.decisions.enums import DecisionTargetType
from ai_governance.decisions.exceptions import DecisionValidationError
from ai_governance.decisions.evidence_validation import (
    require_missing_evidence_severity,
)
from ai_governance.decisions.validation import (
    coerce_enum,
    copy_mapping,
    require_non_empty,
)


@dataclass(frozen=True)
class EvidenceNode:
    """
    Evidence graph node projected from an ontology entity.
    """

    entity_type: str
    entity_id: str
    label: str | None = None
    lifecycle: str | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty("evidence node entity_type", self.entity_type)
        require_non_empty("evidence node entity_id", self.entity_id)
        object.__setattr__(self, "attributes", copy_mapping(self.attributes))
        object.__setattr__(self, "metadata", copy_mapping(self.metadata))


@dataclass(frozen=True)
class EvidenceEdge:
    """
    Evidence graph edge projected from an ontology relationship.
    """

    relationship_type: str
    source_type: str
    source_id: str
    target_type: str
    target_id: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty("evidence edge relationship_type", self.relationship_type)
        require_non_empty("evidence edge source_type", self.source_type)
        require_non_empty("evidence edge source_id", self.source_id)
        require_non_empty("evidence edge target_type", self.target_type)
        require_non_empty("evidence edge target_id", self.target_id)
        object.__setattr__(self, "metadata", copy_mapping(self.metadata))


@dataclass(frozen=True)
class MissingEvidence:
    """
    Explicit report of missing or incomplete evidence.
    """

    evidence_type: str
    reason: str
    severity: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty("missing evidence evidence_type", self.evidence_type)
        require_non_empty("missing evidence reason", self.reason)
        require_missing_evidence_severity(self.severity)
        object.__setattr__(self, "metadata", copy_mapping(self.metadata))


@dataclass(frozen=True)
class DecisionEvidenceGraph:
    """
    Read-only evidence subgraph for one governance decision target.
    """

    target_type: DecisionTargetType | str
    target_id: str
    nodes: Sequence[EvidenceNode] = ()
    edges: Sequence[EvidenceEdge] = ()
    missing: Sequence[MissingEvidence] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty("evidence graph target_id", self.target_id)
        object.__setattr__(
            self,
            "target_type",
            coerce_enum(
                "evidence graph target_type",
                DecisionTargetType,
                self.target_type,
            ),
        )
        nodes = tuple(self.nodes)
        edges = tuple(self.edges)
        missing = tuple(self.missing)
        for node in nodes:
            if not isinstance(node, EvidenceNode):
                raise DecisionValidationError(
                    "Decision evidence graph nodes must be EvidenceNode instances."
                )
        for edge in edges:
            if not isinstance(edge, EvidenceEdge):
                raise DecisionValidationError(
                    "Decision evidence graph edges must be EvidenceEdge instances."
                )
        for item in missing:
            if not isinstance(item, MissingEvidence):
                raise DecisionValidationError(
                    "Decision evidence graph missing entries must be "
                    "MissingEvidence instances."
                )

        object.__setattr__(
            self,
            "nodes",
            tuple(
                sorted(
                    nodes,
                    key=lambda node: (node.entity_type, node.entity_id),
                )
            ),
        )
        object.__setattr__(
            self,
            "edges",
            tuple(
                sorted(
                    edges,
                    key=lambda edge: (
                        edge.relationship_type,
                        edge.source_type,
                        edge.source_id,
                        edge.target_type,
                        edge.target_id,
                    ),
                )
            ),
        )
        object.__setattr__(
            self,
            "missing",
            tuple(
                sorted(
                    missing,
                    key=lambda item: (
                        item.severity,
                        item.evidence_type,
                        item.reason,
                    ),
                )
            ),
        )
        object.__setattr__(self, "metadata", copy_mapping(self.metadata))


@dataclass(frozen=True)
class DecisionEvidenceSummary:
    """
    Decision-ready evidence identifiers extracted from an evidence graph.
    """

    target_type: DecisionTargetType | str
    target_id: str
    evaluation_result_ids: Sequence[str] = ()
    metric_ids: Sequence[str] = ()
    drift_analysis_ids: Sequence[str] = ()
    leaderboard_ids: Sequence[str] = ()
    job_ids: Sequence[str] = ()
    mcp_audit_ids: Sequence[str] = ()
    policy_ids: Sequence[str] = ()
    missing: Sequence[MissingEvidence] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty("evidence summary target_id", self.target_id)
        object.__setattr__(
            self,
            "target_type",
            coerce_enum(
                "evidence summary target_type",
                DecisionTargetType,
                self.target_type,
            ),
        )
        for field_name in (
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
        object.__setattr__(self, "missing", tuple(self.missing))
        object.__setattr__(self, "metadata", copy_mapping(self.metadata))
