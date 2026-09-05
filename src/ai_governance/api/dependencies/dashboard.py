"""
Dashboard wiring for the AI Governance Control Plane platform.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends

from ai_governance.api.dependencies.providers import get_provider_registry
from ai_governance.api.dependencies.repositories import (
    get_agent_execution_repository,
    get_causal_audit_repository,
    get_governance_decision_repository,
    get_job_repository,
    get_ontology_graph_repository,
    get_ontology_sync_event_repository,
    get_replay_repository,
)


def get_dashboard_read_service(
    decision_repository: Any = Depends(get_governance_decision_repository),
    job_repository: Any = Depends(get_job_repository),
    ontology_sync_event_repository: Any = Depends(get_ontology_sync_event_repository),
    ontology_graph_repository: Any = Depends(get_ontology_graph_repository),
    replay_repository: Any = Depends(get_replay_repository),
    causal_audit_repository: Any = Depends(get_causal_audit_repository),
    agent_execution_repositories: Any = Depends(get_agent_execution_repository),
    provider_registry: Any = Depends(get_provider_registry),
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
        replay_repository=replay_repository,
        causal_audit_repository=causal_audit_repository,
        # FastAPI resolves the factory bundle for requests.  A direct call to
        # this provider (as used by dependency-wiring smoke tests) receives
        # FastAPI's ``Depends`` marker instead, so leave runtime execution
        # health unavailable rather than dereferencing that marker.
        agent_execution_repository=getattr(
            agent_execution_repositories, "execution", None
        ),
        provider_registry=provider_registry,
    )
