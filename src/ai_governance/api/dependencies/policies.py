"""
Policy administration service wiring for the AI Governance Control Plane platform.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends

from ai_governance.api.dependencies.repositories import (
    get_policy_administration_repository,
)


def get_policy_administration_service(
    policy_repository: Any = Depends(get_policy_administration_repository),
) -> Any:
    """
    Create the Studio policy administration service.
    """

    from ai_governance.services.policies import PolicyAdministrationService

    return PolicyAdministrationService(policy_repository)
