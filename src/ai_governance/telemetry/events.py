"""Convert existing canonical lifecycle facts into anonymous aggregate metrics."""

from __future__ import annotations

from ai_governance.domain.telemetry import TelemetryMetric
from ai_governance.events import EvaluationCompleted, ExecutionCompleted, ResourceLifecycleEvent
from ai_governance.services.telemetry_service import TelemetryService


class TelemetryEventBridge:
    """Never reads result content; lifecycle mapping uses only canonical tags."""

    def __init__(self, telemetry: TelemetryService) -> None:
        self._telemetry = telemetry

    def evaluation_completed(self, event: EvaluationCompleted) -> None:
        self._telemetry.record(TelemetryMetric.EVALUATION_RUNS)

    def execution_completed(self, event: ExecutionCompleted) -> None:
        self._telemetry.record(TelemetryMetric.GOVERNED_EXECUTIONS)

    def lifecycle(self, event: ResourceLifecycleEvent) -> None:
        metric = {
            ("replay", "completed"): TelemetryMetric.REPLAY_RUNS,
            ("governance_decision", "created"): TelemetryMetric.GOVERNANCE_DECISIONS,
            ("impact_simulation", "completed"): TelemetryMetric.IMPACT_SIMULATIONS,
            ("behavior_contract", "created"): TelemetryMetric.BEHAVIOR_CONTRACTS_CREATED,
            ("prompt", "registered"): TelemetryMetric.PROMPT_ASSETS,
            ("model", "registered"): TelemetryMetric.MODEL_ASSETS,
            ("dataset", "registered"): TelemetryMetric.DATASET_ASSETS,
            ("evaluation_provider", "registered"): TelemetryMetric.EVALUATION_PROVIDER_ASSETS,
            ("job", "queued"): TelemetryMetric.JOB_EXECUTIONS,
            ("candidate_execution", "completed"): TelemetryMetric.GOVERNED_EXECUTIONS,
        }.get((event.resource_kind, event.state))
        if metric is None and event.resource_kind == "asset" and event.state == "registered":
            # Producers use this fixed lifecycle tag. The customer-owned asset
            # identifier/name and all other payload values remain unread.
            metric = {
                "PromptVersion": TelemetryMetric.PROMPT_ASSETS,
                "ModelVersion": TelemetryMetric.MODEL_ASSETS,
                "DatasetVersion": TelemetryMetric.DATASET_ASSETS,
                "EvaluationProvider": TelemetryMetric.EVALUATION_PROVIDER_ASSETS,
            }.get(str(event.payload.get("asset_type", "")))
        if metric is not None:
            self._telemetry.record(metric)
