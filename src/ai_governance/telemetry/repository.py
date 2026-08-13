"""Durable, installation-scoped telemetry state using the configured settings store."""

from __future__ import annotations

from typing import Any, Protocol

from ai_governance.settings_control.domain import SettingScope, SettingVersionConflict
from ai_governance.settings_control.repository import SettingsRepository

_STATE_KEY = "telemetry.runtime_state.v1"


class TelemetryStateRepository(Protocol):
    def load(self) -> tuple[dict[str, Any] | None, int]: ...
    def save(self, value: dict[str, Any], expected_version: int) -> int: ...


class SettingsTelemetryStateRepository:
    """Persist telemetry independently of tenant scope without a new storage backend."""

    def __init__(self, settings_repository: SettingsRepository) -> None:
        self._settings_repository = settings_repository

    def load(self) -> tuple[dict[str, Any] | None, int]:
        current = self._settings_repository.get(_STATE_KEY, SettingScope.SYSTEM, "")
        if current is None:
            return None, 0
        if not isinstance(current.value, dict):
            return None, current.version
        return dict(current.value), current.version

    def save(self, value: dict[str, Any], expected_version: int) -> int:
        saved = self._settings_repository.save(
            _STATE_KEY, SettingScope.SYSTEM, "", value,
            actor_id="telemetry-system", reason="Telemetry aggregation state update",
            expected_version=expected_version,
        )
        return saved.version


__all__ = ["SettingsTelemetryStateRepository", "TelemetryStateRepository", "SettingVersionConflict"]
