"""Runtime-connection service wiring."""

from __future__ import annotations

from typing import Any

from fastapi import Depends

from ai_governance.api.dependencies.settings_control import (
    get_configuration_service,
    get_runtime_connection_repository,
)
from ai_governance.settings_control import ConfigurationService
from ai_governance.settings_control.domain import SettingContext
from ai_governance.tenancy.domain import TenantContext


def get_runtime_connection_service(
    repository: Any = Depends(get_runtime_connection_repository),
    configuration_service: ConfigurationService = Depends(get_configuration_service),
) -> Any:
    """Build a tenant-scoped runtime connection service."""
    from ai_governance.services.runtime_connection_service import RuntimeConnectionService

    def allowed_runtime_providers(context: TenantContext) -> tuple[str, ...]:
        value = configuration_service.get(
            "model_registry.allowed_runtime_providers",
            SettingContext(context.organization_id, context.project_id),
        )
        return tuple(value)

    return RuntimeConnectionService(
        repository,
        allowed_runtime_providers=allowed_runtime_providers,
    )
