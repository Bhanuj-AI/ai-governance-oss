"""Application service for deterministic runtime findings.

Orchestrates aggregation → detection → finding persistence.
Detection is idempotent: repeated runs update existing findings
rather than creating duplicates.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from ai_governance.domain.runtime_findings.detector import (
    DetectorConfig,
    DetectorResult,
    RuntimeDetector,
)
from ai_governance.domain.runtime_findings.detectors import _resolve_setting
from ai_governance.domain.runtime_findings.evidence_window import (
    EvidenceWindowFinalizationPolicy,
)
from ai_governance.domain.runtime_findings.finding import (
    FindingLifecycle,
    FindingReviewAction,
    FindingSeverity,
    FindingStatus,
    ReconciliationOutcome,
    ReconciliationRecord,
    ReconciliationWindow,
    RuntimeFinding,
)
from ai_governance.repositories.runtime_finding_repository import (
    RuntimeFindingListFilters,
)
from ai_governance.services.runtime_aggregation_service import (
    RuntimeAggregationService,
)
from ai_governance.settings_control.domain import SettingContext


@dataclass(frozen=True)
class ReconciliationFindingResult:
    finding_id: str
    outcome: ReconciliationOutcome
    consecutive_normal_windows: int
    required_normal_windows: int
    window: ReconciliationWindow | None = None
    detail: str | None = None


@dataclass(frozen=True)
class ReconciliationRunResult:
    outcomes: tuple[ReconciliationFindingResult, ...]

    @property
    def resolved(self) -> tuple[ReconciliationFindingResult, ...]:
        return tuple(item for item in self.outcomes if item.outcome == ReconciliationOutcome.RESOLVED)

    def __len__(self) -> int:
        """Compatibility: the previous service result was resolved findings."""
        return len(self.resolved)

    def __getitem__(self, index: int) -> ReconciliationFindingResult:
        return self.resolved[index]


@dataclass(frozen=True)
class RuntimeFindingWindows:
    """Resolved evidence spans for one detector and tenant project."""

    baseline: timedelta
    observation: timedelta
    resolution: timedelta
    baseline_label: str
    observation_label: str


class _ScopedConfiguration:
    """Present the Settings Control Plane in one fixed tenant scope."""

    def __init__(self, configuration_service: Any, context: SettingContext) -> None:
        self._configuration_service = configuration_service
        self._context = context

    def get(self, key: str) -> Any:
        try:
            return self._configuration_service.get(key, self._context)
        except TypeError:
            # Small test doubles that predate scoped settings retain their
            # one-argument contract; real ConfigurationService uses scope.
            return self._configuration_service.get(key)


class UnsupportedReconciliation(Exception):
    """Raised when a detector has no safe subject-level reconciliation path."""


class RuntimeFindingService:
    """Orchestrates deterministic runtime finding detection.

    This service reads aggregated metrics, runs detectors, and
    persists findings. It is deliberately decoupled from the
    ingestion service so detection failures never block runtime.
    """

    def __init__(
        self,
        aggregation_service: RuntimeAggregationService,
        finding_repository: Any,
        detectors: tuple[RuntimeDetector, ...] | None = None,
        configuration_service: Any | None = None,
        clock: Callable[[], datetime] | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self._aggregation = aggregation_service
        self._finding_repo = finding_repository
        self._detectors = detectors or ()
        self._config_service = configuration_service
        self._clock = clock or (lambda: datetime.now(UTC))
        self._environment = (
            environment
            if environment is not None
            else getattr(configuration_service, "environment", {})
        )

    def run_detection(
        self,
        organization_id: str,
        project_id: str | None = None,
        detector_ids: tuple[str, ...] | None = None,
    ) -> list[RuntimeFinding]:
        """Run all configured detectors and persist findings.

        Returns the list of findings created or updated.
        """
        now = self._clock()

        findings: list[RuntimeFinding] = []
        for detector in self._detectors:
            if detector_ids is not None and detector.detector_id not in detector_ids:
                continue

            try:
                scoped_detector = self._detector_for_scope(
                    detector, organization_id, project_id
                )
                windows = self._windows_for(scoped_detector.config, organization_id, project_id)
                observed_end = now
                observed_start = observed_end - windows.observation
                baseline_end = observed_start
                baseline_start = baseline_end - windows.baseline
                result = self._run_detector_for_subjects(
                    scoped_detector, organization_id, project_id,
                    baseline_start, baseline_end,
                    observed_start, observed_end,
                    windows=windows,
                )
                findings.extend(result)
            except Exception:  # noqa: BLE001, S110 - one detector cannot block the remaining set.
                # Detector failure must not prevent other detectors from running.
                pass

        return findings

    def list_findings(
        self,
        *,
        organization_id: str,
        project_id: str | None = None,
        finding_type: str | None = None,
        subject_type: str | None = None,
        subject_id: str | None = None,
        severity: FindingSeverity | None = None,
        status: FindingStatus | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        limit: int = 50,
    ) -> list[RuntimeFinding]:
        """Return tenant-scoped runtime findings with validated list filters."""
        return self._finding_repo.list(
            RuntimeFindingListFilters(
                finding_type=finding_type,
                subject_type=subject_type,
                subject_id=subject_id,
                severity=severity,
                status=status,
                created_after=created_after,
                created_before=created_before,
                limit=limit,
            ),
            organization_id,
            project_id,
        )

    def run_detection_for_agent(
        self,
        organization_id: str,
        project_id: str | None,
        agent_id: str,
        detector_ids: tuple[str, ...] | None = None,
    ) -> list[RuntimeFinding]:
        """Run detectors for a specific agent."""
        now = self._clock()

        findings: list[RuntimeFinding] = []
        for detector in self._detectors:
            if detector_ids is not None and detector.detector_id not in detector_ids:
                continue

            try:
                scoped_detector = self._detector_for_scope(
                    detector, organization_id, project_id
                )
                windows = self._windows_for(scoped_detector.config, organization_id, project_id)
                observed_end = now
                observed_start = observed_end - windows.observation
                baseline_end = observed_start
                baseline_start = baseline_end - windows.baseline
                result = self._run_detector_for_agent(
                    scoped_detector, organization_id, project_id, agent_id,
                    baseline_start, baseline_end,
                    observed_start, observed_end,
                    windows=windows,
                )
                findings.extend(result)
            except Exception:  # noqa: BLE001, S110 - one detector cannot block the remaining set.
                pass

        return findings

    def reconcile_active_findings(
        self,
        organization_id: str,
        project_id: str | None = None,
    ) -> ReconciliationRunResult:
        """Check active findings for auto-resolution with sustained recovery.

        A finding is only resolved after ``consecutive_normal_windows``
        observation windows show normal metrics. This prevents oscillation:
        OPEN → RESOLVED → OPEN → RESOLVED rapid cycling.

        Returns the list of findings that were resolved during this cycle.
        """
        # Read the configured threshold (default 2).
        recovery_threshold = int(self._setting(
            "runtime_findings.auto_resolution.consecutive_normal_windows",
            2,
            organization_id,
            project_id,
        ))

        outcomes: list[ReconciliationFindingResult] = []
        cursor = None
        while True:
            page = self._finding_repo.page_by_status(
                FindingStatus.OPEN, organization_id, project_id, cursor=cursor, limit=100
            )
            for finding in page.items:
                # Case-review conclusions are historical: a future metrics
                # window cannot reconcile or invalidate them.
                if finding.lifecycle is FindingLifecycle.CASE_REVIEW:
                    continue
                outcomes.append(self._reconcile_finding(finding, recovery_threshold))
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
        return ReconciliationRunResult(tuple(outcomes))

    def review_case_finding(
        self,
        finding_id: str,
        action: FindingReviewAction,
        actor_id: str,
        *,
        organization_id: str,
        project_id: str | None = None,
        note: str | None = None,
    ) -> RuntimeFinding:
        """Record an explicit human review for a case-review finding."""
        finding = self._finding_repo.get(finding_id, organization_id, project_id)
        if finding is None:
            raise ValueError(f"Finding '{finding_id}' not found.")
        now = self._clock()
        if action is FindingReviewAction.ACKNOWLEDGE:
            reviewed = finding.acknowledge(actor_id, note, now=now)
        elif action is FindingReviewAction.CLOSE:
            reviewed = finding.close(actor_id, note, now=now)
        else:
            raise ValueError(f"Unsupported finding review action '{action}'.")
        return self._finding_repo.save(reviewed)

    def _reconcile_finding(
        self,
        finding: RuntimeFinding,
        recovery_threshold: int,
    ) -> ReconciliationFindingResult:
        registered_detector = next((item for item in self._detectors if item.detector_id == finding.detector_id), None)
        now = self._clock()
        if registered_detector is None:
            return self._record_non_evaluated_reconciliation(
                finding, now, recovery_threshold, ReconciliationOutcome.UNSUPPORTED,
                f"No reconciler is registered for detector '{finding.detector_id}'.",
            )

        detector = self._detector_for_scope(
            registered_detector, finding.organization_id, finding.project_id
        )
        finalization_policy = EvidenceWindowFinalizationPolicy(int(self._setting(
            "runtime_findings.reconciliation.allowed_lateness_hours",
            2,
            finding.organization_id,
            finding.project_id,
        )))
        windows = self._windows_for(detector.config, finding.organization_id, finding.project_id)
        window = _completed_reconciliation_window(now, windows, finalization_policy)
        if (
            finding.last_reconciliation is not None
            and finding.last_reconciliation.window.observed_end > window.observed_end
        ):
            # Increasing allowed lateness after a decision must not make a
            # previously-finalized window disappear and cause us to reconcile
            # an older, mutable one instead.  The durable contract remains
            # the latest decision until a genuinely newer window is eligible.
            window = finding.last_reconciliation.window
        if (
            finding.last_reconciliation is not None
            and finding.last_reconciliation.window.same_evidence_window(window)
        ):
            return ReconciliationFindingResult(
                finding.finding_id,
                ReconciliationOutcome.ALREADY_RECONCILED,
                finding.consecutive_normal_windows,
                recovery_threshold,
                window,
                "This completed observation window was already reconciled.",
            )

        try:
            result = self._run_detector_for_subject(
                detector,
                finding.organization_id,
                finding.project_id,
                finding.subject_type,
                finding.subject_id,
                window.baseline_start,
                window.baseline_end,
                window.observed_start,
                window.observed_end,
                finalization_policy.finalizes_at(window.observed_end),
            )
        except UnsupportedReconciliation as exc:
            return self._record_non_evaluated_reconciliation(
                finding, now, recovery_threshold, ReconciliationOutcome.UNSUPPORTED, str(exc), window
            )
        except Exception as exc:  # noqa: BLE001 - reconciliation records an explicit failed outcome.
            return self._record_non_evaluated_reconciliation(
                finding, now, recovery_threshold, ReconciliationOutcome.FAILED,
                f"Reconciliation evaluation failed: {exc.__class__.__name__}.", window
            )

        if result.insufficient_data:
            updated = finding.record_reconciliation_outcome(
                window, ReconciliationOutcome.INSUFFICIENT_DATA, now=now,
                detail="The completed observation window did not meet the detector minimum sample size.",
                reset_progress=True,
            )
            self._finding_repo.save(updated)
            return ReconciliationFindingResult(finding.finding_id, ReconciliationOutcome.INSUFFICIENT_DATA, 0, recovery_threshold, window)

        if result.finding is not None:
            outcome = ReconciliationOutcome.PROGRESS_RESET if finding.consecutive_normal_windows else ReconciliationOutcome.CONDITION_PRESENT
            updated = finding.record_reconciliation_outcome(
                window, outcome, now=now,
                detail="The detector condition remains present in this completed observation window.",
                reset_progress=True,
            )
            self._finding_repo.save(updated)
            return ReconciliationFindingResult(finding.finding_id, outcome, 0, recovery_threshold, window)

        updated = finding.record_healthy_window(window, now=now)
        if updated.consecutive_normal_windows >= recovery_threshold:
            updated = updated.mark_resolved(now)
            updated = replace(
                updated,
                last_reconciliation=ReconciliationRecord(
                    window=window, outcome=ReconciliationOutcome.RESOLVED, reconciled_at=now
                ),
            )
            self._finding_repo.save(updated)
            return ReconciliationFindingResult(finding.finding_id, ReconciliationOutcome.RESOLVED, updated.consecutive_normal_windows, recovery_threshold, window)
        self._finding_repo.save(updated)
        return ReconciliationFindingResult(finding.finding_id, ReconciliationOutcome.HEALTHY_AWAITING, updated.consecutive_normal_windows, recovery_threshold, window)

    def _record_non_evaluated_reconciliation(
        self,
        finding: RuntimeFinding,
        now: datetime,
        recovery_threshold: int,
        outcome: ReconciliationOutcome,
        detail: str,
        window: ReconciliationWindow | None = None,
    ) -> ReconciliationFindingResult:
        window = window or _fallback_reconciliation_window(now)
        if (
            finding.last_reconciliation is not None
            and finding.last_reconciliation.window.same_evidence_window(window)
        ):
            return ReconciliationFindingResult(finding.finding_id, ReconciliationOutcome.ALREADY_RECONCILED, finding.consecutive_normal_windows, recovery_threshold, window)
        updated = finding.record_reconciliation_outcome(
            window,
            outcome,
            now=now,
            detail=detail,
            # An unverified completed window cannot be part of a consecutive
            # healthy sequence; retaining prior progress could falsely resolve.
            reset_progress=True,
        )
        self._finding_repo.save(updated)
        return ReconciliationFindingResult(finding.finding_id, outcome, updated.consecutive_normal_windows, recovery_threshold, window, detail)

    # -- Internal -------------------------------------------------------------

    def _run_detector_for_subjects(
        self,
        detector: RuntimeDetector,
        organization_id: str,
        project_id: str | None,
        baseline_start: datetime,
        baseline_end: datetime,
        observed_start: datetime,
        observed_end: datetime,
        evidence_received_before: datetime | None = None,
        windows: RuntimeFindingWindows | None = None,
    ) -> list[RuntimeFinding]:
        """Run a detector across all subjects of its type."""
        findings: list[RuntimeFinding] = []

        # Run each detector's subject-specific logic.
        if detector.detector_id == "tool_failure_rate":
            findings.extend(self._run_tool_failure_detector(
                detector, organization_id, project_id,
                baseline_start, baseline_end, observed_start, observed_end,
                windows=windows,
            ))
        elif detector.detector_id == "agent_execution_failure_rate":
            findings.extend(self._run_agent_failure_detector(
                detector, organization_id, project_id,
                baseline_start, baseline_end, observed_start, observed_end,
                windows=windows,
            ))
        elif detector.detector_id == "execution_latency_regression":
            findings.extend(self._run_latency_detector(
                detector, organization_id, project_id,
                baseline_start, baseline_end, observed_start, observed_end,
                windows=windows,
            ))
        elif detector.detector_id == "evaluation_failure_rate":
            findings.extend(self._run_evaluation_detector(
                detector, organization_id, project_id,
                baseline_start, baseline_end, observed_start, observed_end,
                windows=windows,
            ))
        elif detector.detector_id == "policy_denial_rate":
            findings.extend(self._run_policy_detector(
                detector, organization_id, project_id,
                baseline_start, baseline_end, observed_start, observed_end,
                windows=windows,
            ))
        elif detector.detector_id == "repeated_runtime_error":
            findings.extend(self._run_error_detector(
                detector, organization_id, project_id,
                baseline_start, baseline_end, observed_start, observed_end,
                windows=windows,
            ))

        return findings

    def _run_tool_failure_detector(
        self,
        detector: RuntimeDetector,
        organization_id: str,
        project_id: str | None,
        baseline_start: datetime,
        baseline_end: datetime,
        observed_start: datetime,
        observed_end: datetime,
        windows: RuntimeFindingWindows | None = None,
    ) -> list[RuntimeFinding]:
        findings: list[RuntimeFinding] = []

        # Get unique tool IDs from events.
        tool_ids = self._get_unique_tool_ids(organization_id, project_id)

        for tool_id in tool_ids:
            baseline, observed = self._aggregation.get_tool_metrics(
                organization_id, project_id, tool_id,
                baseline_start, baseline_end, observed_start, observed_end,
            )
            result = detector.detect(
                organization_id, project_id, "tool", tool_id,
                baseline, observed,
                int(observed.get("total_calls", 0)),
            )
            if result.finding is not None:
                findings.append(self._persist_or_update_finding(result.finding, windows))

        return findings

    def _run_agent_failure_detector(
        self,
        detector: RuntimeDetector,
        organization_id: str,
        project_id: str | None,
        baseline_start: datetime,
        baseline_end: datetime,
        observed_start: datetime,
        observed_end: datetime,
        windows: RuntimeFindingWindows | None = None,
    ) -> list[RuntimeFinding]:
        findings: list[RuntimeFinding] = []

        # Get unique agent IDs from executions.
        agent_ids = self._get_unique_agent_ids(organization_id, project_id)

        for agent_id in agent_ids:
            baseline, observed = self._aggregation.get_agent_execution_metrics(
                organization_id, project_id, agent_id,
                baseline_start, baseline_end, observed_start, observed_end,
            )
            result = detector.detect(
                organization_id, project_id, "agent", agent_id,
                baseline, observed,
                int(observed.get("total_executions", 0)),
            )
            if result.finding is not None:
                findings.append(self._persist_or_update_finding(result.finding, windows))

        return findings

    def _run_latency_detector(
        self,
        detector: RuntimeDetector,
        organization_id: str,
        project_id: str | None,
        baseline_start: datetime,
        baseline_end: datetime,
        observed_start: datetime,
        observed_end: datetime,
        windows: RuntimeFindingWindows | None = None,
    ) -> list[RuntimeFinding]:
        findings: list[RuntimeFinding] = []

        # Run latency detection per agent.
        agent_ids = self._get_unique_agent_ids(organization_id, project_id)

        for agent_id in agent_ids:
            baseline, observed = self._aggregation.get_latency_metrics(
                organization_id, project_id,
                baseline_start, baseline_end, observed_start, observed_end, agent_id,
            )
            result = detector.detect(
                organization_id, project_id, "agent", agent_id,
                baseline, observed,
                int(observed.get("total_executions", 0)),
            )
            if result.finding is not None:
                findings.append(self._persist_or_update_finding(result.finding, windows))

        return findings

    def _run_evaluation_detector(
        self,
        detector: RuntimeDetector,
        organization_id: str,
        project_id: str | None,
        baseline_start: datetime,
        baseline_end: datetime,
        observed_start: datetime,
        observed_end: datetime,
        windows: RuntimeFindingWindows | None = None,
    ) -> list[RuntimeFinding]:
        findings: list[RuntimeFinding] = []

        baseline, observed = self._aggregation.get_evaluation_metrics(
            organization_id, project_id,
            baseline_start, baseline_end, observed_start, observed_end,
        )
        result = detector.detect(
            organization_id, project_id, "evaluation", "all",
            baseline, observed,
            int(observed.get("total_evaluations", 0)),
        )
        if result.finding is not None:
            findings.append(self._persist_or_update_finding(result.finding, windows))

        return findings

    def _run_policy_detector(
        self,
        detector: RuntimeDetector,
        organization_id: str,
        project_id: str | None,
        baseline_start: datetime,
        baseline_end: datetime,
        observed_start: datetime,
        observed_end: datetime,
        windows: RuntimeFindingWindows | None = None,
    ) -> list[RuntimeFinding]:
        findings: list[RuntimeFinding] = []

        baseline, observed = self._aggregation.get_policy_denial_metrics(
            organization_id, project_id,
            baseline_start, baseline_end, observed_start, observed_end,
        )
        result = detector.detect(
            organization_id, project_id, "policy", "all",
            baseline, observed,
            int(observed.get("total_decisions", 0)),
        )
        if result.finding is not None:
            findings.append(self._persist_or_update_finding(result.finding, windows))

        return findings

    def _run_error_detector(
        self,
        detector: RuntimeDetector,
        organization_id: str,
        project_id: str | None,
        baseline_start: datetime,
        baseline_end: datetime,
        observed_start: datetime,
        observed_end: datetime,
        windows: RuntimeFindingWindows | None = None,
    ) -> list[RuntimeFinding]:
        findings: list[RuntimeFinding] = []

        baseline, observed = self._aggregation.get_error_metrics(
            organization_id, project_id,
            baseline_start, baseline_end, observed_start, observed_end,
        )
        result = detector.detect(
            organization_id, project_id, "error", "all",
            baseline, observed,
            int(observed.get("total_executions", 0)),
        )
        if result.finding is not None:
            findings.append(self._persist_or_update_finding(result.finding, windows))

        return findings

    def _run_detector_for_agent(
        self,
        detector: RuntimeDetector,
        organization_id: str,
        project_id: str | None,
        agent_id: str,
        baseline_start: datetime,
        baseline_end: datetime,
        observed_start: datetime,
        observed_end: datetime,
        windows: RuntimeFindingWindows | None = None,
    ) -> list[RuntimeFinding]:
        findings: list[RuntimeFinding] = []

        if detector.detector_id == "agent_execution_failure_rate":
            baseline, observed = self._aggregation.get_agent_execution_metrics(
                organization_id, project_id, agent_id,
                baseline_start, baseline_end, observed_start, observed_end,
            )
            result = detector.detect(
                organization_id, project_id, "agent", agent_id,
                baseline, observed,
                int(observed.get("total_executions", 0)),
            )
            if result.finding is not None:
                findings.append(self._persist_or_update_finding(result.finding, windows))

        return findings

    def _run_detector_for_subject(
        self,
        detector: RuntimeDetector,
        organization_id: str,
        project_id: str | None,
        subject_type: str,
        subject_id: str,
        baseline_start: datetime,
        baseline_end: datetime,
        observed_start: datetime,
        observed_end: datetime,
        evidence_received_before: datetime | None = None,
    ) -> DetectorResult:
        """Run a detector for a specific subject and return the result."""
        if detector.detector_id == "tool_failure_rate":
            baseline, observed = self._aggregation.get_tool_metrics(
                organization_id, project_id, subject_id,
                baseline_start, baseline_end, observed_start, observed_end,
                evidence_received_before,
            )
            return detector.detect(
                organization_id, project_id, "tool", subject_id,
                baseline, observed,
                int(observed.get("total_calls", 0)),
            )
        elif detector.detector_id == "agent_execution_failure_rate":
            baseline, observed = self._aggregation.get_agent_execution_metrics(
                organization_id, project_id, subject_id,
                baseline_start, baseline_end, observed_start, observed_end,
            )
            return detector.detect(
                organization_id, project_id, "agent", subject_id,
                baseline, observed,
                int(observed.get("total_executions", 0)),
            )
        elif detector.detector_id == "execution_latency_regression":
            baseline, observed = self._aggregation.get_latency_metrics(
                organization_id, project_id,
                baseline_start, baseline_end, observed_start, observed_end, subject_id,
            )
            return detector.detect(
                organization_id, project_id, subject_type, subject_id,
                baseline, observed,
                int(observed.get("total_executions", observed.get("sample_size", 0))),
            )
        elif detector.detector_id == "evaluation_failure_rate":
            baseline, observed = self._aggregation.get_evaluation_metrics(
                organization_id, project_id,
                baseline_start, baseline_end, observed_start, observed_end,
                evidence_received_before,
            )
            return detector.detect(
                organization_id, project_id, subject_type, subject_id,
                baseline, observed, int(observed.get("total_evaluations", 0)),
            )
        elif detector.detector_id == "policy_denial_rate":
            baseline, observed = self._aggregation.get_policy_denial_metrics(
                organization_id, project_id,
                baseline_start, baseline_end, observed_start, observed_end,
                evidence_received_before,
            )
            return detector.detect(
                organization_id, project_id, subject_type, subject_id,
                baseline, observed, int(observed.get("total_decisions", 0)),
            )
        elif detector.detector_id == "repeated_runtime_error":
            baseline, observed = self._aggregation.get_error_metrics(
                organization_id, project_id,
                baseline_start, baseline_end, observed_start, observed_end,
                evidence_received_before,
            )
            return detector.detect(
                organization_id, project_id, subject_type, subject_id,
                baseline, observed, int(observed.get("total_executions", 0)),
            )
        raise UnsupportedReconciliation(
            f"Detector '{detector.detector_id}' has no safe reconciliation implementation."
        )

    def _persist_or_update_finding(
        self,
        finding: RuntimeFinding,
        windows: RuntimeFindingWindows | None = None,
    ) -> RuntimeFinding:
        """Save a new finding or update an existing one (idempotent)."""
        if windows is not None:
            finding = replace(
                finding,
                baseline_window=windows.baseline_label,
                observation_window=windows.observation_label,
            )
        existing = self._finding_repo.find_by_dedup_key(
            finding.deduplication_key(),
            finding.organization_id,
            finding.project_id,
        )

        if existing is not None and existing.is_active:
            # Update existing active finding.
            updated = existing.update_observation()
            return self._finding_repo.save(updated)

        # Save new finding.
        return self._finding_repo.save(finding)

    def _detector_for_scope(
        self,
        detector: RuntimeDetector,
        organization_id: str,
        project_id: str | None,
    ) -> RuntimeDetector:
        """Construct one detector from the real, tenant-scoped settings view."""
        if self._config_service is None:
            return detector
        try:
            return type(detector)(
                _ScopedConfiguration(
                    self._config_service, SettingContext(organization_id, project_id)
                )
            )
        except (TypeError, ValueError):
            # Extensions may own a different construction contract.  Their
            # existing instance remains safe; built-in detectors are scoped.
            return detector

    def _setting(
        self,
        key: str,
        default: Any,
        organization_id: str,
        project_id: str | None,
    ) -> Any:
        if self._config_service is None:
            return default
        try:
            return self._config_service.get(key, SettingContext(organization_id, project_id))
        except TypeError:
            return _resolve_setting(self._config_service, key, default)
        except Exception:  # noqa: BLE001 - unavailable scoped settings use the default.
            return default

    def _windows_for(
        self,
        config: DetectorConfig,
        organization_id: str,
        project_id: str | None,
    ) -> RuntimeFindingWindows:
        """Use the guarded local profile or retain the detector production spans."""
        if self._validation_profile_enabled(organization_id, project_id):
            baseline_minutes = int(self._setting(
                "runtime_findings.validation_profile.baseline_minutes", 10,
                organization_id, project_id,
            ))
            observation_minutes = int(self._setting(
                "runtime_findings.validation_profile.observation_minutes", 2,
                organization_id, project_id,
            ))
            resolution_minutes = int(self._setting(
                "runtime_findings.validation_profile.resolution_minutes", 2,
                organization_id, project_id,
            ))
            return RuntimeFindingWindows(
                timedelta(minutes=baseline_minutes),
                timedelta(minutes=observation_minutes),
                timedelta(minutes=resolution_minutes),
                f"{baseline_minutes}m",
                f"{observation_minutes}m",
            )
        return RuntimeFindingWindows(
            timedelta(days=config.baseline_window_days),
            timedelta(hours=config.observation_window_hours),
            timedelta(hours=config.resolution_window_hours),
            f"{config.baseline_window_days}d",
            f"{config.observation_window_hours}h",
        )

    def _validation_profile_enabled(
        self, organization_id: str, project_id: str | None
    ) -> bool:
        allowed_project = str(
            self._environment.get(
                "AI_GOVERNANCE_RUNTIME_FINDINGS_TEST_WINDOW_PROJECT_ID", ""
            )
        ).strip()
        enabled = str(
            self._environment.get(
                "AI_GOVERNANCE_RUNTIME_FINDINGS_TEST_WINDOWS_ENABLED", "false"
            )
        ).strip().lower() == "true"
        return bool(
            enabled
            and project_id
            and project_id == allowed_project
            and self._setting(
                "runtime_findings.validation_profile.enabled",
                False,
                organization_id,
                project_id,
            )
        )

    def _get_unique_tool_ids(
        self, organization_id: str, project_id: str | None
    ) -> list[str]:
        """Get stable tool IDs from authoritative, tenant-scoped event evidence."""
        return list(self._aggregation.get_observed_tool_ids(organization_id, project_id))

    def _get_unique_agent_ids(
        self, organization_id: str, project_id: str | None
    ) -> list[str]:
        """Get unique agent IDs from executions."""
        agent_ids: set[str] = set()

        from ai_governance.repositories.agent_execution_repository import (
            AgentExecutionListFilters,
        )

        executions = self._aggregation._execution_repo.list(
            AgentExecutionListFilters(limit=10000),
            organization_id,
            project_id,
        )
        for execution in executions:
            agent_ids.add(execution.agent_id)

        return list(agent_ids)


def _completed_reconciliation_window(
    now: datetime,
    windows: RuntimeFindingWindows,
    finalization_policy: EvidenceWindowFinalizationPolicy,
) -> ReconciliationWindow:
    """Build a closed window using the detector's configured cadence and spans.

    The resolution interval provides the cadence; the configured current
    observation span remains the actual evidence fed into the detector.
    Flooring the end boundary makes retries in the same interval identical.
    """
    now = now.astimezone(UTC)
    cadence_seconds = int(windows.resolution.total_seconds())
    epoch_seconds = int(now.timestamp())
    end = datetime.fromtimestamp((epoch_seconds // cadence_seconds) * cadence_seconds, UTC)
    # A boundary is not evidence-final until its allowed lateness has elapsed.
    # Move to an earlier cadence window rather than reading mutable evidence.
    while not finalization_policy.is_finalized(end, now):
        end -= timedelta(seconds=cadence_seconds)
    observed_start = end - windows.observation
    cutoff = finalization_policy.finalizes_at(end)
    return ReconciliationWindow(
        observed_start=observed_start,
        observed_end=end,
        baseline_start=observed_start - windows.baseline,
        baseline_end=observed_start,
        finalization_cutoff_at=cutoff,
        lateness_policy_hours=finalization_policy.allowed_lateness_hours,
    )


def _fallback_reconciliation_window(now: datetime) -> ReconciliationWindow:
    """A non-contributing record window for explicitly unsupported detectors."""
    end = now.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(hours=1)
    return ReconciliationWindow(start, end, start - timedelta(days=1), start)
