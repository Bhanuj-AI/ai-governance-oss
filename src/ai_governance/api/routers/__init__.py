from ai_governance.api.routers.audit import router as audit_router
from ai_governance.api.routers.datasets import router as datasets_router
from ai_governance.api.routers.dashboard import router as dashboard_router
from ai_governance.api.routers.decisions import router as decisions_router
from ai_governance.api.routers.evaluations import router as evaluations_router
from ai_governance.api.routers.experiments import router as experiments_router
from ai_governance.api.routers.extensions import router as extensions_router
from ai_governance.api.routers.governance import router as governance_router
from ai_governance.api.routers.health import router as health_router
from ai_governance.api.routers.investigations import router as investigations_router
from ai_governance.api.routers.jobs import router as jobs_router
from ai_governance.api.routers.local_demo import router as local_demo_router
from ai_governance.api.routers.mcp_audit import router as mcp_audit_router
from ai_governance.api.routers.metadata import router as metadata_router
from ai_governance.api.routers.models import router as models_router
from ai_governance.api.routers.ontology_graph import router as ontology_graph_router
from ai_governance.api.routers.ontology_sync import router as ontology_sync_router
from ai_governance.api.routers.policies import router as policies_router
from ai_governance.api.routers.prompts import router as prompts_router
from ai_governance.api.routers.providers import router as providers_router
from ai_governance.api.routers.provider_installations import router as provider_installations_router
from ai_governance.api.routers.reports import router as reports_router
from ai_governance.api.routers.replays import router as replays_router
from ai_governance.api.routers.replay_executions import router as replay_executions_router
from ai_governance.api.routers.tenancy import router as tenancy_router
from ai_governance.api.routers.settings_control import router as settings_router

__all__ = [
    "audit_router",
    "datasets_router",
    "dashboard_router",
    "decisions_router",
    "evaluations_router",
    "experiments_router",
    "extensions_router",
    "governance_router",
    "health_router",
    "investigations_router",
    "jobs_router",
    "local_demo_router",
    "mcp_audit_router",
    "metadata_router",
    "models_router",
    "ontology_graph_router",
    "ontology_sync_router",
    "policies_router",
    "prompts_router",
    "providers_router",
    "provider_installations_router",
    "reports_router",
    "replays_router",
    "replay_executions_router",
    "tenancy_router",
    "settings_router",
]
