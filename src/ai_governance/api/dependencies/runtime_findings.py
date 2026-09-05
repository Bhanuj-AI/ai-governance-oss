"""Dependency providers for runtime findings endpoints.

Repository construction is isolated here so router modules never import
from ``ai_governance.repositories``.
"""

from __future__ import annotations

from functools import lru_cache

from ai_governance.services.runtime_finding_service import (
    RuntimeFindingService,
)


@lru_cache(maxsize=1)
def get_runtime_finding_service() -> RuntimeFindingService:
    """Build and return the runtime finding service.

    Repository construction is delegated to this provider so router
    modules remain repository-free. The configuration service is wired
    in so detector thresholds and auto-resolution behaviour are
    externally tunable through the settings control plane.
    """
    from ai_governance.api.dependencies.agent_execution import (
        get_agent_execution_service,
    )
    from ai_governance.api.dependencies.runtime_finding_repo import (
        get_runtime_finding_repository,
    )
    from ai_governance.api.dependencies.settings_control import (
        get_settings_repository,
    )
    from ai_governance.domain.runtime_findings.detectors import ALL_DETECTORS
    from ai_governance.services.runtime_aggregation_service import (
        RuntimeAggregationService,
    )
    from ai_governance.settings_control import ConfigurationService

    finding_repo = get_runtime_finding_repository()

    exec_service = get_agent_execution_service()
    aggregation_service = RuntimeAggregationService(
        exec_service._execution_repo,
        exec_service._event_repo,
    )

    # Wire the settings control plane so thresholds are externally tunable.
    config_service = ConfigurationService(get_settings_repository())
    detectors = tuple(cls(config_service) for cls in ALL_DETECTORS)

    return RuntimeFindingService(
        aggregation_service,
        finding_repo,
        detectors,
        configuration_service=config_service,
    )
