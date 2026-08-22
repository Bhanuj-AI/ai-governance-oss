"""Typed runtime-connection resource storage backed by the durable settings store.

The settings store supplies durable, scoped records and an audit trail; this
adapter does not expose runtime connections as ordinary configuration settings.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ai_governance.domain.runtime_connection import (
    RuntimeConnection,
    RuntimeConnectionTestStatus,
)
from ai_governance.repositories.runtime_connection_repository import (
    RuntimeConnectionRepository,
)
from ai_governance.settings_control.domain import SettingScope
from ai_governance.settings_control.repository import SettingsRepository

_KEY_PREFIX = "runtime_connection."


class SettingsRuntimeConnectionRepository(RuntimeConnectionRepository):
    def __init__(self, settings_repository: SettingsRepository) -> None:
        self._settings_repository = settings_repository

    def save(self, connection: RuntimeConnection) -> RuntimeConnection:
        key = _key(connection.runtime_connection_id)
        scope, scope_id = _scope(connection.organization_id, connection.project_id)
        existing = self._settings_repository.get(key, scope, scope_id)
        saved = self._settings_repository.save(
            key=key,
            scope=scope,
            scope_id=scope_id,
            value=_to_value(connection),
            actor_id=connection.updated_by,
            reason="runtime connection updated",
            expected_version=existing.version if existing else 0,
        )
        return _from_value(saved.value, saved.version)

    def find_by_id(
        self, runtime_connection_id: str, organization_id: str, project_id: str | None
    ) -> RuntimeConnection | None:
        if project_id:
            item = self._settings_repository.get(
                _key(runtime_connection_id),
                SettingScope.PROJECT,
                _project_scope_id(organization_id, project_id),
            )
            if item:
                return _from_value(item.value, item.version)
        item = self._settings_repository.get(
            _key(runtime_connection_id), SettingScope.ORGANIZATION, organization_id
        )
        return _from_value(item.value, item.version) if item else None

    def list_for_scope(
        self, organization_id: str, project_id: str | None
    ) -> list[RuntimeConnection]:
        connections = [
            _from_value(item.value, item.version)
            for item in self._settings_repository.list()
            if item.key.startswith(_KEY_PREFIX)
            and (
                (item.scope is SettingScope.ORGANIZATION and item.scope_id == organization_id)
                or (
                    project_id is not None
                    and item.scope is SettingScope.PROJECT
                    and item.scope_id == _project_scope_id(organization_id, project_id)
                )
            )
        ]
        return sorted(
            connections,
            key=lambda item: (item.display_name.lower(), item.runtime_connection_id),
        )


def _key(runtime_connection_id: str) -> str:
    return f"{_KEY_PREFIX}{runtime_connection_id}"


def _project_scope_id(organization_id: str, project_id: str) -> str:
    return f"{organization_id}:{project_id}"


def _scope(organization_id: str, project_id: str | None) -> tuple[SettingScope, str]:
    if project_id is None:
        return SettingScope.ORGANIZATION, organization_id
    return SettingScope.PROJECT, _project_scope_id(organization_id, project_id)


def _to_value(connection: RuntimeConnection) -> dict[str, Any]:
    return {
        "runtime_connection_id": connection.runtime_connection_id,
        "display_name": connection.display_name,
        "provider": connection.provider,
        "settings": dict(connection.settings),
        "secret_refs": dict(connection.secret_refs),
        "enabled": connection.enabled,
        "organization_id": connection.organization_id,
        "project_id": connection.project_id,
        "created_by": connection.created_by,
        "updated_by": connection.updated_by,
        "created_at": connection.created_at.isoformat(),
        "updated_at": connection.updated_at.isoformat(),
        "last_tested_at": connection.last_tested_at.isoformat()
        if connection.last_tested_at
        else None,
        "last_test_status": connection.last_test_status.value,
        "last_test_message": connection.last_test_message,
    }


def _from_value(value: Any, version: int) -> RuntimeConnection:
    if not isinstance(value, dict):
        raise TypeError("Runtime connection persistence value must be an object.")
    last_tested_at = value.get("last_tested_at")
    return RuntimeConnection(
        runtime_connection_id=str(value["runtime_connection_id"]),
        display_name=str(value["display_name"]),
        provider=str(value["provider"]),
        settings=dict(value.get("settings") or {}),
        secret_refs=dict(value.get("secret_refs") or {}),
        enabled=bool(value.get("enabled", True)),
        organization_id=str(value["organization_id"]),
        project_id=(str(value["project_id"]) if value.get("project_id") else None),
        created_by=str(value["created_by"]),
        updated_by=str(value.get("updated_by") or value["created_by"]),
        created_at=datetime.fromisoformat(str(value["created_at"])),
        updated_at=datetime.fromisoformat(str(value["updated_at"])),
        last_tested_at=datetime.fromisoformat(str(last_tested_at)) if last_tested_at else None,
        last_test_status=RuntimeConnectionTestStatus(
            str(value.get("last_test_status") or RuntimeConnectionTestStatus.NOT_TESTED.value)
        ),
        last_test_message=(str(value["last_test_message"]) if value.get("last_test_message") else None),
        version=version,
    )
