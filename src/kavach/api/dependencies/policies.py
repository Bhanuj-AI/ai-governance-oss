"""
Policy administration service wiring for the Kavach platform.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends

from kavach.api.dependencies.repositories import (
    get_policy_administration_repository,
)


def get_policy_administration_service(
    policy_repository: Any = Depends(get_policy_administration_repository),
) -> Any:
    """
    Create the Studio policy administration service.
    """

    from kavach.services.policies import PolicyAdministrationService

    return PolicyAdministrationService(policy_repository)
