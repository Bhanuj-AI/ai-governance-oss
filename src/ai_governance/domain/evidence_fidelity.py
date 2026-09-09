"""Immutable evidence-fidelity contracts derived from runtime event evidence.

These records compare two views of one execution.  They deliberately do not
own or duplicate execution events: the Agent Runtime event store remains the
authoritative source of observable trajectory evidence.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType


class EvidenceFidelityStatus(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class EvidenceCompleteness(str, Enum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    UNSUPPORTED = "UNSUPPORTED"


class EvidenceConclusion(str, Enum):
    SUPPORTED = "SUPPORTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class EvidenceProjection:
    """Deterministic, reference-only view of one execution's evidence."""

    source_execution_id: str
    source_artifact_digest: str
    projection_type: str
    projection_version: str
    projection_fingerprint: str
    retained_evidence_types: tuple[str, ...]
    missing_evidence_types: tuple[str, ...]
    completeness: EvidenceCompleteness
    event_count: int

    def __post_init__(self) -> None:
        for name, value in (
            ("source_execution_id", self.source_execution_id),
            ("source_artifact_digest", self.source_artifact_digest),
            ("projection_type", self.projection_type),
            ("projection_version", self.projection_version),
            ("projection_fingerprint", self.projection_fingerprint),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty.")
        if self.event_count < 0:
            raise ValueError("event_count must be non-negative.")
        object.__setattr__(self, "retained_evidence_types", tuple(self.retained_evidence_types))
        object.__setattr__(self, "missing_evidence_types", tuple(self.missing_evidence_types))


@dataclass(frozen=True)
class EvidenceFidelityComparison:
    """Tenant-scoped immutable conclusion about projection information loss."""

    comparison_id: str
    organization_id: str
    project_id: str | None
    source_execution_id: str
    request_fingerprint: str
    created_by: str
    created_at: datetime
    status: EvidenceFidelityStatus
    trajectory: EvidenceProjection | None = None
    runtime_projection: EvidenceProjection | None = None
    outcome_preserved: bool | None = None
    score_preserved: bool | None = None
    token_usage_preserved: bool | None = None
    duration_preserved: bool | None = None
    action_count_preserved: bool | None = None
    ordering_preserved: bool | None = None
    termination_reason_preserved: bool | None = None
    recovery_sequence_preserved: bool | None = None
    failure_classification_preserved: bool | None = None
    causal_evidence_complete: bool | None = None
    trajectory_classification: EvidenceConclusion = EvidenceConclusion.INSUFFICIENT_EVIDENCE
    runtime_projection_classification: EvidenceConclusion = EvidenceConclusion.INSUFFICIENT_EVIDENCE
    retained_evidence_types: tuple[str, ...] = ()
    missing_evidence_types: tuple[str, ...] = ()
    unsupported_conclusions: tuple[str, ...] = ()
    failure_code: str | None = None
    failure_reason: str | None = None
    provenance: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, value in (
            ("comparison_id", self.comparison_id),
            ("organization_id", self.organization_id),
            ("source_execution_id", self.source_execution_id),
            ("request_fingerprint", self.request_fingerprint),
            ("created_by", self.created_by),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty.")
        if self.project_id is not None and not self.project_id.strip():
            raise ValueError("project_id must not be blank.")
        if self.status is EvidenceFidelityStatus.SUCCEEDED and (
            self.trajectory is None or self.runtime_projection is None
        ):
            raise ValueError("Succeeded comparisons require both evidence projections.")
        if self.status is EvidenceFidelityStatus.FAILED and not self.failure_code:
            raise ValueError("Failed comparisons require a failure_code.")
        object.__setattr__(self, "retained_evidence_types", tuple(self.retained_evidence_types))
        object.__setattr__(self, "missing_evidence_types", tuple(self.missing_evidence_types))
        object.__setattr__(self, "unsupported_conclusions", tuple(self.unsupported_conclusions))
        object.__setattr__(self, "provenance", MappingProxyType(dict(self.provenance)))
