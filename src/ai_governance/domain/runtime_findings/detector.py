"""Deterministic runtime detector contracts and configuration.

Every detector defines explicit detection rules: minimum observation
count, baseline window, current observation window, absolute and
relative thresholds, severity calculation, and deduplication identity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ai_governance.domain.runtime_findings.finding import (
    EvidenceReference,
    FindingSeverity,
    RuntimeFinding,
)


@dataclass(frozen=True)
class DetectorConfig:
    """Configuration for a single detector instance.

    Attributes:
        detector_id: Stable detector identifier.
        detector_version: Schema version for this detector.
        min_observation_count: Minimum observations before generating a finding.
        baseline_window_days: Number of days for the baseline window.
        observation_window_hours: Number of hours for the current window.
        absolute_threshold: Absolute metric threshold (e.g. failure_rate >= 0.10).
        relative_threshold: Relative change threshold (e.g. 2x increase).
        severity_levels: Mapping from metric ranges to severity levels.
        resolution_window_hours: Hours of normal metrics before auto-resolution.
    """

    detector_id: str
    detector_version: str = "1"
    min_observation_count: int = 50
    baseline_window_days: int = 7
    observation_window_hours: int = 24
    absolute_threshold: float = 0.0
    relative_threshold: float = 1.0
    severity_levels: dict[str, FindingSeverity] = field(default_factory=dict)
    resolution_window_hours: int = 48

    def __post_init__(self) -> None:
        if not self.detector_id.strip():
            raise ValueError("detector_id must not be empty.")
        if self.min_observation_count < 1:
            raise ValueError("min_observation_count must be >= 1.")
        if self.baseline_window_days < 1:
            raise ValueError("baseline_window_days must be >= 1.")
        if self.observation_window_hours < 1:
            raise ValueError("observation_window_hours must be >= 1.")


@dataclass(frozen=True)
class DetectorResult:
    """Output from one detector run against a subject.

    Attributes:
        finding: The generated finding, or None if no finding warranted.
        insufficient_data: True when sample size is too small to justify a finding.
    """

    finding: RuntimeFinding | None = None
    insufficient_data: bool = False


class RuntimeDetector(Protocol):
    """Deterministic detector contract.

    A detector reads aggregated metrics from the aggregation service
    and produces findings when thresholds are exceeded. It never
    accesses raw execution payloads.
    """

    @property
    def detector_id(self) -> str:
        """Return the stable detector identifier."""
        ...

    @property
    def detector_version(self) -> str:
        """Return the detector schema version."""
        ...

    @property
    def config(self) -> DetectorConfig:
        """Return the detector's configuration."""
        ...

    def detect(
        self,
        organization_id: str,
        project_id: str | None,
        subject_type: str,
        subject_id: str,
        baseline_metrics: dict[str, float],
        observed_metrics: dict[str, float],
        observation_count: int,
        related_execution_ids: tuple[str, ...] = (),
    ) -> DetectorResult:
        """Run detection logic and return findings.

        Args:
            organization_id: Tenant scope.
            project_id: Project scope (may be None).
            subject_type: Type of subject (agent, tool, model, policy, etc.).
            subject_id: Identifier of the subject.
            baseline_metrics: Metrics from the baseline window.
            observed_metrics: Metrics from the observation window.
            observation_count: Number of observations in the current window.
            related_execution_ids: Bounded list of related execution IDs.

        Returns:
            DetectorResult with an optional finding and insufficient_data flag.
        """
        ...


# -- Helper functions ---------------------------------------------------------


def _calculate_severity(
    severity_levels: dict[str, FindingSeverity],
    metric_name: str,
    metric_value: float,
) -> FindingSeverity:
    """Calculate severity based on configured thresholds."""
    if not severity_levels:
        return FindingSeverity.MEDIUM

    # Check in reverse order (highest severity first).
    for level in [FindingSeverity.CRITICAL, FindingSeverity.HIGH, FindingSeverity.MEDIUM, FindingSeverity.LOW, FindingSeverity.INFO]:
        threshold_key = f"{metric_name}_{level.value.lower()}_threshold"
        if (
            threshold_key in severity_levels
            and metric_value >= severity_levels[threshold_key]
        ):
            return level

    return FindingSeverity.INFO


def _build_evidence_references(
    detector_id: str,
    detector_version: str,
    baseline_metrics: dict[str, float],
    observed_metrics: dict[str, float],
    threshold: float,
) -> tuple[EvidenceReference, ...]:
    """Build bounded evidence references explaining why a finding was generated."""
    refs: list[EvidenceReference] = [
        EvidenceReference(kind="detector_id", value=detector_id),
        EvidenceReference(kind="detector_version", value=detector_version),
        EvidenceReference(kind="threshold", value=str(threshold)),
    ]
    for name, value in baseline_metrics.items():
        refs.append(EvidenceReference(kind=f"baseline_{name}", value=str(value)))
    for name, value in observed_metrics.items():
        refs.append(EvidenceReference(kind=f"observed_{name}", value=str(value)))
    return tuple(refs)
