"""Provider model-catalog discovery service wiring."""

from __future__ import annotations

from typing import Any

from fastapi import Depends

from ai_governance.api.dependencies.runtime_connections import (
    get_runtime_connection_service,
)


def get_model_catalog_discovery_service(
    runtime_connection_service: Any = Depends(get_runtime_connection_service),
) -> Any:
    from ai_governance.services.model_catalog_discovery_service import (
        ModelCatalogDiscoveryService,
    )

    return ModelCatalogDiscoveryService(runtime_connection_service)
