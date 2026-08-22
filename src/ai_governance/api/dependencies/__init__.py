"""
AI Governance Control Plane REST API dependency injection wiring.

Platform-plane modules::
    settings          - ApiSettings, get_api_settings
    providers         - get_provider_registry
    repositories      - raw repository factories
    evaluation        - evaluation service wiring
    experiments       - experiment API wiring
    registries        - prompt / model / dataset registry services
    ontology          - ontology graph and sync wiring
    decisions         - governance decision wiring
    jobs              - job API wiring
    audit             - Studio audit read service
    dashboard         - dashboard read service
    policies          - policy administration service
    mcp               - MCP audit log
    governance_insights - Phase 3 insights and reports
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
from ai_governance.api.dependencies.settings import (
    ApiSettings,
    get_api_settings,
)

__all__ = [
    # Settings
    "ApiSettings",
    "get_api_settings",
    # Audit
    "get_audit_read_service",
    # Authentication
    "get_authenticated_principal",
    # Dashboard
    "get_dashboard_read_service",
    "get_dataset_registry_service",
    "get_dataset_repository",
    # Decisions
    "get_decision_evidence_builder",
    "get_drift_explanation_service",
    "get_evaluation_api_service",
    "get_evaluation_history_service",
    # Repositories
    "get_evaluation_repository",
    "get_evaluation_run_repository",
    # Evaluation
    "get_evaluation_service",
    # Jobs
    "get_event_publisher",
    "get_execution_investigation_service",
    # Experiments
    "get_experiment_api_service",
    "get_experiment_candidate_repository",
    # Governance insights
    "get_experiment_insight_service",
    "get_experiment_repository",
    "get_governance_api_service",
    "get_governance_decision_application_service",
    "get_governance_decision_repository",
    "get_governance_policy_provider",
    "get_governance_reasoning_engine",
    "get_governance_report_service",
    "get_job_api_service",
    "get_job_repository",
    "get_leaderboard_repository",
    # MCP audit
    "get_mcp_audit_log",
    "get_mcp_invocation_audit_log",
    "get_model_registry_service",
    "get_model_repository",
    "get_ontology_graph_query_repository",
    # Ontology
    "get_ontology_graph_query_service",
    "get_ontology_graph_repository",
    "get_ontology_sync_event_publisher",
    "get_ontology_sync_event_repository",
    "get_ontology_sync_event_service",
    "get_policy_administration_repository",
    # Policies
    "get_policy_administration_service",
    "get_prompt_registry_service",
    "get_prompt_repository",
    # Providers
    "get_provider_registry",
    # Registries
    "get_provider_registry_service",
    "get_replay_application_service",
    "get_replay_audit_service",
    "get_replay_execution_catalog",
    "get_replay_repository",
    "get_replay_result_repository",
    "get_replay_source_resolver",
]

# -- Providers ---------------------------------------------------------------
# -- Audit -------------------------------------------------------------------
from ai_governance.api.dependencies.audit import get_audit_read_service

# -- Authentication ----------------------------------------------------------
from ai_governance.api.dependencies.authentication import (
    get_authenticated_principal,
)

# -- Dashboard ---------------------------------------------------------------
from ai_governance.api.dependencies.dashboard import get_dashboard_read_service

# -- Decisions ---------------------------------------------------------------
from ai_governance.api.dependencies.decisions import (
    get_decision_evidence_builder,
    get_governance_decision_application_service,
    get_governance_policy_provider,
    get_governance_reasoning_engine,
)

# -- Evaluation --------------------------------------------------------------
from ai_governance.api.dependencies.evaluation import (
    get_evaluation_api_service,
    get_evaluation_history_service,
    get_evaluation_service,
)

# -- Jobs --------------------------------------------------------------------
from ai_governance.api.dependencies.events import get_event_publisher

# -- Experiments -------------------------------------------------------------
from ai_governance.api.dependencies.experiments import get_experiment_api_service

# -- Governance insights -----------------------------------------------------
from ai_governance.api.dependencies.governance_insights import (
    get_drift_explanation_service,
    get_execution_investigation_service,
    get_experiment_insight_service,
    get_governance_api_service,
    get_governance_report_service,
)
from ai_governance.api.dependencies.jobs import get_job_api_service

# -- MCP audit ---------------------------------------------------------------
from ai_governance.api.dependencies.mcp import (
    get_mcp_audit_log,
    get_mcp_invocation_audit_log,
)

# -- Ontology ----------------------------------------------------------------
from ai_governance.api.dependencies.ontology import (
    get_ontology_graph_query_service,
    get_ontology_sync_event_publisher,
    get_ontology_sync_event_service,
)

# -- Policies ----------------------------------------------------------------
from ai_governance.api.dependencies.policies import get_policy_administration_service
from ai_governance.api.dependencies.providers import get_provider_registry

# -- Registries --------------------------------------------------------------
from ai_governance.api.dependencies.registries import (
    get_dataset_registry_service,
    get_model_registry_service,
    get_prompt_registry_service,
    get_provider_registry_service,
)
from ai_governance.api.dependencies.replay import (
    get_replay_application_service,
    get_replay_audit_service,
    get_replay_execution_catalog,
    get_replay_source_resolver,
)

# -- Repositories ------------------------------------------------------------
from ai_governance.api.dependencies.repositories import (
    get_dataset_repository,
    get_evaluation_repository,
    get_evaluation_run_repository,
    get_experiment_candidate_repository,
    get_experiment_repository,
    get_governance_decision_repository,
    get_job_repository,
    get_leaderboard_repository,
    get_model_repository,
    get_ontology_graph_query_repository,
    get_ontology_graph_repository,
    get_ontology_sync_event_repository,
    get_policy_administration_repository,
    get_prompt_repository,
    get_replay_repository,
    get_replay_result_repository,
)
