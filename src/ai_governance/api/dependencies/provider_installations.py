"""Provider-installation service wiring."""

from __future__ import annotations

from typing import Any

from fastapi import Depends

from ai_governance.api.dependencies.providers import get_provider_registry
from ai_governance.api.dependencies.settings_control import (
    get_provider_installation_repository,
)


def get_provider_installation_service(
    repository: Any = Depends(get_provider_installation_repository),
    provider_registry: Any = Depends(get_provider_registry),
) -> Any:
    from ai_governance.services.provider_installation_service import (
        ProviderInstallationService,
    )

    return ProviderInstallationService(repository, provider_registry)
