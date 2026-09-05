"""Six initial deterministic runtime detectors.

Each detector reads its configuration from the settings control plane
at construction time. Thresholds, sample sizes, and time windows are
fully externalized — no code changes required to tune detection.

Detectors:
1. ToolFailureRateDetector — tool call failure rate increase
2. AgentExecutionFailureRateDetector — agent execution failure rate increase
3. ExecutionLatencyRegressionDetector — execution latency regression
4. EvaluationFailureRateDetector — evaluation failure rate increase
5. PolicyDenialRateDetector — governance/policy denial rate increase
6. RepeatedRuntimeErrorDetector — repeated runtime error pattern
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ai_governance.domain.runtime_findings.detector import (
    DetectorConfig,
    DetectorResult,
    RuntimeDetector,
    _build_evidence_references,
    _calculate_severity,
)
from ai_governance.domain.runtime_findings.finding import (
    MetricSnapshot,
    RuntimeFinding,
)

# ---------------------------------------------------------------------------
# Configuration helpers — read from settings control plane
# ---------------------------------------------------------------------------

def _resolve_setting(
    configuration_service: Any | None,
    key: str,
    default: Any,
) -> Any:
    """Resolve a detector setting from the configuration service or return default."""
    if configuration_service is not None:
        try:
            return configuration_service.get(key)
        except Exception:  # noqa: BLE001, S110 - settings remain optional.
            pass
    return default


# ---------------------------------------------------------------------------
# 1. Tool Failure Rate Increase Detector
# ---------------------------------------------------------------------------

class ToolFailureRateDetector(RuntimeDetector):
    """Detect meaningful increases in a tool's call failure rate.

    All configuration is read from the settings control plane at
    construction time. Defaults are conservative to avoid noise.
    """

    def __init__(
        self,
        configuration_service: Any | None = None,
    ) -> None:
        self._config = DetectorConfig(
            detector_id="tool_failure_rate",
            min_observation_count=int(_resolve_setting(
                configuration_service,
                "runtime_findings.tool_failure_rate.min_observation_count",
                30,
            )),
            baseline_window_days=int(_resolve_setting(
                configuration_service,
                "runtime_findings.tool_failure_rate.baseline_window_days",
                7,
            )),
            observation_window_hours=int(_resolve_setting(
                configuration_service,
                "runtime_findings.tool_failure_rate.observation_window_hours",
                24,
            )),
            absolute_threshold=float(_resolve_setting(
                configuration_service,
                "runtime_findings.tool_failure_rate.absolute_threshold",
                0.05,
            )),
            relative_threshold=float(_resolve_setting(
                configuration_service,
                "runtime_findings.tool_failure_rate.relative_threshold",
                2.0,
            )),
            severity_levels={
                "failure_rate_critical_threshold": float(_resolve_setting(
                    configuration_service,
                    "runtime_findings.tool_failure_rate.severity_critical_threshold",
                    0.25,
                )),
                "failure_rate_high_threshold": float(_resolve_setting(
                    configuration_service,
                    "runtime_findings.tool_failure_rate.severity_high_threshold",
                    0.15,
                )),
                "failure_rate_medium_threshold": float(_resolve_setting(
                    configuration_service,
                    "runtime_findings.tool_failure_rate.severity_medium_threshold",
                    0.10,
                )),
                "failure_rate_low_threshold": float(_resolve_setting(
                    configuration_service,
                    "runtime_findings.tool_failure_rate.severity_low_threshold",
                    0.05,
                )),
            },
            resolution_window_hours=int(_resolve_setting(
                configuration_service,
                "runtime_findings.tool_failure_rate.resolution_window_hours",
                48,
            )),
        )

    @property
    def detector_id(self) -> str:
        return self._config.detector_id

    @property
    def detector_version(self) -> str:
        return self._config.detector_version

    @property
    def config(self) -> DetectorConfig:
        return self._config

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
        baseline_calls = float(baseline_metrics.get("total_calls", 0))
        baseline_failures = float(baseline_metrics.get("failures", 0))
        observed_calls = float(observed_metrics.get("total_calls", 0))
        observed_failures = float(observed_metrics.get("failures", 0))

        if observed_calls < self._config.min_observation_count:
            return DetectorResult(insufficient_data=True)

        baseline_rate = baseline_failures / baseline_calls if baseline_calls > 0 else 0.0
        observed_rate = observed_failures / observed_calls if observed_calls > 0 else 0.0

        if observed_rate <= baseline_rate:
            return DetectorResult()
        if baseline_rate > 0 and observed_rate / baseline_rate < self._config.relative_threshold:
            return DetectorResult()
        if observed_rate < self._config.absolute_threshold:
            return DetectorResult()

        severity = _calculate_severity(self._config.severity_levels, "failure_rate", observed_rate)

        now = datetime.now(UTC)
        finding = RuntimeFinding(
            finding_id=f"finding:tool_failure_rate:{subject_id}:{now.isoformat()}",
            organization_id=organization_id,
            project_id=project_id,
            finding_type="TOOL_FAILURE_RATE_INCREASE",
            subject_type="tool",
            subject_id=subject_id,
            severity=severity,
            baseline_window=f"{self._config.baseline_window_days}d",
            observation_window=f"{self._config.observation_window_hours}h",
            baseline_metrics=(
                MetricSnapshot(name="failure_rate", value=baseline_rate, sample_size=int(baseline_calls)),
                MetricSnapshot(name="total_calls", value=baseline_calls, sample_size=int(baseline_calls)),
                MetricSnapshot(name="failures", value=baseline_failures, sample_size=int(baseline_calls)),
            ),
            observed_metrics=(
                MetricSnapshot(name="failure_rate", value=observed_rate, sample_size=int(observed_calls)),
                MetricSnapshot(name="total_calls", value=observed_calls, sample_size=int(observed_calls)),
                MetricSnapshot(name="failures", value=observed_failures, sample_size=int(observed_calls)),
            ),
            observation_count=int(observed_calls),
            evidence_references=_build_evidence_references(
                self.detector_id, self.detector_version,
                {"baseline_failure_rate": baseline_rate, "observed_failure_rate": observed_rate},
                {"observed_failure_rate": observed_rate},
                self._config.absolute_threshold,
            ),
            related_execution_ids=related_execution_ids[:20],
            detector_id=self.detector_id,
            detector_version=self.detector_version,
            first_detected_at=now,
            last_detected_at=now,
        )
        return DetectorResult(finding=finding)


# ---------------------------------------------------------------------------
# 2. Agent Execution Failure Rate Detector
# ---------------------------------------------------------------------------

class AgentExecutionFailureRateDetector(RuntimeDetector):
    """Detect meaningful deterioration in an agent's execution success/failure ratio."""

    def __init__(
        self,
        configuration_service: Any | None = None,
    ) -> None:
        self._config = DetectorConfig(
            detector_id="agent_execution_failure_rate",
            min_observation_count=int(_resolve_setting(
                configuration_service,
                "runtime_findings.agent_execution_failure_rate.min_observation_count",
                20,
            )),
            baseline_window_days=int(_resolve_setting(
                configuration_service,
                "runtime_findings.agent_execution_failure_rate.baseline_window_days",
                7,
            )),
            observation_window_hours=int(_resolve_setting(
                configuration_service,
                "runtime_findings.agent_execution_failure_rate.observation_window_hours",
                24,
            )),
            absolute_threshold=float(_resolve_setting(
                configuration_service,
                "runtime_findings.agent_execution_failure_rate.absolute_threshold",
                0.10,
            )),
            relative_threshold=float(_resolve_setting(
                configuration_service,
                "runtime_findings.agent_execution_failure_rate.relative_threshold",
                2.0,
            )),
            severity_levels={
                "failure_rate_critical_threshold": float(_resolve_setting(
                    configuration_service,
                    "runtime_findings.agent_execution_failure_rate.severity_critical_threshold",
                    0.50,
                )),
                "failure_rate_high_threshold": float(_resolve_setting(
                    configuration_service,
                    "runtime_findings.agent_execution_failure_rate.severity_high_threshold",
                    0.30,
                )),
                "failure_rate_medium_threshold": float(_resolve_setting(
                    configuration_service,
                    "runtime_findings.agent_execution_failure_rate.severity_medium_threshold",
                    0.20,
                )),
                "failure_rate_low_threshold": float(_resolve_setting(
                    configuration_service,
                    "runtime_findings.agent_execution_failure_rate.severity_low_threshold",
                    0.10,
                )),
            },
            resolution_window_hours=int(_resolve_setting(
                configuration_service,
                "runtime_findings.agent_execution_failure_rate.resolution_window_hours",
                48,
            )),
        )

    @property
    def detector_id(self) -> str:
        return self._config.detector_id

    @property
    def detector_version(self) -> str:
        return self._config.detector_version

    @property
    def config(self) -> DetectorConfig:
        return self._config

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
        baseline_total = float(baseline_metrics.get("total_executions", 0))
        baseline_failures = float(baseline_metrics.get("failures", 0))
        observed_total = float(observed_metrics.get("total_executions", 0))
        observed_failures = float(observed_metrics.get("failures", 0))

        if observed_total < self._config.min_observation_count:
            return DetectorResult(insufficient_data=True)

        baseline_rate = baseline_failures / baseline_total if baseline_total > 0 else 0.0
        observed_rate = observed_failures / observed_total if observed_total > 0 else 0.0

        if observed_rate <= baseline_rate:
            return DetectorResult()
        if baseline_rate > 0 and observed_rate / baseline_rate < self._config.relative_threshold:
            return DetectorResult()
        if observed_rate < self._config.absolute_threshold:
            return DetectorResult()

        severity = _calculate_severity(self._config.severity_levels, "failure_rate", observed_rate)

        now = datetime.now(UTC)
        finding = RuntimeFinding(
            finding_id=f"finding:agent_failure_rate:{subject_id}:{now.isoformat()}",
            organization_id=organization_id,
            project_id=project_id,
            finding_type="AGENT_EXECUTION_FAILURE_RATE_INCREASE",
            subject_type="agent",
            subject_id=subject_id,
            severity=severity,
            baseline_window=f"{self._config.baseline_window_days}d",
            observation_window=f"{self._config.observation_window_hours}h",
            baseline_metrics=(
                MetricSnapshot(name="failure_rate", value=baseline_rate, sample_size=int(baseline_total)),
                MetricSnapshot(name="total_executions", value=baseline_total, sample_size=int(baseline_total)),
            ),
            observed_metrics=(
                MetricSnapshot(name="failure_rate", value=observed_rate, sample_size=int(observed_total)),
                MetricSnapshot(name="total_executions", value=observed_total, sample_size=int(observed_total)),
            ),
            observation_count=int(observed_total),
            evidence_references=_build_evidence_references(
                self.detector_id, self.detector_version,
                {"baseline_failure_rate": baseline_rate},
                {"observed_failure_rate": observed_rate},
                self._config.absolute_threshold,
            ),
            related_execution_ids=related_execution_ids[:20],
            detector_id=self.detector_id,
            detector_version=self.detector_version,
            first_detected_at=now,
            last_detected_at=now,
        )
        return DetectorResult(finding=finding)


