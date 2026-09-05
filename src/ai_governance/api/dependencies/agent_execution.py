"""Dependency injection for the Agent Execution Trace service."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from ai_governance.services.agent_execution_service import AgentExecutionService


@lru_cache(maxsize=1)
def get_agent_execution_service() -> AgentExecutionService:
    """Create the agent execution service used by REST dependencies."""

    repos = get_agent_execution_repository()
    from ai_governance.api.dependencies.runtime_finding_repo import (
        get_runtime_finding_repository,
    )
    from ai_governance.api.dependencies.settings_control import get_settings_repository
    from ai_governance.settings_control import ConfigurationService
    return AgentExecutionService(
        execution_repository=repos.execution,
        event_repository=repos.event,
        configuration_service=ConfigurationService(get_settings_repository()),
        runtime_finding_repository=get_runtime_finding_repository(),
    )


def get_agent_execution_repository() -> Any:
    """Return the cached agent execution repository pair."""
    from ai_governance.api.dependencies.repositories import (
        get_agent_execution_repository as _get_repo,
    )
    return _get_repo()
