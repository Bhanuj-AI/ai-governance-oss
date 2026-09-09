"""
Repository factories for AI Governance Control Plane.

Each factory selects the concrete repository implementation based on
runtime configuration (``AI_GOVERNANCE_*_REPOSITORY`` environment variables).
"""

from __future__ import annotations

from ai_governance.repositories.factories.agent_execution_repository_factory import (
    AgentExecutionRepositoryFactory,
)
from ai_governance.repositories.factories.causal_audit_repository_factory import (
    CausalAuditRepositoryFactory,
)
from ai_governance.repositories.factories.dataset_repository_factory import (
    DatasetRepositoryFactory,
)
from ai_governance.repositories.factories.evaluation_repository_factory import (
    EvaluationRepositoryFactory,
)
from ai_governance.repositories.factories.evaluation_run_repository_factory import (
    EvaluationRunRepositoryFactory,
)
from ai_governance.repositories.factories.evidence_fidelity_repository_factory import (
    EvidenceFidelityComparisonRepositoryFactory,
)
from ai_governance.repositories.factories.evidence_intervention_policy_repository_factory import (
    EvidenceInterventionPolicyRepositoryFactory,
)
from ai_governance.repositories.factories.experiment_candidate_repository_factory import (
    ExperimentCandidateRepositoryFactory,
)
from ai_governance.repositories.factories.experiment_repository_factory import (
    ExperimentRepositoryFactory,
)
from ai_governance.repositories.factories.governance_decision_repository_factory import (
    GovernanceDecisionRepositoryFactory,
)
from ai_governance.repositories.factories.job_repository_factory import (
    JobRepositoryFactory,
)
from ai_governance.repositories.factories.leaderboard_repository_factory import (
    LeaderboardRepositoryFactory,
)
from ai_governance.repositories.factories.model_repository_factory import (
    ModelRepositoryFactory,
)
from ai_governance.repositories.factories.ontology_graph_repository_factory import (
    OntologyGraphRepositoryFactory,
)
from ai_governance.repositories.factories.ontology_sync_event_repository_factory import (
    OntologySyncEventRepositoryFactory,
)
from ai_governance.repositories.factories.policy_repository_factory import (
    PolicyRepositoryFactory,
)
from ai_governance.repositories.factories.prompt_repository_factory import (
    PromptRepositoryFactory,
)
from ai_governance.repositories.factories.replay_execution_store_factory import (
    ReplayExecutionStoreFactory,
)
from ai_governance.repositories.factories.replay_repository_factory import (
    ReplayRepositoryFactory,
)
from ai_governance.repositories.factories.replay_result_repository_factory import (
    ReplayResultRepositoryFactory,
)
from ai_governance.repositories.factories.runtime_finding_repository_factory import (
    RuntimeFindingRepositoryFactory,
)
from ai_governance.repositories.factories.runtime_projection_repository_factory import (
    RuntimeProjectionRepositoryFactory,
)

__all__ = [
    "AgentExecutionRepositoryFactory",
    "CausalAuditRepositoryFactory",
    "DatasetRepositoryFactory",
    "EvaluationRepositoryFactory",
    "EvaluationRunRepositoryFactory",
    "EvidenceFidelityComparisonRepositoryFactory",
    "EvidenceInterventionPolicyRepositoryFactory",
    "ExperimentCandidateRepositoryFactory",
    "ExperimentRepositoryFactory",
    "GovernanceDecisionRepositoryFactory",
    "JobRepositoryFactory",
    "LeaderboardRepositoryFactory",
    "ModelRepositoryFactory",
    "OntologyGraphRepositoryFactory",
    "OntologySyncEventRepositoryFactory",
    "PolicyRepositoryFactory",
    "PromptRepositoryFactory",
    "ReplayExecutionStoreFactory",
    "ReplayRepositoryFactory",
    "ReplayResultRepositoryFactory",
    "RuntimeFindingRepositoryFactory",
    "RuntimeProjectionRepositoryFactory",
]
