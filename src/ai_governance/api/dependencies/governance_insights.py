"""
Governance insights and report wiring for the AI Governance Control Plane platform.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends

from ai_governance.api.dependencies.mcp import get_mcp_audit_log
from ai_governance.api.dependencies.repositories import (
    get_evaluation_repository,
    get_evaluation_run_repository,
    get_experiment_candidate_repository,
    get_experiment_repository,
    get_job_repository,
    get_leaderboard_repository,
)


def get_experiment_insight_service(
    experiment_repository: Any = Depends(get_experiment_repository),
    candidate_repository: Any = Depends(get_experiment_candidate_repository),
    evaluation_run_repository: Any = Depends(get_evaluation_run_repository),
    evaluation_repository: Any = Depends(get_evaluation_repository),
    leaderboard_repository: Any = Depends(get_leaderboard_repository),
) -> Any:
    """
    Create the Phase 3 experiment insight service.
    """

    from ai_governance.services.governance_insights import ExperimentInsightService

    return ExperimentInsightService(
        experiment_repository=experiment_repository,
        candidate_repository=candidate_repository,
        evaluation_run_repository=evaluation_run_repository,
        evaluation_repository=evaluation_repository,
        leaderboard_repository=leaderboard_repository,
    )


def get_execution_investigation_service(
    audit_log: Any = Depends(get_mcp_audit_log),
    job_repository: Any = Depends(get_job_repository),
    evaluation_repository: Any = Depends(get_evaluation_repository),
) -> Any:
    """
    Create the Phase 3 execution investigation service.
    """

    from ai_governance.services.governance_insights import (
        ExecutionInvestigationService,
    )

    return ExecutionInvestigationService(
        audit_log=audit_log,
        job_repository=job_repository,
        evaluation_repository=evaluation_repository,
    )


def get_drift_explanation_service(
    evaluation_repository: Any = Depends(get_evaluation_repository),
) -> Any:
    """
    Create the Phase 3 drift explanation service.
    """

    from ai_governance.services.governance_insights import DriftExplanationService

    return DriftExplanationService(evaluation_repository)


def get_governance_report_service(
    experiment_insight_service: Any = Depends(get_experiment_insight_service),
    execution_investigation_service: Any = Depends(get_execution_investigation_service),
    drift_explanation_service: Any = Depends(get_drift_explanation_service),
    evaluation_repository: Any = Depends(get_evaluation_repository),
    audit_log: Any = Depends(get_mcp_audit_log),
) -> Any:
    """
    Create the Phase 3 governance report service.
    """

    from ai_governance.services.governance_insights import GovernanceReportService

    return GovernanceReportService(
        experiment_insights=experiment_insight_service,
        investigations=execution_investigation_service,
        drift_explanations=drift_explanation_service,
        evaluation_repository=evaluation_repository,
        audit_log=audit_log,
    )


def get_governance_api_service(
    evaluation_repository: Any = Depends(get_evaluation_repository),
) -> Any:
    """
    Create the REST governance facade through dependency injection.
    """

    from ai_governance.services.governance_api_service import GovernanceApiService

    return GovernanceApiService(evaluation_repository)
