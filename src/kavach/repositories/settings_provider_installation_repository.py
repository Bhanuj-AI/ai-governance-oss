"""Provider-installation persistence backed by the durable settings store.

Settings persistence already supplies SQLite/Postgres durability and an audit
trail. This adapter gives provider installations a typed, tenant-scoped
repository without treating provider configuration as executable code.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from kavach.domain.provider_installation import ProviderInstallation
from kavach.repositories.provider_installation_repository import ProviderInstallationRepository
from kavach.settings_control.domain import SettingScope
from kavach.settings_control.repository import SettingsRepository


_KEY_PREFIX = "provider_installation."


class SettingsProviderInstallationRepository(ProviderInstallationRepository):
    def __init__(self, settings_repository: SettingsRepository) -> None:
        self._settings_repository = settings_repository

    def save(self, installation: ProviderInstallation) -> ProviderInstallation:
        key = _key(installation.installation_id)
        scope, scope_id = _scope(installation.organization_id, installation.project_id)
        existing = self._settings_repository.get(key, scope, scope_id)
        saved = self._settings_repository.save(
            key=key,
            scope=scope,
            scope_id=scope_id,
            value=_to_value(installation),
            actor_id=installation.updated_by,
            reason="provider installation updated",
            expected_version=existing.version if existing else 0,
        )
        return _from_value(saved.value, saved.version)

    def find_by_id(
        self, installation_id: str, organization_id: str, project_id: str | None
    ) -> ProviderInstallation | None:
        if project_id:
            item = self._settings_repository.get(
                _key(installation_id), SettingScope.PROJECT, _project_scope_id(organization_id, project_id)
            )
            if item:
                return _from_value(item.value, item.version)
        item = self._settings_repository.get(_key(installation_id), SettingScope.ORGANIZATION, organization_id)
        return _from_value(item.value, item.version) if item else None

    def list_for_scope(
        self, organization_id: str, project_id: str | None
    ) -> list[ProviderInstallation]:
        installations = [
            _from_value(item.value, item.version)
            for item in self._settings_repository.list()
            if item.key.startswith(_KEY_PREFIX)
            and (
                (item.scope is SettingScope.ORGANIZATION and item.scope_id == organization_id)
                or (project_id is not None and item.scope is SettingScope.PROJECT and item.scope_id == _project_scope_id(organization_id, project_id))
            )
        ]
        return sorted(installations, key=lambda item: (item.display_name.lower(), item.installation_id))


def _key(installation_id: str) -> str:
    return f"{_KEY_PREFIX}{installation_id}"


def _project_scope_id(organization_id: str, project_id: str) -> str:
    return f"{organization_id}:{project_id}"


def _scope(organization_id: str, project_id: str | None) -> tuple[SettingScope, str]:
    if project_id is None:
        return SettingScope.ORGANIZATION, organization_id
    return SettingScope.PROJECT, _project_scope_id(organization_id, project_id)


def _to_value(installation: ProviderInstallation) -> dict[str, Any]:
    return {
        "installation_id": installation.installation_id,
        "provider_type": installation.provider_type,
        "adapter_version": installation.adapter_version,
        "display_name": installation.display_name,
        "settings": dict(installation.settings),
        "secret_refs": dict(installation.secret_refs),
        "enabled": installation.enabled,
        "organization_id": installation.organization_id,
        "project_id": installation.project_id,
        "created_by": installation.created_by,
        "updated_by": installation.updated_by,
        "created_at": installation.created_at.isoformat(),
        "updated_at": installation.updated_at.isoformat(),
    }


def _from_value(value: Any, version: int) -> ProviderInstallation:
    if not isinstance(value, dict):
        raise ValueError("Provider installation persistence value must be an object.")
    return ProviderInstallation(
        installation_id=str(value["installation_id"]),
        provider_type=str(value["provider_type"]),
        adapter_version=str(value.get("adapter_version") or "unknown"),
        display_name=str(value["display_name"]),
        settings=dict(value.get("settings") or {}),
        secret_refs=dict(value.get("secret_refs") or {}),
        enabled=bool(value.get("enabled", True)),
        organization_id=str(value["organization_id"]),
        project_id=(str(value["project_id"]) if value.get("project_id") else None),
        created_by=str(value["created_by"]),
        updated_by=str(value.get("updated_by") or value["created_by"]),
        created_at=datetime.fromisoformat(str(value["created_at"])),
        updated_at=datetime.fromisoformat(str(value["updated_at"])),
        version=version,
    )
