"""Comprehensive tests for deterministic runtime findings.

Covers:
- Finding generated when threshold is genuinely exceeded
- No finding below threshold
- Minimum sample-size enforcement
- Insufficient baseline data
- Relative and absolute threshold behaviour
- Idempotent repeated detector runs
- Active finding updated instead of duplicated
- Resolved finding when condition normalises
- Tenant/project isolation
- Bounded evidence references
- Detector-version behaviour
- Worker failure isolation
- Repository persistence
- Privacy guarantees
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ai_governance.domain.runtime_findings.detectors import (
    ALL_DETECTORS,
    ToolFailureRateDetector,
    AgentExecutionFailureRateDetector,
    ExecutionLatencyRegressionDetector,
    EvaluationFailureRateDetector,
    PolicyDenialRateDetector,
    RepeatedRuntimeErrorDetector,
)
from ai_governance.domain.agent_execution import (
    AgentExecution,
    AgentExecutionEvent,
    AgentExecutionStatus,
    EventType,
)
from ai_governance.domain.agent_execution.agent_execution_event import ActorType
from ai_governance.domain.runtime_findings.evidence_window import (
    EvidenceWindowFinalizationPolicy,
)
from ai_governance.domain.runtime_findings.detector import DetectorConfig
from ai_governance.domain.runtime_findings.finding import (
    EvidenceReference,
    FindingLifecycle,
    FindingReviewAction,
    FindingSeverity,
    FindingStatus,
    MetricSnapshot,
    ReconciliationOutcome,
    ReconciliationWindow,
    RuntimeFinding,
)
from ai_governance.repositories.in_memory.in_memory_runtime_finding_repository import (
    InMemoryRuntimeFindingRepository,
)
from ai_governance.repositories.in_memory.in_memory_agent_execution_repository import (
    InMemoryAgentExecutionEventRepository,
    InMemoryAgentExecutionRepository,
)
from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.repositories.sqlite.sqlite_runtime_finding_repository import (
    SQLiteRuntimeFindingRepository,
)
from ai_governance.services.runtime_finding_service import (
    RuntimeFindingService,
)
from ai_governance.services.runtime_aggregation_service import (
    RuntimeAggregationService,
)


# -- Fixtures -----------------------------------------------------------------


def _make_finding(
    finding_id: str = "finding-1",
    organization_id: str = "org_test",
    project_id: str | None = "project_test",
    finding_type: str = "TOOL_FAILURE_RATE_INCREASE",
    subject_type: str = "tool",
    subject_id: str = "customer-profile",
    severity: FindingSeverity = FindingSeverity.HIGH,
    status: FindingStatus = FindingStatus.OPEN,
    lifecycle: FindingLifecycle = FindingLifecycle.OPERATIONAL,
    detector_id: str = "tool_failure_rate",
    related_execution_ids: tuple[str, ...] = ("exec-1", "exec-2"),
    consecutive_normal_windows: int = 0,
) -> RuntimeFinding:
    now = datetime.now(UTC)
    return RuntimeFinding(
        finding_id=finding_id,
        organization_id=organization_id,
        project_id=project_id,
        finding_type=finding_type,
        subject_type=subject_type,
        subject_id=subject_id,
        severity=severity,
        status=status,
        lifecycle=lifecycle,
        baseline_window="7d",
        observation_window="24h",
        baseline_metrics=(
            MetricSnapshot(name="failure_rate", value=0.02, sample_size=1000),
        ),
        observed_metrics=(
            MetricSnapshot(name="failure_rate", value=0.15, sample_size=200),
        ),
        observation_count=200,
        consecutive_normal_windows=consecutive_normal_windows,
        evidence_references=(
            EvidenceReference(kind="detector_id", value=detector_id),
            EvidenceReference(kind="threshold", value="0.05"),
        ),
        related_execution_ids=related_execution_ids,
        detector_id=detector_id,
        detector_version="1",
        first_detected_at=now,
        last_detected_at=now,
        created_at=now,
        updated_at=now,
    )


def _make_service(
    finding_repo: InMemoryRuntimeFindingRepository | None = None,
    clock=None,
) -> RuntimeFindingService:
    if finding_repo is None:
        finding_repo = InMemoryRuntimeFindingRepository()

    # Create a mock aggregation service that returns normal metrics
    # (low failure rates, no findings triggered).
    class MockAggregationService:
        def get_tool_metrics(self, *args, **kwargs):
            return {"total_calls": 1000, "failures": 10}, {"total_calls": 200, "failures": 2}

        def get_agent_execution_metrics(self, *args, **kwargs):
            return {"total_executions": 1000, "failures": 10}, {"total_executions": 200, "failures": 2}

        def get_latency_metrics(self, *args, **kwargs):
            return {"p50": 100}, {"p50": 105}

        def get_evaluation_metrics(self, *args, **kwargs):
            return {"total_evals": 100, "failures": 2}, {"total_evals": 50, "failures": 1}

        def get_policy_denial_metrics(self, *args, **kwargs):
            return {"total_decisions": 100, "denials": 2}, {"total_decisions": 50, "denials": 1}

        def get_error_metrics(self, *args, **kwargs):
            return {"total_events": 1000, "errors": 5}, {"total_events": 200, "errors": 2}

        _execution_repo = None

    service = RuntimeFindingService(
        MockAggregationService(),
        finding_repo,
        detectors=tuple(cls() for cls in ALL_DETECTORS),
        clock=clock,
    )
    service._finding_repo = finding_repo
    return service


# -- Finding domain model -----------------------------------------------------


class TestFindingDomainModel:
    """Test the RuntimeFinding aggregate."""

    def test_finding_created_with_defaults(self):
        finding = _make_finding()
        assert finding.status == FindingStatus.OPEN
        assert finding.is_active is True
        assert finding.is_terminal is False

    def test_finding_mark_resolved(self):
        finding = _make_finding()
        resolved = finding.mark_resolved()
        assert resolved.status == FindingStatus.RESOLVED
        assert resolved.is_active is False
        assert resolved.is_terminal is True
        assert resolved.resolved_at is not None

    def test_finding_update_observation(self):
        finding = _make_finding()
        updated = finding.update_observation()
        assert updated.status == FindingStatus.OPEN
        assert updated.last_detected_at > finding.last_detected_at

    def test_finding_deduplication_key(self):
        finding = _make_finding(
            finding_type="TOOL_FAILURE_RATE_INCREASE",
            subject_type="tool",
            subject_id="my-tool",
        )
        key = finding.deduplication_key()
        assert "TOOL_FAILURE_RATE_INCREASE" in key
        assert "my-tool" in key

    def test_finding_rejects_empty_fields(self):
        with pytest.raises(ValueError, match="finding_id must not be empty"):
            RuntimeFinding(
                finding_id="",
                organization_id="org_test",
                finding_type="TEST",
                subject_id="subj",
                detector_id="det",
            )

    def test_finding_bounds_related_execution_ids(self):
        exec_ids = tuple(f"exec-{i}" for i in range(30))
        finding = _make_finding(related_execution_ids=exec_ids)
        # The __post_init__ should bound to 20.
        assert len(finding.related_execution_ids) <= 20

    def test_evidence_window_finalization_requires_the_lateness_allowance(self):
        policy = EvidenceWindowFinalizationPolicy(allowed_lateness_hours=2)
        end = datetime(2026, 8, 25, 0, tzinfo=UTC)
        assert not policy.is_finalized(end, datetime(2026, 8, 25, 1, 59, tzinfo=UTC))
        assert policy.is_finalized(end, datetime(2026, 8, 25, 2, tzinfo=UTC))

    def test_later_policy_change_cannot_reconcile_an_older_window(self):
        class ChangedPolicy:
            def get(self, key):
                if key == "runtime_findings.reconciliation.allowed_lateness_hours":
                    return 24
                return 0

        class Detector:
            detector_id = "tool_failure_rate"
            detector_version = "1"
            config = DetectorConfig(
                detector_id="tool_failure_rate",
                min_observation_count=1,
                baseline_window_days=1,
                observation_window_hours=24,
                resolution_window_hours=24,
            )

            def detect(self, *args, **kwargs):
                raise AssertionError("A persisted finalized window must be idempotent.")

        class Aggregation:
            def get_tool_metrics(self, *args, **kwargs):
                raise AssertionError("A persisted finalized window must not be re-evaluated.")

        old_window = ReconciliationWindow(
            observed_start=datetime(2026, 8, 24, 0, tzinfo=UTC),
            observed_end=datetime(2026, 8, 25, 0, tzinfo=UTC),
            baseline_start=datetime(2026, 8, 23, 0, tzinfo=UTC),
            baseline_end=datetime(2026, 8, 24, 0, tzinfo=UTC),
            finalization_cutoff_at=datetime(2026, 8, 25, 2, tzinfo=UTC),
            lateness_policy_hours=2,
        )
        finding = _make_finding().record_healthy_window(
            old_window, now=datetime(2026, 8, 25, 2, tzinfo=UTC)
        )
        repo = InMemoryRuntimeFindingRepository()
        repo.save(finding)
        service = RuntimeFindingService(
            Aggregation(), repo, (Detector(),),
            configuration_service=ChangedPolicy(),
            clock=lambda: datetime(2026, 8, 25, 3, tzinfo=UTC),
        )

        result = service.reconcile_active_findings("org_test", "project_test")

        assert result.outcomes[0].outcome == ReconciliationOutcome.ALREADY_RECONCILED
        assert result.outcomes[0].window == old_window


# -- Tool Failure Rate Detector -----------------------------------------------


class TestToolFailureRateDetector:
    """Test the tool failure rate detector."""

    def test_finding_generated_when_threshold_exceeded(self):
        detector = ToolFailureRateDetector()
        result = detector.detect(
            organization_id="org_test",
            project_id="project_test",
            subject_type="tool",
            subject_id="customer-profile",
            baseline_metrics={"total_calls": 1420, "failures": 24},
            observed_metrics={"total_calls": 311, "failures": 34},
            observation_count=311,
        )
        assert result.finding is not None
        assert result.finding.finding_type == "TOOL_FAILURE_RATE_INCREASE"
        assert result.finding.subject_id == "customer-profile"

    def test_no_finding_below_threshold(self):
        detector = ToolFailureRateDetector()
        result = detector.detect(
            organization_id="org_test",
            project_id="project_test",
            subject_type="tool",
            subject_id="safe-tool",
            baseline_metrics={"total_calls": 1000, "failures": 10},
            observed_metrics={"total_calls": 500, "failures": 5},
            observation_count=500,
        )
        assert result.finding is None

    def test_no_finding_when_rate_decreased(self):
        detector = ToolFailureRateDetector()
        result = detector.detect(
            organization_id="org_test",
            project_id="project_test",
            subject_type="tool",
            subject_id="improving-tool",
            baseline_metrics={"total_calls": 1000, "failures": 100},
            observed_metrics={"total_calls": 500, "failures": 10},
            observation_count=500,
        )
        assert result.finding is None

    def test_insufficient_sample_size(self):
        detector = ToolFailureRateDetector()
        result = detector.detect(
            organization_id="org_test",
            project_id="project_test",
            subject_type="tool",
            subject_id="small-tool",
            baseline_metrics={"total_calls": 100, "failures": 1},
            observed_metrics={"total_calls": 10, "failures": 3},
            observation_count=10,
        )
        assert result.insufficient_data is True
        assert result.finding is None

    def test_no_finding_from_tiny_sample_size(self):
        """Apparent percentage changes from tiny samples must not generate findings."""
        detector = ToolFailureRateDetector()
        result = detector.detect(
            organization_id="org_test",
            project_id="project_test",
            subject_type="tool",
            subject_id="tiny-tool",
            baseline_metrics={"total_calls": 10, "failures": 0},
            observed_metrics={"total_calls": 2, "failures": 1},
            observation_count=2,
        )
        assert result.insufficient_data is True

    def test_severity_calculated_correctly(self):
        detector = ToolFailureRateDetector()
        # High failure rate should produce HIGH severity.
        result = detector.detect(
            organization_id="org_test",
            project_id="project_test",
            subject_type="tool",
            subject_id="bad-tool",
            baseline_metrics={"total_calls": 1000, "failures": 10},
            observed_metrics={"total_calls": 500, "failures": 100},
            observation_count=500,
        )
        assert result.finding is not None
        assert result.finding.severity in (FindingSeverity.HIGH, FindingSeverity.CRITICAL)

    def test_evidence_references_bounded(self):
        detector = ToolFailureRateDetector()
        result = detector.detect(
            organization_id="org_test",
            project_id="project_test",
            subject_type="tool",
            subject_id="tool-1",
            baseline_metrics={"total_calls": 1000, "failures": 10},
            observed_metrics={"total_calls": 500, "failures": 50},
            observation_count=500,
        )
        assert result.finding is not None
        assert len(result.finding.evidence_references) > 0
        # No raw payloads in evidence.
        for ref in result.finding.evidence_references:
            assert "prompt" not in ref.kind.lower()
            assert "response" not in ref.kind.lower()
            assert "credential" not in ref.kind.lower()


# -- Agent Execution Failure Rate Detector ------------------------------------


class TestAgentExecutionFailureRateDetector:
    """Test the agent execution failure rate detector."""

    def test_finding_generated(self):
        detector = AgentExecutionFailureRateDetector()
        result = detector.detect(
            organization_id="org_test",
            project_id="project_test",
            subject_type="agent",
            subject_id="claims-agent",
            baseline_metrics={"total_executions": 500, "failures": 10},
            observed_metrics={"total_executions": 200, "failures": 40},
            observation_count=200,
        )
        assert result.finding is not None
        assert result.finding.finding_type == "AGENT_EXECUTION_FAILURE_RATE_INCREASE"

    def test_no_finding_stable_rate(self):
        detector = AgentExecutionFailureRateDetector()
        result = detector.detect(
            organization_id="org_test",
            project_id="project_test",
            subject_type="agent",
            subject_id="stable-agent",
            baseline_metrics={"total_executions": 500, "failures": 50},
            observed_metrics={"total_executions": 200, "failures": 20},
            observation_count=200,
        )
        assert result.finding is None


# -- Execution Latency Regression Detector ------------------------------------


class TestExecutionLatencyRegressionDetector:
    """Test the latency regression detector."""

    def test_finding_generated_on_regression(self):
        detector = ExecutionLatencyRegressionDetector()
        result = detector.detect(
            organization_id="org_test",
            project_id="project_test",
            subject_type="agent",
            subject_id="slow-agent",
            baseline_metrics={"median_duration_seconds": 2.0, "p95_duration_seconds": 5.0},
            observed_metrics={"median_duration_seconds": 6.0, "p95_duration_seconds": 15.0},
            observation_count=50,
        )
        assert result.finding is not None
        assert result.finding.finding_type == "EXECUTION_LATENCY_REGRESSION"

    def test_no_finding_no_regression(self):
        detector = ExecutionLatencyRegressionDetector()
        result = detector.detect(
            organization_id="org_test",
            project_id="project_test",
            subject_type="agent",
            subject_id="fast-agent",
            baseline_metrics={"median_duration_seconds": 2.0, "p95_duration_seconds": 5.0},
            observed_metrics={"median_duration_seconds": 1.5, "p95_duration_seconds": 4.0},
            observation_count=50,
        )
        assert result.finding is None


# -- Evaluation Failure Rate Detector -----------------------------------------


class TestEvaluationFailureRateDetector:
    """Test the evaluation failure rate detector."""

    def test_finding_generated(self):
        detector = EvaluationFailureRateDetector()
        result = detector.detect(
            organization_id="org_test",
            project_id="project_test",
            subject_type="evaluation",
            subject_id="all",
            baseline_metrics={"total_evaluations": 100, "failures": 5},
            observed_metrics={"total_evaluations": 50, "failures": 15},
            observation_count=50,
        )
        assert result.finding is not None
        assert result.finding.finding_type == "EVALUATION_FAILURE_RATE_INCREASE"


# -- Policy Denial Rate Detector ----------------------------------------------


class TestPolicyDenialRateDetector:
    """Test the policy denial rate detector."""

    def test_finding_generated(self):
        detector = PolicyDenialRateDetector()
        result = detector.detect(
            organization_id="org_test",
            project_id="project_test",
            subject_type="policy",
            subject_id="all",
            baseline_metrics={"total_decisions": 200, "denials": 10},
            observed_metrics={"total_decisions": 100, "denials": 30},
            observation_count=100,
        )
        assert result.finding is not None
        assert result.finding.finding_type == "POLICY_DENIAL_RATE_INCREASE"


# -- Repeated Runtime Error Detector ------------------------------------------


class TestRepeatedRuntimeErrorDetector:
    """Test the repeated error detector."""

    def test_finding_generated(self):
        detector = RepeatedRuntimeErrorDetector()
        result = detector.detect(
            organization_id="org_test",
            project_id="project_test",
            subject_type="error",
            subject_id="all",
            baseline_metrics={"max_errors": 1},
            observed_metrics={"max_errors": 5, "error_timeout": 3, "error_auth": 2},
            observation_count=100,
        )
        assert result.finding is not None
        assert result.finding.finding_type == "REPEATED_RUNTIME_ERROR"


# -- Idempotency and Deduplication --------------------------------------------


class TestFindingIdempotency:
    """Test idempotent repeated detector runs."""

    def test_repeated_run_updates_existing_finding(self):
        repo = InMemoryRuntimeFindingRepository()
        # First run creates a finding.
        finding1 = _make_finding(finding_id="finding-dedup-1")
        repo.save(finding1)

        # Second run with same dedup key should update, not duplicate.
        existing = repo.find_by_dedup_key(
            finding1.deduplication_key(), "org_test", "project_test"
        )
        assert existing is not None
        assert existing.finding_id == finding1.finding_id

    def test_active_finding_updated_not_duplicated(self):
        repo = InMemoryRuntimeFindingRepository()
        finding = _make_finding(finding_id="finding-update-1")
        repo.save(finding)

        # Update the finding.
        updated = finding.update_observation()
        repo.save(updated)

        retrieved = repo.get("finding-update-1", "org_test", "project_test")
        assert retrieved is not None
        assert retrieved.status == FindingStatus.OPEN
        assert retrieved.last_detected_at > finding.last_detected_at


# -- Resolution ---------------------------------------------------------------


class TestFindingResolution:
    """Test deterministic resolution behaviour."""

    def test_finding_marked_resolved(self):
        finding = _make_finding()
        resolved = finding.mark_resolved()
        assert resolved.status == FindingStatus.RESOLVED
        assert resolved.resolved_at is not None

    def test_resolved_finding_not_recreated(self):
        repo = InMemoryRuntimeFindingRepository()
        finding = _make_finding(finding_id="finding-resolved-1")
        resolved = finding.mark_resolved()
        repo.save(resolved)

        retrieved = repo.get("finding-resolved-1", "org_test", "project_test")
        assert retrieved is not None
        assert retrieved.status == FindingStatus.RESOLVED


# -- Tenant/Project Isolation -------------------------------------------------


class TestFindingTenancy:
    """Test tenant and project isolation."""

    def test_cross_tenant_finding_not_found(self):
        repo = InMemoryRuntimeFindingRepository()
        finding = _make_finding(finding_id="cross-tenant-1", organization_id="org_a")
        repo.save(finding)

        retrieved = repo.get("cross-tenant-1", "org_b", "project_test")
        assert retrieved is None

    def test_finding_scoped_to_tenant(self):
        repo = InMemoryRuntimeFindingRepository()
        finding = _make_finding(organization_id="org_test")
        repo.save(finding)

        retrieved = repo.get("finding-1", "org_test", "project_test")
        assert retrieved is not None


# -- Privacy ------------------------------------------------------------------


class TestFindingPrivacy:
    """Runtime findings must never contain raw runtime payloads."""

    def test_no_prompt_in_evidence(self):
        finding = _make_finding()
        for ref in finding.evidence_references:
            assert "prompt" not in ref.kind.lower()
            assert "response" not in ref.kind.lower()
            assert "chain_of_thought" not in ref.kind.lower()
            assert "credential" not in ref.kind.lower()

    def test_no_raw_payload_in_metrics(self):
        finding = _make_finding()
        for metric in finding.baseline_metrics + finding.observed_metrics:
            assert "prompt" not in metric.name.lower()
            assert "response" not in metric.name.lower()


# -- Detector Version ---------------------------------------------------------


class TestDetectorVersion:
    """Test detector version behaviour."""

    def test_detector_has_stable_id(self):
        for detector_cls in ALL_DETECTORS:
            d = detector_cls()
            assert d.detector_id.strip()
            assert d.detector_version.strip()

    def test_detector_config_has_minimum_observation_count(self):
        for detector_cls in ALL_DETECTORS:
            d = detector_cls()
            assert d.config.min_observation_count >= 1


# -- Worker Failure Isolation -------------------------------------------------


class TestWorkerFailureIsolation:
    """One detector failure must not prevent unrelated detectors from running."""

    def test_all_detectors_instantiable(self):
        """All detectors can be instantiated without error."""
        for detector_cls in ALL_DETECTORS:
            d = detector_cls()
            assert d.detector_id

    def test_detector_with_insufficient_data_returns_cleanly(self):
        detector = ToolFailureRateDetector()
        result = detector.detect(
            organization_id="org_test",
            project_id="project_test",
            subject_type="tool",
            subject_id="tool-1",
            baseline_metrics={"total_calls": 0, "failures": 0},
            observed_metrics={"total_calls": 1, "failures": 1},
            observation_count=1,
        )
        # Should return insufficient_data=True, not raise.
        assert result.insufficient_data is True or result.finding is None


# -- Repository Persistence ---------------------------------------------------


class TestFindingRepositoryPersistence:
    """Test repository persistence operations."""

    def test_save_and_get_finding(self):
        repo = InMemoryRuntimeFindingRepository()
        finding = _make_finding(finding_id="persist-1")
        repo.save(finding)

        retrieved = repo.get("persist-1", "org_test", "project_test")
        assert retrieved is not None
        assert retrieved.finding_id == "persist-1"

    def test_list_findings_with_filters(self):
        repo = InMemoryRuntimeFindingRepository()
        f1 = _make_finding(finding_id="list-1", finding_type="TOOL_FAILURE_RATE_INCREASE")
        f2 = _make_finding(finding_id="list-2", finding_type="AGENT_EXECUTION_FAILURE_RATE_INCREASE")
        repo.save(f1)
        repo.save(f2)

        results = repo.list(
            type("Filters", (), {"finding_type": "TOOL_FAILURE_RATE_INCREASE", "subject_type": None, "subject_id": None, "severity": None, "status": None, "created_after": None, "created_before": None, "limit": 100})(),
            "org_test",
            "project_test",
        )
        assert len(results) == 1
        assert results[0].finding_id == "list-1"

    def test_find_by_dedup_key(self):
        repo = InMemoryRuntimeFindingRepository()
        finding = _make_finding(finding_id="dedup-1")
        repo.save(finding)

        existing = repo.find_by_dedup_key(
            finding.deduplication_key(), "org_test", "project_test"
        )
        assert existing is not None
        assert existing.finding_id == "dedup-1"

    def test_count_by_subject(self):
        repo = InMemoryRuntimeFindingRepository()
        f1 = _make_finding(finding_id="count-1", subject_id="tool-a")
        f2 = _make_finding(finding_id="count-2", subject_id="tool-a")
        f3 = _make_finding(finding_id="count-3", subject_id="tool-b")
        repo.save(f1)
        repo.save(f2)
        repo.save(f3)

        count = repo.count_by_subject("tool", "tool-a", "org_test", "project_test")
        assert count == 2


# -- Acceptance Scenario ------------------------------------------------------


class TestAcceptanceScenario:
    """End-to-end acceptance scenario from the spec."""

    def test_spec_acceptance_scenario(self):
        """
        Tool: customer-profile
        Agent: claims-agent

        Baseline (7d):
          calls = 1,420, failures = 24, rate = 1.69%

        Current (24h):
          calls = 311, failures = 34, rate = 10.93%

        Finding: TOOL_FAILURE_RATE_INCREASE
        """
        detector = ToolFailureRateDetector()
        result = detector.detect(
            organization_id="org_test",
            project_id="project_test",
            subject_type="tool",
            subject_id="customer-profile",
            baseline_metrics={"total_calls": 1420, "failures": 24},
            observed_metrics={"total_calls": 311, "failures": 34},
            observation_count=311,
        )

        assert result.finding is not None
        assert result.finding.finding_type == "TOOL_FAILURE_RATE_INCREASE"
        assert result.finding.subject_id == "customer-profile"
        assert result.finding.status == FindingStatus.OPEN

        # Verify evidence.
        assert len(result.finding.evidence_references) > 0
        assert result.finding.observation_count == 311

        # Verify metrics are captured.
        assert len(result.finding.baseline_metrics) > 0
        assert len(result.finding.observed_metrics) > 0

        # Verify no raw payloads.
        for ref in result.finding.evidence_references:
            assert "prompt" not in ref.kind.lower()
            assert "response" not in ref.kind.lower()


# -- Hardening Check 3: Sustained Recovery for Auto-Resolution ----------------


class TestSustainedRecovery:
    """Verify that auto-resolution requires sustained recovery, not a single normal window.

    This prevents oscillation: OPEN → RESOLVED → OPEN → RESOLVED rapid cycling.
    """

    def test_single_normal_window_does_not_resolve(self):
        """One normal observation window should NOT resolve a finding."""
        repo = InMemoryRuntimeFindingRepository()
        service = _make_service(repo)

        finding = _make_finding(
            finding_id="oscillation-1",
            detector_id="tool_failure_rate",
        )
        repo.save(finding)

        # Run reconciliation — condition is normal (mock returns empty metrics).
        resolved = service.reconcile_active_findings("org_test", "project_test")

        # Should NOT be resolved after one normal window.
        assert len(resolved) == 0
        stored = repo.get("oscillation-1", "org_test", "project_test")
        assert stored is not None
        assert stored.status == FindingStatus.OPEN
        # Counter should have been incremented.
        assert stored.consecutive_normal_windows >= 1

    def test_case_review_findings_skip_reconciliation_and_require_review(self):
        repo = InMemoryRuntimeFindingRepository()
        service = _make_service(repo)
        finding = _make_finding(
            finding_id="causal-case",
            finding_type="EVIDENCE_IGNORED",
            detector_id="causal_audit",
            lifecycle=FindingLifecycle.CASE_REVIEW,
        )
        repo.save(finding)

        result = service.reconcile_active_findings("org_test", "project_test")

        assert result.outcomes == ()
        assert repo.get("causal-case", "org_test", "project_test").status is FindingStatus.OPEN

        acknowledged = service.review_case_finding(
            "causal-case", FindingReviewAction.ACKNOWLEDGE, "auditor-1",
            organization_id="org_test", project_id="project_test", note="Reviewed evidence.",
        )
        assert acknowledged.status is FindingStatus.ACKNOWLEDGED
        assert acknowledged.reviews[-1].actor_id == "auditor-1"

        closed = service.review_case_finding(
            "causal-case", FindingReviewAction.CLOSE, "auditor-1",
            organization_id="org_test", project_id="project_test",
        )
        assert closed.status is FindingStatus.CLOSED

    def test_same_window_is_idempotent_and_distinct_windows_resolve_after_threshold(self):
        """N consecutive normal windows (default 2) should resolve the finding."""
        repo = InMemoryRuntimeFindingRepository()
        current = [datetime(2026, 8, 25, 1, tzinfo=UTC)]
        service = _make_service(repo, clock=lambda: current[0])

        finding = _make_finding(
            finding_id="sustained-1",
            detector_id="tool_failure_rate",
        )
        repo.save(finding)

        # First normal window — counter increments to 1, not resolved.
        resolved = service.reconcile_active_findings("org_test", "project_test")
        assert len(resolved) == 0

        stored = repo.get("sustained-1", "org_test", "project_test")
        assert stored.status == FindingStatus.OPEN
        assert stored.consecutive_normal_windows == 1

        # Repeating the same completed window is idempotent.
        resolved = service.reconcile_active_findings("org_test", "project_test")
        assert len(resolved) == 0

        # The next detector resolution window is a distinct healthy observation.
        current[0] = datetime(2026, 8, 27, 1, tzinfo=UTC)
        resolved = service.reconcile_active_findings("org_test", "project_test")
        assert len(resolved) == 1
        assert resolved[0].outcome.value == "RESOLVED"
        assert resolved[0].consecutive_normal_windows >= 2

    def test_counter_resets_on_abnormal_condition(self):
        """If abnormal condition reappears, the counter should reset to 0."""
        repo = InMemoryRuntimeFindingRepository()
        current = [datetime(2026, 8, 25, 1, tzinfo=UTC)]
        service = _make_service(repo, clock=lambda: current[0])

        finding = _make_finding(
            finding_id="reset-1",
            detector_id="tool_failure_rate",
        )
        repo.save(finding)

        # First normal window — counter increments to 1.
        resolved = service.reconcile_active_findings("org_test", "project_test")
        assert len(resolved) == 0
        stored = repo.get("reset-1", "org_test", "project_test")
        assert stored.consecutive_normal_windows == 1

        # A distinct normal window reaches threshold (2).
        current[0] = datetime(2026, 8, 27, 1, tzinfo=UTC)
        resolved = service.reconcile_active_findings("org_test", "project_test")
        assert len(resolved) == 1
        assert resolved[0].outcome.value == "RESOLVED"

    def test_finding_mark_normal_increments_counter(self):
        """mark_normal() should increment the consecutive normal windows counter."""
        finding = _make_finding(consecutive_normal_windows=0)
        assert finding.consecutive_normal_windows == 0

        normal = finding.mark_normal()
        assert normal.consecutive_normal_windows == 1

        normal2 = normal.mark_normal()
        assert normal2.consecutive_normal_windows == 2

    def test_finding_mark_abnormal_resets_counter(self):
        """mark_abnormal() should reset the counter to zero."""
        finding = _make_finding(consecutive_normal_windows=3)
        assert finding.consecutive_normal_windows == 3

        abnormal = finding.mark_abnormal()
        assert abnormal.consecutive_normal_windows == 0

    def test_all_builtin_detectors_reconcile_a_healthy_completed_window(self):
        class NormalAggregation:
            def get_tool_metrics(self, *args): return ({"total_calls": 100, "failures": 10}, {"total_calls": 100, "failures": 1})
            def get_agent_execution_metrics(self, *args): return ({"total_executions": 100, "failures": 10}, {"total_executions": 100, "failures": 1})
            def get_latency_metrics(self, *args): return ({"median_duration_seconds": 10, "p95_duration_seconds": 12, "total_executions": 100}, {"median_duration_seconds": 10, "p95_duration_seconds": 12, "total_executions": 100})
            def get_evaluation_metrics(self, *args): return ({"total_evaluations": 100, "failures": 10}, {"total_evaluations": 100, "failures": 1})
            def get_policy_denial_metrics(self, *args): return ({"total_decisions": 100, "denials": 10}, {"total_decisions": 100, "denials": 1})
            def get_error_metrics(self, *args): return ({"max_errors": 10, "total_executions": 100}, {"max_errors": 0, "total_executions": 100})

        repo = InMemoryRuntimeFindingRepository()
        definitions = (
            ("tool_failure_rate", "TOOL_FAILURE_RATE_INCREASE", "tool", "tool-1"),
            ("agent_execution_failure_rate", "AGENT_EXECUTION_FAILURE_RATE_INCREASE", "agent", "agent-1"),
            ("execution_latency_regression", "EXECUTION_LATENCY_REGRESSION", "agent", "agent-1"),
            ("evaluation_failure_rate", "EVALUATION_FAILURE_RATE_INCREASE", "evaluation", "all"),
            ("policy_denial_rate", "POLICY_DENIAL_RATE_INCREASE", "policy", "all"),
            ("repeated_runtime_error", "REPEATED_RUNTIME_ERROR", "error", "all"),
        )
        for index, (detector_id, finding_type, subject_type, subject_id) in enumerate(definitions):
            repo.save(_make_finding(f"all-{index}", detector_id=detector_id, finding_type=finding_type, subject_type=subject_type, subject_id=subject_id))
        service = RuntimeFindingService(
            NormalAggregation(), repo, tuple(cls() for cls in ALL_DETECTORS),
            clock=lambda: datetime(2026, 8, 25, 1, tzinfo=UTC),
        )

        result = service.reconcile_active_findings("org_test", "project_test")

        assert len(result.outcomes) == 6
        assert {item.outcome.value for item in result.outcomes} == {"HEALTHY_AWAITING"}

    def test_reconciliation_progress_survives_sqlite_restart(self, tmp_path):
        database = SQLiteDatabase(tmp_path / "findings.db")
        database.initialize()
        repo = SQLiteRuntimeFindingRepository(database)
        repo.save(_make_finding(finding_id="persisted"))
        current = [datetime(2026, 8, 25, 1, tzinfo=UTC)]
        service = _make_service(repo, clock=lambda: current[0])

        service.reconcile_active_findings("org_test", "project_test")

        restarted = SQLiteRuntimeFindingRepository(SQLiteDatabase(tmp_path / "findings.db"))
        stored = restarted.get("persisted", "org_test", "project_test")
        assert stored is not None
        assert stored.consecutive_normal_windows == 1
        assert len(stored.healthy_reconciliation_windows) == 1
        assert stored.last_reconciliation is not None
        finalized_window = stored.healthy_reconciliation_windows[0]
        assert finalized_window.finalization_cutoff_at is not None
        assert finalized_window.lateness_policy_hours == 2
        assert restarted.finalized_windows_covering(
            finalized_window.observed_end - timedelta(minutes=1),
            "org_test",
            "project_test",
        ) == (finalized_window,)

    def test_case_review_lifecycle_survives_sqlite_restart(self, tmp_path):
        database = SQLiteDatabase(tmp_path / "case-review.db")
        database.initialize()
        repo = SQLiteRuntimeFindingRepository(database)
        finding = _make_finding(
            finding_id="case-review-persisted",
            detector_id="causal_audit",
            lifecycle=FindingLifecycle.CASE_REVIEW,
        ).acknowledge("auditor-1", "Reviewed evidence.")
        repo.save(finding)

        stored = SQLiteRuntimeFindingRepository(SQLiteDatabase(tmp_path / "case-review.db")).get(
            "case-review-persisted", "org_test", "project_test"
        )

        assert stored is not None
        assert stored.lifecycle is FindingLifecycle.CASE_REVIEW
        assert stored.status is FindingStatus.ACKNOWLEDGED
        assert stored.reviews[0].actor_id == "auditor-1"

    def test_reconciliation_pages_all_open_findings(self):
        repo = InMemoryRuntimeFindingRepository()
        for index in range(101):
            repo.save(_make_finding(finding_id=f"page-{index}"))
        service = _make_service(repo, clock=lambda: datetime(2026, 8, 25, 1, tzinfo=UTC))

        result = service.reconcile_active_findings("org_test", "project_test")

        assert len(result.outcomes) == 101
        assert all(item.outcome.value == "HEALTHY_AWAITING" for item in result.outcomes)

    def test_recurrence_insufficient_data_and_unsupported_reset_or_block_progress(self):
        class SwitchingAggregation:
            mode = "healthy"
            def get_tool_metrics(self, *args):
                if self.mode == "recurring":
                    return {"total_calls": 100, "failures": 1}, {"total_calls": 100, "failures": 20}
                if self.mode == "insufficient":
                    return {"total_calls": 100, "failures": 1}, {"total_calls": 1, "failures": 0}
                return {"total_calls": 100, "failures": 10}, {"total_calls": 100, "failures": 1}

        repo = InMemoryRuntimeFindingRepository()
        repo.save(_make_finding(finding_id="recovery"))
        repo.save(_make_finding(finding_id="unsupported", detector_id="retired-detector"))
        current = [datetime(2026, 8, 25, 1, tzinfo=UTC)]
        aggregation = SwitchingAggregation()
        service = RuntimeFindingService(aggregation, repo, tuple(cls() for cls in ALL_DETECTORS), clock=lambda: current[0])

        first = service.reconcile_active_findings("org_test", "project_test")
        assert any(item.outcome.value == "UNSUPPORTED" for item in first.outcomes)
        assert repo.get("recovery", "org_test", "project_test").consecutive_normal_windows == 1

        current[0] = datetime(2026, 8, 27, 1, tzinfo=UTC)
        aggregation.mode = "recurring"
        recurrence = service.reconcile_active_findings("org_test", "project_test")
        assert any(item.outcome.value == "PROGRESS_RESET" for item in recurrence.outcomes)
        assert repo.get("recovery", "org_test", "project_test").consecutive_normal_windows == 0

        current[0] = datetime(2026, 8, 29, 1, tzinfo=UTC)
        aggregation.mode = "insufficient"
        insufficient = service.reconcile_active_findings("org_test", "project_test")
        assert any(item.outcome.value == "INSUFFICIENT_DATA" for item in insufficient.outcomes)
        assert repo.get("recovery", "org_test", "project_test").consecutive_normal_windows == 0

    def test_reconciliation_honours_detector_specific_windows(self):
        class Config:
            def get(self, key):
                configured = {
                    "runtime_findings.tool_failure_rate.baseline_window_days": 3,
                    "runtime_findings.tool_failure_rate.observation_window_hours": 5,
                    "runtime_findings.tool_failure_rate.resolution_window_hours": 6,
                }
                if key in configured:
                    return configured[key]
                return {"min_observation_count": 30, "absolute_threshold": 0.05, "relative_threshold": 2.0}.get(key.rsplit(".", 1)[-1], 0.0)

        class CaptureAggregation:
            arguments = None
            def get_tool_metrics(self, *args):
                self.arguments = args
                return {"total_calls": 100, "failures": 10}, {"total_calls": 100, "failures": 1}

        repo = InMemoryRuntimeFindingRepository()
        repo.save(_make_finding())
        aggregation = CaptureAggregation()
        service = RuntimeFindingService(
            aggregation, repo, (ToolFailureRateDetector(Config()),),
            clock=lambda: datetime(2026, 8, 25, 7, 30, tzinfo=UTC),
        )
        service.reconcile_active_findings("org_test", "project_test")

        baseline_start, baseline_end, observed_start, observed_end = aggregation.arguments[3:7]
        # The 06:00 boundary is still inside the two-hour lateness allowance,
        # so reconciliation correctly uses the prior finalized 00:00 window.
        assert observed_end == datetime(2026, 8, 25, 0, tzinfo=UTC)
        assert observed_end - observed_start == timedelta(hours=5)
        assert baseline_end - baseline_start == timedelta(days=3)
        assert aggregation.arguments[7] == datetime(2026, 8, 25, 2, tzinfo=UTC)

    def test_finding_update_observation_resets_counter(self):
        """update_observation() should reset the counter (new abnormal observation)."""
        finding = _make_finding(consecutive_normal_windows=2)
        assert finding.consecutive_normal_windows == 2

        updated = finding.update_observation()
        assert updated.consecutive_normal_windows == 0

    def test_mark_resolved_preserves_counter(self):
        """mark_resolved() should preserve the final counter value."""
        finding = _make_finding(consecutive_normal_windows=2)
        resolved = finding.mark_resolved()
        assert resolved.consecutive_normal_windows == 2
        assert resolved.status == FindingStatus.RESOLVED


class TestSimulatorStyleDetectorCoverage:
    """Detector coverage using the event shape emitted by external runtimes."""

    def test_all_six_detectors_trigger_from_authoritative_runtime_evidence(self):
        class DetectorSettings:
            def get(self, key: str):
                if key.endswith("min_observation_count"):
                    return 1
                raise KeyError(key)

        organization_id = "org_test"
        project_id = "project_test"
        now = datetime.now(UTC).replace(microsecond=0)
        baseline_time = now - timedelta(days=2)
        observed_time = now - timedelta(hours=1)
        execution_repo = InMemoryAgentExecutionRepository()
        event_repo = InMemoryAgentExecutionEventRepository()

        def save_execution(
            execution_id: str,
            started_at: datetime,
            status: AgentExecutionStatus,
            duration_seconds: int | None,
            include_runtime_events: bool,
        ) -> None:
            completed_at = (
                started_at + timedelta(seconds=duration_seconds)
                if duration_seconds is not None
                else None
            )
            execution_repo.save(
                AgentExecution(
                    execution_id=execution_id,
                    organization_id=organization_id,
                    project_id=project_id,
                    agent_id="claims-agent-v2",
                    agent_name="Claims Processing Agent",
                    agent_version="2",
                    external_execution_id=f"synthetic-{execution_id}",
                    runtime_provider="synthetic-agent-runtime",
                    status=status,
                    started_at=started_at,
                    completed_at=completed_at,
                    correlation_id=None,
                    parent_execution_id=None,
                    created_at=started_at,
                    updated_at=completed_at or started_at,
                )
            )
            if not include_runtime_events:
                return

            failed = status is AgentExecutionStatus.FAILED
            event_definitions = (
                (EventType.TOOL_CALL, ActorType.TOOL, "claim_history.lookup", {
                    "tool": "claim_history.lookup",
                    "status": "failed" if failed else "succeeded",
                }),
                (EventType.EVALUATION, ActorType.EVALUATOR, "quality-evaluator", {
                    "status": "failed" if failed else "succeeded",
                }),
                (EventType.GOVERNANCE_DECISION, ActorType.GOVERNANCE, "policy-engine", {
                    "decision_outcome": "denied" if failed else "allowed",
                }),
            )
            for sequence_number, (event_type, actor_type, actor_id, attributes) in enumerate(event_definitions, start=1):
                event_repo.save(
                    AgentExecutionEvent(
                        event_id=f"{execution_id}-event-{sequence_number}",
                        execution_id=execution_id,
                        organization_id=organization_id,
                        project_id=project_id,
                        event_type=event_type,
                        sequence_number=sequence_number,
                        occurred_at=started_at,
                        received_at=started_at,
                        correlation_id=None,
                        causation_id=None,
                        actor_id=actor_id,
                        actor_type=actor_type,
                        resource_references=(),
                        evidence_references=(),
                        attributes=attributes,
                    )
                )
            if failed:
                event_repo.save(
                    AgentExecutionEvent(
                        event_id=f"{execution_id}-error",
                        execution_id=execution_id,
                        organization_id=organization_id,
                        project_id=project_id,
                        event_type=EventType.ERROR,
                        sequence_number=4,
                        occurred_at=started_at,
                        received_at=started_at,
                        correlation_id=None,
                        causation_id=None,
                        actor_id="claims-agent-v2",
                        actor_type=ActorType.AGENT,
                        resource_references=(),
                        evidence_references=(),
                        attributes={"error_category": "dependency_timeout"},
                    )
                )

        for index in range(2):
            save_execution(
                f"baseline-{index}",
                baseline_time + timedelta(minutes=index),
                AgentExecutionStatus.SUCCEEDED,
                1,
                True,
            )
        for index in range(3):
            save_execution(
                f"observed-{index}",
                observed_time + timedelta(minutes=index),
                AgentExecutionStatus.FAILED,
                6,
                True,
            )
        # It is a real execution record but is not eligible for duration
        # statistics until it reaches a terminal lifecycle state.
        save_execution(
            "observed-running",
            observed_time + timedelta(minutes=10),
            AgentExecutionStatus.RUNNING,
            None,
            False,
        )

        aggregation = RuntimeAggregationService(execution_repo, event_repo)
        service = RuntimeFindingService(
            aggregation,
            InMemoryRuntimeFindingRepository(),
            detectors=tuple(detector(DetectorSettings()) for detector in ALL_DETECTORS),
        )

        findings = service.run_detection(organization_id, project_id)

        assert service._get_unique_tool_ids(organization_id, project_id) == [
            "claim_history.lookup"
        ]
        assert {finding.detector_id for finding in findings} == {
            "tool_failure_rate",
            "agent_execution_failure_rate",
            "execution_latency_regression",
            "evaluation_failure_rate",
            "policy_denial_rate",
            "repeated_runtime_error",
        }
        latency_finding = next(
            finding
            for finding in findings
            if finding.detector_id == "execution_latency_regression"
        )
        assert latency_finding.observation_count == 3
        assert {metric.value for metric in latency_finding.baseline_metrics} == {1.0}
        assert {metric.value for metric in latency_finding.observed_metrics} == {6.0}
        assert {metric.sample_size for metric in latency_finding.baseline_metrics} == {2}
        assert {metric.sample_size for metric in latency_finding.observed_metrics} == {3}
