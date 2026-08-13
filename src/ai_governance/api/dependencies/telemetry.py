"""Application composition for the telemetry subsystem."""

from __future__ import annotations

from fastapi import Request

from ai_governance.api.dependencies.settings_control import get_configuration_service, get_settings_repository
from ai_governance.events import EvaluationCompleted, ExecutionCompleted, ResourceLifecycleEvent
from ai_governance.services.telemetry_service import TelemetryService
from ai_governance.telemetry.events import TelemetryEventBridge
from ai_governance.telemetry.repository import SettingsTelemetryStateRepository


def install_telemetry(app) -> TelemetryService:
    """Install a single fail-open collector and subscribe to stable facts."""
    service = TelemetryService(
        SettingsTelemetryStateRepository(get_settings_repository()),
        get_configuration_service(),
    )
    bridge = TelemetryEventBridge(service)
    publisher = app.state.extension_registry.events
    publisher.subscribe(event_type=EvaluationCompleted, handler=bridge.evaluation_completed, plugin_name="core-telemetry")
    publisher.subscribe(event_type=ExecutionCompleted, handler=bridge.execution_completed, plugin_name="core-telemetry")
    publisher.subscribe(event_type=ResourceLifecycleEvent, handler=bridge.lifecycle, plugin_name="core-telemetry")
    app.state.telemetry_service = service
    return service


def get_telemetry_service(request: Request) -> TelemetryService:
    return request.app.state.telemetry_service
