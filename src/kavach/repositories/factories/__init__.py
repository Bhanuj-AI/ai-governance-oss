"""
Repository factories for Kavach.

Each factory selects the concrete repository implementation based on
runtime configuration (``KAVACH_*_REPOSITORY`` environment variables).
"""

from __future__ import annotations

from kavach.repositories.factories.evaluation_repository_factory import (
    EvaluationRepositoryFactory,
)
from kavach.repositories.factories.experiment_repository_factory import (
    ExperimentRepositoryFactory,
)
from kavach.repositories.factories.experiment_candidate_repository_factory import (
    ExperimentCandidateRepositoryFactory,
)
from kavach.repositories.factories.evaluation_run_repository_factory import (
    EvaluationRunRepositoryFactory,
)
from kavach.repositories.factories.leaderboard_repository_factory import (
    LeaderboardRepositoryFactory,
)
from kavach.repositories.factories.prompt_repository_factory import (
    PromptRepositoryFactory,
)
from kavach.repositories.factories.model_repository_factory import (
    ModelRepositoryFactory,
)
from kavach.repositories.factories.dataset_repository_factory import (
    DatasetRepositoryFactory,
)
from kavach.repositories.factories.job_repository_factory import (
    JobRepositoryFactory,
)
from kavach.repositories.factories.governance_decision_repository_factory import (
    GovernanceDecisionRepositoryFactory,
)
from kavach.repositories.factories.ontology_sync_event_repository_factory import (
    OntologySyncEventRepositoryFactory,
)
from kavach.repositories.factories.ontology_graph_repository_factory import (
    OntologyGraphRepositoryFactory,
)
from kavach.repositories.factories.policy_repository_factory import (
    PolicyRepositoryFactory,
)
from kavach.repositories.factories.replay_repository_factory import (
    ReplayRepositoryFactory,
)
from kavach.repositories.factories.replay_result_repository_factory import (
    ReplayResultRepositoryFactory,
)
from kavach.repositories.factories.replay_execution_store_factory import (
    ReplayExecutionStoreFactory,
)

__all__ = [
    "DatasetRepositoryFactory",
    "EvaluationRepositoryFactory",
    "EvaluationRunRepositoryFactory",
    "ExperimentCandidateRepositoryFactory",
    "ExperimentRepositoryFactory",
    "GovernanceDecisionRepositoryFactory",
    "JobRepositoryFactory",
    "LeaderboardRepositoryFactory",
    "ModelRepositoryFactory",
    "OntologyGraphRepositoryFactory",
    "OntologySyncEventRepositoryFactory",
    "PromptRepositoryFactory",
    "PolicyRepositoryFactory",
    "ReplayRepositoryFactory",
    "ReplayExecutionStoreFactory",
    "ReplayResultRepositoryFactory",
]