# ---------------------------------------------------------------------------
# 3. Execution Latency Regression Detector
# ---------------------------------------------------------------------------

class ExecutionLatencyRegressionDetector(RuntimeDetector):
    """Detect meaningful increases in execution duration distribution.

    Uses median and P95 rather than averages for robustness.
    """

    def __init__(
        self,
        configuration_service: Any | None = None,
    ) -> None:
        self._config = DetectorConfig(
            detector_id="execution_latency_regression",
            min_observation_count=int(_resolve_setting(
                configuration_service,
                "runtime_findings.execution_latency_regression.min_observation_count",
                20,
            )),
            baseline_window_days=int(_resolve_setting(
                configuration_service,
                "runtime_findings.execution_latency_regression.baseline_window_days",
                7,
            )),
            observation_window_hours=int(_resolve_setting(
                configuration_service,
                "runtime_findings.execution_latency_regression.observation_window_hours",
                24,
            )),
            absolute_threshold=0.0,
            relative_threshold=float(_resolve_setting(
                configuration_service,
                "runtime_findings.execution_latency_regression.relative_threshold",
                1.5,
            )),
            severity_levels={
                "latency_critical_threshold": float(_resolve_setting(
                    configuration_service,
                    "runtime_findings.execution_latency_regression.severity_critical_threshold",
                    3.0,
                )),
                "latency_high_threshold": float(_resolve_setting(
                    configuration_service,
                    "runtime_findings.execution_latency_regression.severity_high_threshold",
                    2.0,
                )),
                "latency_medium_threshold": float(_resolve_setting(
                    configuration_service,
                    "runtime_findings.execution_latency_regression.severity_medium_threshold",
                    1.5,
                )),
                "latency_low_threshold": float(_resolve_setting(
                    configuration_service,
                    "runtime_findings.execution_latency_regression.severity_low_threshold",
                    1.2,
                )),
            },
            resolution_window_hours=int(_resolve_setting(
                configuration_service,
                "runtime_findings.execution_latency_regression.resolution_window_hours",
                48,
            )),
        )

    @property
    def detector_id(self) -> str:
        return self._config.detector_id

    @property
    def detector_version(self) -> str:
        return self._config.detector_version

    @property
    def config(self) -> DetectorConfig:
        return self._config

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
        baseline_median = float(baseline_metrics.get("median_duration_seconds", 0))
        observed_median = float(observed_metrics.get("median_duration_seconds", 0))
        baseline_p95 = float(baseline_metrics.get("p95_duration_seconds", 0))
        observed_p95 = float(observed_metrics.get("p95_duration_seconds", 0))
        baseline_count = int(baseline_metrics.get("total_executions", observation_count))
        observed_count = int(observed_metrics.get("total_executions", observation_count))

        if observation_count < self._config.min_observation_count:
            return DetectorResult(insufficient_data=True)

        if baseline_median <= 0 or observed_median <= 0:
            return DetectorResult()

        regression_ratio = observed_median / baseline_median
        if regression_ratio < self._config.relative_threshold:
            return DetectorResult()

        severity = _calculate_severity(self._config.severity_levels, "latency", regression_ratio)

        now = datetime.now(UTC)
        finding = RuntimeFinding(
            finding_id=f"finding:latency_regression:{subject_id}:{now.isoformat()}",
            organization_id=organization_id,
            project_id=project_id,
            finding_type="EXECUTION_LATENCY_REGRESSION",
            subject_type=subject_type,
            subject_id=subject_id,
            severity=severity,
            baseline_window=f"{self._config.baseline_window_days}d",
            observation_window=f"{self._config.observation_window_hours}h",
            baseline_metrics=(
                MetricSnapshot(name="median_duration_seconds", value=baseline_median, sample_size=baseline_count),
                MetricSnapshot(name="p95_duration_seconds", value=baseline_p95, sample_size=baseline_count),
            ),
            observed_metrics=(
                MetricSnapshot(name="median_duration_seconds", value=observed_median, sample_size=observed_count),
                MetricSnapshot(name="p95_duration_seconds", value=observed_p95, sample_size=observed_count),
            ),
            observation_count=int(observation_count),
            evidence_references=_build_evidence_references(
                self.detector_id, self.detector_version,
                {"baseline_median": baseline_median},
                {"observed_median": observed_median},
                self._config.relative_threshold,
            ),
            related_execution_ids=related_execution_ids[:20],
            detector_id=self.detector_id,
            detector_version=self.detector_version,
            first_detected_at=now,
            last_detected_at=now,
        )
        return DetectorResult(finding=finding)


