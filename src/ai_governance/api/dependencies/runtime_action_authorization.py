"""Dependency wiring for runtime action authorization."""

from __future__ import annotations

from typing import Any

from fastapi import Depends

from ai_governance.api.dependencies.repositories import (
    get_agent_execution_repository,
    get_policy_administration_repository,
    get_runtime_action_delegation_repository,
)
from ai_governance.services.runtime_action_authorization_service import (
    RuntimeActionAuthorizationService,
)


def get_runtime_action_authorization_service(
    policy_repository: Any = Depends(get_policy_administration_repository),
    execution_repositories: Any = Depends(get_agent_execution_repository),
    delegation_repository: Any = Depends(get_runtime_action_delegation_repository),
) -> RuntimeActionAuthorizationService:
    """Compose policy and execution repositories through their factories."""

    return RuntimeActionAuthorizationService(
        policy_repository=policy_repository,
        execution_repository=execution_repositories.execution,
        event_repository=execution_repositories.event,
        delegation_repository=delegation_repository,
    )
