"""Dependency wiring for trusted runtime-action delegations."""

from __future__ import annotations

from typing import Any

from fastapi import Depends

from ai_governance.api.dependencies.repositories import (
    get_agent_execution_repository,
    get_policy_administration_repository,
    get_runtime_action_delegation_repository,
)
from ai_governance.services.runtime_action_delegation_service import (
    RuntimeActionDelegationService,
)


def get_runtime_action_delegation_service(
    repository: Any = Depends(get_runtime_action_delegation_repository),
    execution_repositories: Any = Depends(get_agent_execution_repository),
    policy_repository: Any = Depends(get_policy_administration_repository),
) -> RuntimeActionDelegationService:
    return RuntimeActionDelegationService(
        repository=repository,
        execution_repository=execution_repositories.execution,
        policy_repository=policy_repository,
    )