# ---------------------------------------------------------------------------
# 4. Evaluation Failure Rate Detector
# ---------------------------------------------------------------------------

class EvaluationFailureRateDetector(RuntimeDetector):
    """Detect material increases in failed runtime-linked evaluations."""

    def __init__(
        self,
        configuration_service: Any | None = None,
    ) -> None:
        self._config = DetectorConfig(
            detector_id="evaluation_failure_rate",
            min_observation_count=int(_resolve_setting(
                configuration_service,
                "runtime_findings.evaluation_failure_rate.min_observation_count",
                10,
            )),
            baseline_window_days=int(_resolve_setting(
                configuration_service,
                "runtime_findings.evaluation_failure_rate.baseline_window_days",
                7,
            )),
            observation_window_hours=int(_resolve_setting(
                configuration_service,
                "runtime_findings.evaluation_failure_rate.observation_window_hours",
                24,
            )),
            absolute_threshold=float(_resolve_setting(
                configuration_service,
                "runtime_findings.evaluation_failure_rate.absolute_threshold",
                0.15,
            )),
            relative_threshold=float(_resolve_setting(
                configuration_service,
                "runtime_findings.evaluation_failure_rate.relative_threshold",
                2.0,
            )),
            severity_levels={
                "failure_rate_critical_threshold": float(_resolve_setting(
                    configuration_service,
                    "runtime_findings.evaluation_failure_rate.severity_critical_threshold",
                    0.50,
                )),
                "failure_rate_high_threshold": float(_resolve_setting(
                    configuration_service,
                    "runtime_findings.evaluation_failure_rate.severity_high_threshold",
                    0.30,
                )),
                "failure_rate_medium_threshold": float(_resolve_setting(
                    configuration_service,
                    "runtime_findings.evaluation_failure_rate.severity_medium_threshold",
                    0.20,
                )),
                "failure_rate_low_threshold": float(_resolve_setting(
                    configuration_service,
                    "runtime_findings.evaluation_failure_rate.severity_low_threshold",
                    0.15,
                )),
            },
            resolution_window_hours=int(_resolve_setting(
                configuration_service,
                "runtime_findings.evaluation_failure_rate.resolution_window_hours",
                48,
            )),
        )

    @property
    def detector_id(self) -> str:
        return self._config.detector_id

    @property
    def detector_version(self) -> str:
        return self._config.detector_version

    @property
    def config(self) -> DetectorConfig:
        return self._config

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
        baseline_total = float(baseline_metrics.get("total_evaluations", 0))
        baseline_failures = float(baseline_metrics.get("failures", 0))
        observed_total = float(observed_metrics.get("total_evaluations", 0))
        observed_failures = float(observed_metrics.get("failures", 0))

        if observed_total < self._config.min_observation_count:
            return DetectorResult(insufficient_data=True)

        baseline_rate = baseline_failures / baseline_total if baseline_total > 0 else 0.0
        observed_rate = observed_failures / observed_total if observed_total > 0 else 0.0

        if observed_rate <= baseline_rate:
            return DetectorResult()
        if baseline_rate > 0 and observed_rate / baseline_rate < self._config.relative_threshold:
            return DetectorResult()
        if observed_rate < self._config.absolute_threshold:
            return DetectorResult()

        severity = _calculate_severity(self._config.severity_levels, "failure_rate", observed_rate)

        now = datetime.now(UTC)
        finding = RuntimeFinding(
            finding_id=f"finding:eval_failure_rate:{subject_id}:{now.isoformat()}",
            organization_id=organization_id,
            project_id=project_id,
            finding_type="EVALUATION_FAILURE_RATE_INCREASE",
            subject_type=subject_type,
            subject_id=subject_id,
            severity=severity,
            baseline_window=f"{self._config.baseline_window_days}d",
            observation_window=f"{self._config.observation_window_hours}h",
            baseline_metrics=(
                MetricSnapshot(name="failure_rate", value=baseline_rate, sample_size=int(baseline_total)),
            ),
            observed_metrics=(
                MetricSnapshot(name="failure_rate", value=observed_rate, sample_size=int(observed_total)),
            ),
            observation_count=int(observed_total),
            evidence_references=_build_evidence_references(
                self.detector_id, self.detector_version,
                {"baseline_failure_rate": baseline_rate},
                {"observed_failure_rate": observed_rate},
                self._config.absolute_threshold,
            ),
            related_execution_ids=related_execution_ids[:20],
            detector_id=self.detector_id,
            detector_version=self.detector_version,
            first_detected_at=now,
            last_detected_at=now,
        )
        return DetectorResult(finding=finding)


