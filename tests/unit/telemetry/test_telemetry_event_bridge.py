from ai_governance.domain.telemetry import TelemetryMetric
from ai_governance.events import ResourceLifecycleEvent
from ai_governance.telemetry.events import TelemetryEventBridge


class _Collector:
    def __init__(self) -> None:
        self.metrics: list[TelemetryMetric] = []

    def record(self, metric: TelemetryMetric, *, duration_ms: int | None = None) -> None:
        self.metrics.append(metric)


def test_event_bridge_uses_only_canonical_asset_tag() -> None:
    collector = _Collector()
    bridge = TelemetryEventBridge(collector)  # type: ignore[arg-type]
    bridge.lifecycle(
        ResourceLifecycleEvent(
            tenant={"organization_id": "org", "project_id": "project"},
            resource_kind="asset",
            resource_id="customer-owned-id",
            state="registered",
            payload={"asset_type": "PromptVersion", "prompt": "must never be collected"},
        )
    )

    assert collector.metrics == [TelemetryMetric.PROMPT_ASSETS]
