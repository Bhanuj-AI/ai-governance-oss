"""Stable, deterministic intelligence reasoning contracts.

The intelligence plane plans and aggregates evidence; it never grants an
advisor direct access to a repository, query engine, or language model.
Concrete advisors remain independently deployable services or plugins.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping, Protocol

from ai_governance.spi.context import TenantContext


class FindingSeverity(StrEnum):
    """The highest materiality of an advisor's deterministic evidence."""

    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FindingStatus(StrEnum):
    """The outcome of one bounded advisor invocation."""

    COMPLETED = "COMPLETED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class AdvisorRequest:
    """A stateless, tenant-scoped question sent to an advisor.

    ``context`` is caller-supplied, JSON-compatible routing data such as a
    change-plan ID. Advisors must treat it as input, not retained memory.
    """

    question: str
    tenant: TenantContext
    context: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        question = self.question.strip()
        if not question:
            raise ValueError("An intelligence question is required.")
        object.__setattr__(self, "question", question)
        object.__setattr__(self, "context", MappingProxyType(dict(self.context)))


@dataclass(frozen=True)
class AdvisorEvidence:
    """One structured, traceable piece of advisor evidence."""

    evidence_id: str
    kind: str
    summary: str
    attributes: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.evidence_id or not self.kind or not self.summary:
            raise ValueError("Advisor evidence requires an ID, kind, and summary.")
        object.__setattr__(self, "attributes", MappingProxyType(dict(self.attributes)))

    def as_dict(self) -> dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "kind": self.kind,
            "summary": self.summary,
            "attributes": dict(self.attributes),
        }


@dataclass(frozen=True)
class AdvisorFinding:
    """Structured output from one advisor; deliberately not generated prose."""

    advisor_id: str
    advisor_version: str
    severity: FindingSeverity
    summary: str
    findings: tuple[AdvisorEvidence, ...] = ()
    status: FindingStatus = FindingStatus.COMPLETED
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.advisor_id or not self.advisor_version or not self.summary:
            raise ValueError("Advisor findings require an advisor identity and summary.")
        object.__setattr__(self, "findings", tuple(self.findings))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def as_dict(self) -> dict[str, object]:
        return {
            "advisor": self.advisor_id,
            "advisor_version": self.advisor_version,
            "status": self.status.value,
            "severity": self.severity.value,
            "summary": self.summary,
            "findings": [finding.as_dict() for finding in self.findings],
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class AdvisorDescriptor:
    """Discoverable, versioned metadata for an independently useful advisor."""

    advisor_id: str
    version: str
    title: str
    capabilities: tuple[str, ...]
    required_context: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.advisor_id or not self.version or not self.title:
            raise ValueError("Advisor descriptors require an ID, version, and title.")
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("Advisor descriptor capabilities must be unique.")
        if len(set(self.required_context)) != len(self.required_context):
            raise ValueError("Advisor required context keys must be unique.")

    def as_dict(self) -> dict[str, object]:
        return {
            "advisor": self.advisor_id,
            "version": self.version,
            "title": self.title,
            "capabilities": list(self.capabilities),
            "required_context": list(self.required_context),
        }


class Advisor(Protocol):
    """Versioned, evidence-only advisor contract owned by AI Governance Control Plane OSS."""

    @property
    def descriptor(self) -> AdvisorDescriptor:
        """Describe this advisor before a planner selects it."""
        ...

    def analyze(self, request: AdvisorRequest) -> AdvisorFinding:
        """Return bounded structured evidence for one tenant-scoped question."""
        ...


@dataclass(frozen=True)
class AdvisorSelection:
    """Auditable planner decision for one available advisor."""

    advisor_id: str
    selected: bool
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {"advisor": self.advisor_id, "selected": self.selected, "reason": self.reason}


@dataclass(frozen=True)
class ReasoningPlan:
    """A versioned, replayable selection of advisors for one question."""

    planner_id: str
    planner_version: str
    selected_advisor_ids: tuple[str, ...]
    selections: tuple[AdvisorSelection, ...]

    def __post_init__(self) -> None:
        selected = tuple(self.selected_advisor_ids)
        if len(set(selected)) != len(selected):
            raise ValueError("A reasoning plan cannot select an advisor twice.")
        selected_from_decisions = tuple(
            decision.advisor_id for decision in self.selections if decision.selected
        )
        if selected != selected_from_decisions:
            raise ValueError("Selected advisors must match the recorded decisions.")
        object.__setattr__(self, "selected_advisor_ids", selected)
        object.__setattr__(self, "selections", tuple(self.selections))

    def as_dict(self) -> dict[str, object]:
        return {
            "planner": {"id": self.planner_id, "version": self.planner_version},
            "selected_advisors": list(self.selected_advisor_ids),
            "advisor_selections": [selection.as_dict() for selection in self.selections],
        }


class Planner(Protocol):
    """Deterministically select applicable advisors without gathering evidence."""

    @property
    def planner_id(self) -> str:
        """Return a stable planner strategy identifier."""
        ...

    @property
    def version(self) -> str:
        """Return the planner strategy version."""
        ...

    def plan(self, request: AdvisorRequest, advisors: tuple[AdvisorDescriptor, ...]) -> ReasoningPlan:
        """Select advisors and retain a reason for every decision."""
        ...


__all__ = [
    "Advisor", "AdvisorDescriptor", "AdvisorEvidence", "AdvisorFinding",
    "AdvisorRequest", "AdvisorSelection", "FindingSeverity", "FindingStatus",
    "Planner", "ReasoningPlan",
]