# ---------------------------------------------------------------------------
# 5. Policy Denial Rate Detector
# ---------------------------------------------------------------------------

class PolicyDenialRateDetector(RuntimeDetector):
    """Detect significant increases in runtime governance denials."""

    def __init__(
        self,
        configuration_service: Any | None = None,
    ) -> None:
        self._config = DetectorConfig(
            detector_id="policy_denial_rate",
            min_observation_count=int(_resolve_setting(
                configuration_service,
                "runtime_findings.policy_denial_rate.min_observation_count",
                10,
            )),
            baseline_window_days=int(_resolve_setting(
                configuration_service,
                "runtime_findings.policy_denial_rate.baseline_window_days",
                7,
            )),
            observation_window_hours=int(_resolve_setting(
                configuration_service,
                "runtime_findings.policy_denial_rate.observation_window_hours",
                24,
            )),
            absolute_threshold=float(_resolve_setting(
                configuration_service,
                "runtime_findings.policy_denial_rate.absolute_threshold",
                0.10,
            )),
            relative_threshold=float(_resolve_setting(
                configuration_service,
                "runtime_findings.policy_denial_rate.relative_threshold",
                2.0,
            )),
            severity_levels={
                "denial_rate_critical_threshold": float(_resolve_setting(
                    configuration_service,
                    "runtime_findings.policy_denial_rate.severity_critical_threshold",
                    0.50,
                )),
                "denial_rate_high_threshold": float(_resolve_setting(
                    configuration_service,
                    "runtime_findings.policy_denial_rate.severity_high_threshold",
                    0.30,
                )),
                "denial_rate_medium_threshold": float(_resolve_setting(
                    configuration_service,
                    "runtime_findings.policy_denial_rate.severity_medium_threshold",
                    0.20,
                )),
                "denial_rate_low_threshold": float(_resolve_setting(
                    configuration_service,
                    "runtime_findings.policy_denial_rate.severity_low_threshold",
                    0.10,
                )),
            },
            resolution_window_hours=int(_resolve_setting(
                configuration_service,
                "runtime_findings.policy_denial_rate.resolution_window_hours",
                48,
            )),
        )

    @property
    def detector_id(self) -> str:
        return self._config.detector_id

    @property
    def detector_version(self) -> str:
        return self._config.detector_version

    @property
    def config(self) -> DetectorConfig:
        return self._config

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
        baseline_total = float(baseline_metrics.get("total_decisions", 0))
        baseline_denials = float(baseline_metrics.get("denials", 0))
        observed_total = float(observed_metrics.get("total_decisions", 0))
        observed_denials = float(observed_metrics.get("denials", 0))

        if observed_total < self._config.min_observation_count:
            return DetectorResult(insufficient_data=True)

        baseline_rate = baseline_denials / baseline_total if baseline_total > 0 else 0.0
        observed_rate = observed_denials / observed_total if observed_total > 0 else 0.0

        if observed_rate <= baseline_rate:
            return DetectorResult()
        if baseline_rate > 0 and observed_rate / baseline_rate < self._config.relative_threshold:
            return DetectorResult()
        if observed_rate < self._config.absolute_threshold:
            return DetectorResult()

        severity = _calculate_severity(self._config.severity_levels, "denial_rate", observed_rate)

        now = datetime.now(UTC)
        finding = RuntimeFinding(
            finding_id=f"finding:policy_denial_rate:{subject_id}:{now.isoformat()}",
            organization_id=organization_id,
            project_id=project_id,
            finding_type="POLICY_DENIAL_RATE_INCREASE",
            subject_type=subject_type,
            subject_id=subject_id,
            severity=severity,
            baseline_window=f"{self._config.baseline_window_days}d",
            observation_window=f"{self._config.observation_window_hours}h",
            baseline_metrics=(
                MetricSnapshot(name="denial_rate", value=baseline_rate, sample_size=int(baseline_total)),
            ),
            observed_metrics=(
                MetricSnapshot(name="denial_rate", value=observed_rate, sample_size=int(observed_total)),
            ),
            observation_count=int(observed_total),
            evidence_references=_build_evidence_references(
                self.detector_id, self.detector_version,
                {"baseline_denial_rate": baseline_rate},
                {"observed_denial_rate": observed_rate},
                self._config.absolute_threshold,
            ),
            related_execution_ids=related_execution_ids[:20],
            detector_id=self.detector_id,
            detector_version=self.detector_version,
            first_detected_at=now,
            last_detected_at=now,
        )
        return DetectorResult(finding=finding)


