"""
Backward-compatibility tests for the split dependency package.

These tests ensure that every public provider that was previously importable
from ``ai_governance.api.dependencies`` remains importable after the refactor.
"""

from __future__ import annotations


def test_backward_compatible_imports() -> None:
    """Old-style imports from the package root must still work."""

    from ai_governance.api.dependencies import (
        ApiSettings,
        get_api_settings,
        get_audit_read_service,
        get_dashboard_read_service,
        get_dataset_registry_service,
        get_dataset_repository,
        get_decision_evidence_builder,
        get_drift_explanation_service,
        get_evaluation_api_service,
        get_evaluation_history_service,
        get_evaluation_repository,
        get_evaluation_run_repository,
        get_evaluation_service,
        get_execution_investigation_service,
        get_experiment_api_service,
        get_experiment_candidate_repository,
        get_experiment_insight_service,
        get_experiment_repository,
        get_governance_api_service,
        get_governance_decision_application_service,
        get_governance_decision_repository,
        get_governance_policy_provider,
        get_governance_reasoning_engine,
        get_governance_report_service,
        get_job_api_service,
        get_job_repository,
        get_leaderboard_repository,
        get_mcp_audit_log,
        get_model_registry_service,
        get_model_repository,
        get_ontology_graph_query_repository,
        get_ontology_graph_query_service,
        get_ontology_graph_repository,
        get_ontology_sync_event_publisher,
        get_ontology_sync_event_repository,
        get_ontology_sync_event_service,
        get_policy_administration_repository,
        get_policy_administration_service,
        get_prompt_registry_service,
        get_prompt_repository,
        get_provider_registry,
        get_provider_registry_service,
    )

    imported = (
        ApiSettings,
        get_api_settings,
        get_evaluation_repository,
        get_experiment_repository,
        get_experiment_candidate_repository,
        get_evaluation_run_repository,
        get_leaderboard_repository,
        get_prompt_repository,
        get_model_repository,
        get_dataset_repository,
        get_job_repository,
        get_governance_decision_repository,
        get_policy_administration_repository,
        get_ontology_sync_event_repository,
        get_ontology_graph_repository,
        get_ontology_graph_query_repository,
        get_evaluation_service,
        get_evaluation_history_service,
        get_evaluation_api_service,
        get_experiment_api_service,
        get_provider_registry_service,
        get_prompt_registry_service,
        get_model_registry_service,
        get_dataset_registry_service,
        get_ontology_graph_query_service,
        get_ontology_sync_event_publisher,
        get_ontology_sync_event_service,
        get_decision_evidence_builder,
        get_governance_policy_provider,
        get_governance_reasoning_engine,
        get_governance_decision_application_service,
        get_job_api_service,
        get_audit_read_service,
        get_dashboard_read_service,
        get_policy_administration_service,
        get_mcp_audit_log,
        get_experiment_insight_service,
        get_execution_investigation_service,
        get_drift_explanation_service,
        get_governance_report_service,
        get_governance_api_service,
        get_provider_registry,
    )

    assert all(item is not None for item in imported)
    assert callable(get_api_settings)
    assert callable(get_evaluation_repository)
    assert callable(get_experiment_api_service)
    assert callable(get_governance_decision_application_service)
    assert callable(get_audit_read_service)
    assert callable(get_dashboard_read_service)
    assert callable(get_governance_report_service)


def test_plane_specific_imports() -> None:
    """Each plane module must be importable directly."""

    from ai_governance.api.dependencies.audit import get_audit_read_service
    from ai_governance.api.dependencies.dashboard import get_dashboard_read_service
    from ai_governance.api.dependencies.decisions import (
        get_governance_decision_application_service,
    )
    from ai_governance.api.dependencies.evaluation import get_evaluation_api_service
    from ai_governance.api.dependencies.experiments import get_experiment_api_service
    from ai_governance.api.dependencies.governance_insights import (
        get_governance_report_service,
    )
    from ai_governance.api.dependencies.jobs import get_job_api_service
    from ai_governance.api.dependencies.mcp import get_mcp_audit_log
    from ai_governance.api.dependencies.ontology import (
        get_ontology_sync_event_publisher,
    )
    from ai_governance.api.dependencies.policies import (
        get_policy_administration_service,
    )
    from ai_governance.api.dependencies.providers import get_provider_registry
    from ai_governance.api.dependencies.registries import (
        get_dataset_registry_service,
        get_model_registry_service,
        get_prompt_registry_service,
        get_provider_registry_service,
    )
    from ai_governance.api.dependencies.repositories import get_job_repository
    from ai_governance.api.dependencies.settings import get_api_settings

    imported = (
        get_api_settings,
        get_evaluation_api_service,
        get_experiment_api_service,
        get_governance_decision_application_service,
        get_dashboard_read_service,
        get_governance_report_service,
        get_job_repository,
        get_ontology_sync_event_publisher,
        get_mcp_audit_log,
        get_provider_registry,
        get_prompt_registry_service,
        get_model_registry_service,
        get_dataset_registry_service,
        get_provider_registry_service,
        get_job_api_service,
        get_audit_read_service,
        get_policy_administration_service,
    )

    assert all(item is not None for item in imported)
    assert callable(get_api_settings)
    assert callable(get_evaluation_api_service)
    assert callable(get_experiment_api_service)
    assert callable(get_governance_decision_application_service)
    assert callable(get_dashboard_read_service)
    assert callable(get_governance_report_service)
    assert callable(get_job_repository)
    assert callable(get_ontology_sync_event_publisher)
    assert callable(get_mcp_audit_log)
    assert callable(get_provider_registry)
    assert callable(get_prompt_registry_service)
    assert callable(get_model_registry_service)
    assert callable(get_dataset_registry_service)
    assert callable(get_provider_registry_service)
    assert callable(get_job_api_service)
    assert callable(get_audit_read_service)
    assert callable(get_policy_administration_service)
