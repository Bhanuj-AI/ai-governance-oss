from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ai_governance.domain.runtime_findings.detectors import ToolFailureRateDetector
from ai_governance.domain.runtime_findings.finding import ReconciliationOutcome
from ai_governance.repositories.in_memory.in_memory_runtime_finding_repository import (
    InMemoryRuntimeFindingRepository,
)
from ai_governance.services.runtime_finding_service import RuntimeFindingService
from ai_governance.settings_control.domain import SettingContext, SettingScope
from ai_governance.settings_control.repository import InMemorySettingsRepository
from ai_governance.settings_control.service import ConfigurationService


NOW = datetime(2026, 8, 26, 12, 5, tzinfo=UTC)
CONTEXT = SettingContext("org-test", "project-validation")


class _Aggregation:
    def __init__(self) -> None:
        self.healthy = False
        self.calls: list[tuple] = []

    def get_observed_tool_ids(self, _organization_id, _project_id):
        return ("policy.lookup",)

    def get_tool_metrics(self, *args):
        self.calls.append(args)
        if self.healthy:
            return {"total_calls": 100, "failures": 1}, {"total_calls": 100, "failures": 1}
        return {"total_calls": 100, "failures": 1}, {"total_calls": 100, "failures": 30}


def test_validation_profile_uses_project_scoped_minute_windows_and_real_finalization():
    configuration = ConfigurationService(
        InMemorySettingsRepository(),
        {
            "AI_GOVERNANCE_RUNTIME_FINDINGS_TEST_WINDOWS_ENABLED": "true",
            "AI_GOVERNANCE_RUNTIME_FINDINGS_TEST_WINDOW_PROJECT_ID": "project-validation",
        },
    )
    _set(configuration, "runtime_findings.validation_profile.enabled", True)
    _set(configuration, "runtime_findings.validation_profile.baseline_minutes", 10)
    _set(configuration, "runtime_findings.validation_profile.observation_minutes", 2)
    _set(configuration, "runtime_findings.validation_profile.resolution_minutes", 2)
    _set(configuration, "runtime_findings.reconciliation.allowed_lateness_hours", 0)

    aggregation = _Aggregation()
    repository = InMemoryRuntimeFindingRepository()
    service = RuntimeFindingService(
        aggregation,
        repository,
        (ToolFailureRateDetector(configuration),),
        configuration_service=configuration,
        clock=lambda: NOW,
    )

    findings = service.run_detection("org-test", "project-validation")

    assert len(findings) == 1
    assert findings[0].baseline_window == "10m"
    assert findings[0].observation_window == "2m"
    baseline_start, baseline_end, observed_start, observed_end = aggregation.calls[0][3:7]
    assert baseline_end - baseline_start == timedelta(minutes=10)
    assert observed_end - observed_start == timedelta(minutes=2)

    aggregation.healthy = True
    reconciliation = service.reconcile_active_findings("org-test", "project-validation")
    outcome = reconciliation.outcomes[0]

    assert outcome.outcome is ReconciliationOutcome.HEALTHY_AWAITING
    assert outcome.window is not None
    assert outcome.window.observed_end == datetime(2026, 8, 26, 12, 4, tzinfo=UTC)
    assert outcome.window.observed_end - outcome.window.observed_start == timedelta(minutes=2)
    assert outcome.window.baseline_end - outcome.window.baseline_start == timedelta(minutes=10)
    assert outcome.window.finalization_cutoff_at == outcome.window.observed_end


def test_validation_profile_cannot_affect_an_unapproved_project():
    configuration = ConfigurationService(
        InMemorySettingsRepository(),
        {
            "AI_GOVERNANCE_RUNTIME_FINDINGS_TEST_WINDOWS_ENABLED": "true",
            "AI_GOVERNANCE_RUNTIME_FINDINGS_TEST_WINDOW_PROJECT_ID": "project-validation",
        },
    )
    _set(configuration, "runtime_findings.validation_profile.enabled", True)
    _set(configuration, "runtime_findings.validation_profile.baseline_minutes", 10)
    _set(configuration, "runtime_findings.validation_profile.observation_minutes", 2)
    _set(configuration, "runtime_findings.validation_profile.resolution_minutes", 2)

    aggregation = _Aggregation()
    service = RuntimeFindingService(
        aggregation,
        InMemoryRuntimeFindingRepository(),
        (ToolFailureRateDetector(configuration),),
        configuration_service=configuration,
        clock=lambda: NOW,
    )

    findings = service.run_detection("org-test", "another-project")

    assert len(findings) == 1
    assert findings[0].baseline_window == "7d"
    assert findings[0].observation_window == "24h"
    baseline_start, baseline_end, observed_start, observed_end = aggregation.calls[0][3:7]
    assert baseline_end - baseline_start == timedelta(days=7)
    assert observed_end - observed_start == timedelta(hours=24)


def _set(configuration: ConfigurationService, key: str, value: object) -> None:
    current = configuration.resolve(key, CONTEXT, SettingScope.PROJECT)
    configuration.update(
        key,
        value,
        "synthetic-agent-runtime",
        "Synthetic Agent Runtime local validation",
        current.version or 0,
        SettingScope.PROJECT,
        CONTEXT,
    )