# ---------------------------------------------------------------------------
# 6. Repeated Runtime Error Detector
# ---------------------------------------------------------------------------

class RepeatedRuntimeErrorDetector(RuntimeDetector):
    """Detect repeated occurrences of the same structured error category."""

    def __init__(
        self,
        configuration_service: Any | None = None,
    ) -> None:
        self._config = DetectorConfig(
            detector_id="repeated_runtime_error",
            min_observation_count=int(_resolve_setting(
                configuration_service,
                "runtime_findings.repeated_runtime_error.min_observation_count",
                5,
            )),
            baseline_window_days=int(_resolve_setting(
                configuration_service,
                "runtime_findings.repeated_runtime_error.baseline_window_days",
                7,
            )),
            observation_window_hours=int(_resolve_setting(
                configuration_service,
                "runtime_findings.repeated_runtime_error.observation_window_hours",
                24,
            )),
            absolute_threshold=int(_resolve_setting(
                configuration_service,
                "runtime_findings.repeated_runtime_error.absolute_threshold",
                3,
            )),
            relative_threshold=1.0,
            severity_levels={
                "error_count_critical_threshold": int(_resolve_setting(
                    configuration_service,
                    "runtime_findings.repeated_runtime_error.severity_critical_threshold",
                    20,
                )),
                "error_count_high_threshold": int(_resolve_setting(
                    configuration_service,
                    "runtime_findings.repeated_runtime_error.severity_high_threshold",
                    10,
                )),
                "error_count_medium_threshold": int(_resolve_setting(
                    configuration_service,
                    "runtime_findings.repeated_runtime_error.severity_medium_threshold",
                    5,
                )),
                "error_count_low_threshold": int(_resolve_setting(
                    configuration_service,
                    "runtime_findings.repeated_runtime_error.severity_low_threshold",
                    3,
                )),
            },
            resolution_window_hours=int(_resolve_setting(
                configuration_service,
                "runtime_findings.repeated_runtime_error.resolution_window_hours",
                24,
            )),
        )

    @property
    def detector_id(self) -> str:
        return self._config.detector_id

    @property
    def detector_version(self) -> str:
        return self._config.detector_version

    @property
    def config(self) -> DetectorConfig:
        return self._config

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
        max_error_count = float(observed_metrics.get("max_errors", 0))

        if observation_count < self._config.min_observation_count:
            return DetectorResult(insufficient_data=True)
        if max_error_count < self._config.absolute_threshold:
            return DetectorResult()

        severity = _calculate_severity(self._config.severity_levels, "error_count", max_error_count)

        now = datetime.now(UTC)
        finding = RuntimeFinding(
            finding_id=f"finding:repeated_error:{subject_id}:{now.isoformat()}",
            organization_id=organization_id,
            project_id=project_id,
            finding_type="REPEATED_RUNTIME_ERROR",
            subject_type=subject_type,
            subject_id=subject_id,
            severity=severity,
            baseline_window=f"{self._config.baseline_window_days}d",
            observation_window=f"{self._config.observation_window_hours}h",
            baseline_metrics=(
                MetricSnapshot(name="max_error_count", value=float(baseline_metrics.get("max_errors", 0)), sample_size=int(observation_count)),
            ),
            observed_metrics=(
                MetricSnapshot(name="max_error_count", value=float(max_error_count), sample_size=int(observation_count)),
            ),
            observation_count=int(observation_count),
            evidence_references=_build_evidence_references(
                self.detector_id, self.detector_version,
                {"baseline_max_errors": baseline_metrics.get("max_errors", 0)},
                {"observed_max_errors": max_error_count},
                self._config.absolute_threshold,
            ),
            related_execution_ids=related_execution_ids[:20],
            detector_id=self.detector_id,
            detector_version=self.detector_version,
            first_detected_at=now,
            last_detected_at=now,
        )
        return DetectorResult(finding=finding)


# -- Registry -----------------------------------------------------------------

ALL_DETECTORS: tuple[type[RuntimeDetector], ...] = (
    ToolFailureRateDetector,
    AgentExecutionFailureRateDetector,
    ExecutionLatencyRegressionDetector,
    EvaluationFailureRateDetector,
    PolicyDenialRateDetector,
    RepeatedRuntimeErrorDetector,
)


def create_detector(detector_id: str, configuration_service: Any | None = None) -> RuntimeDetector:
    """Instantiate a detector by ID, optionally with configuration service."""
    for detector_cls in ALL_DETECTORS:
        if detector_cls().detector_id == detector_id:
            return detector_cls(configuration_service=configuration_service)
    raise ValueError(f"Unknown detector: {detector_id}")
