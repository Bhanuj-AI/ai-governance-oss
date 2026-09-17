"""
Policy administration service wiring for the AI Governance Control Plane platform.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends

from ai_governance.api.dependencies.ontology import get_ontology_sync_event_publisher
from ai_governance.api.dependencies.repositories import (
    get_policy_administration_repository,
)


def get_policy_administration_service(
    policy_repository: Any = Depends(get_policy_administration_repository),
    ontology_event_publisher: Any = Depends(get_ontology_sync_event_publisher),
) -> Any:
    """
    Create the Studio policy administration service.
    """

    from ai_governance.services.policies import PolicyAdministrationService

    return PolicyAdministrationService(
        policy_repository,
        ontology_event_publisher=ontology_event_publisher,
    )
