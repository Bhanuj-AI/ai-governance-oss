"""
Dashboard wiring for the AI Governance Control Plane platform.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends

from ai_governance.api.dependencies.repositories import (
    get_governance_decision_repository,
    get_job_repository,
    get_ontology_graph_repository,
    get_ontology_sync_event_repository,
)


def get_dashboard_read_service(
    decision_repository: Any = Depends(get_governance_decision_repository),
    job_repository: Any = Depends(get_job_repository),
    ontology_sync_event_repository: Any = Depends(get_ontology_sync_event_repository),
    ontology_graph_repository: Any = Depends(get_ontology_graph_repository),
) -> Any:
    """
    Create the Studio dashboard read service.
    """

    from ai_governance.services.dashboard_service import DashboardReadService

    return DashboardReadService(
        decision_repository=decision_repository,
        job_repository=job_repository,
        ontology_sync_event_repository=ontology_sync_event_repository,
        ontology_graph_repository=ontology_graph_repository,
    )
