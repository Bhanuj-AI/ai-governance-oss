"""
Raw repository providers for the Kavach platform.

Each function returns a singleton repository instance via ``@lru_cache``.
Repository construction is delegated to explicit factories that select the
concrete implementation based on runtime configuration (``KAVACH_*_REPOSITORY``
environment variables).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from kavach.repositories.policy_administration_repository import (
    PolicyAdministrationRepository,
)


@lru_cache(maxsize=1)
def get_evaluation_repository() -> Any:
    """
    Create the evaluation repository used by REST request dependencies.
    """

    from kavach.settings import load_settings
    from kavach.repositories.factories import EvaluationRepositoryFactory

    return EvaluationRepositoryFactory(load_settings()).create()


@lru_cache(maxsize=1)
def get_replay_repository() -> Any:
    """Create the tenant-scoped Replay repository used by REST."""

    from kavach.repositories.factories import ReplayRepositoryFactory
    from kavach.settings import load_settings

    return ReplayRepositoryFactory(load_settings()).create()


@lru_cache(maxsize=1)
def get_replay_result_repository() -> Any:
    from kavach.repositories.factories import ReplayResultRepositoryFactory
    from kavach.settings import load_settings

    return ReplayResultRepositoryFactory(load_settings()).create()


@lru_cache(maxsize=1)
def get_experiment_repository() -> Any:
    """
    Create the experiment repository used by REST dependencies.
    """

    from kavach.settings import load_settings
    from kavach.repositories.factories import ExperimentRepositoryFactory

    return ExperimentRepositoryFactory(load_settings()).create()


@lru_cache(maxsize=1)
def get_experiment_candidate_repository() -> Any:
    """
    Create the experiment candidate repository used by REST dependencies.
    """

    from kavach.settings import load_settings
    from kavach.repositories.factories import (
        ExperimentCandidateRepositoryFactory,
    )

    return ExperimentCandidateRepositoryFactory(load_settings()).create()


@lru_cache(maxsize=1)
def get_evaluation_run_repository() -> Any:
    """
    Create the evaluation run repository used by REST dependencies.
    """

    from kavach.settings import load_settings
    from kavach.repositories.factories import EvaluationRunRepositoryFactory

    return EvaluationRunRepositoryFactory(load_settings()).create()


@lru_cache(maxsize=1)
def get_leaderboard_repository() -> Any:
    """
    Create the leaderboard repository used by REST dependencies.
    """

    from kavach.settings import load_settings
    from kavach.repositories.factories import LeaderboardRepositoryFactory

    return LeaderboardRepositoryFactory(load_settings()).create()


@lru_cache(maxsize=1)
def get_prompt_repository() -> Any:
    """
    Create the prompt repository used by REST dependencies.
    """

    from kavach.settings import load_settings
    from kavach.repositories.factories import PromptRepositoryFactory

    return PromptRepositoryFactory(load_settings()).create()


@lru_cache(maxsize=1)
def get_model_repository() -> Any:
    """
    Create the model repository used by REST dependencies.
    """

    from kavach.settings import load_settings
    from kavach.repositories.factories import ModelRepositoryFactory

    return ModelRepositoryFactory(load_settings()).create()


@lru_cache(maxsize=1)
def get_dataset_repository() -> Any:
    """
    Create the dataset repository used by REST dependencies.
    """

    from kavach.settings import load_settings
    from kavach.repositories.factories import DatasetRepositoryFactory

    return DatasetRepositoryFactory(load_settings()).create()


@lru_cache(maxsize=1)
def get_job_repository() -> Any:
    """
    Create the job repository used by REST dependencies.
    """

    from kavach.settings import load_settings
    from kavach.repositories.factories import JobRepositoryFactory

    return JobRepositoryFactory(load_settings()).create()


@lru_cache(maxsize=1)
def get_governance_decision_repository() -> Any:
    """
    Create the governance decision repository used by REST dependencies.

    This repository requires an ontology event publisher as a runtime
    collaborator.  The publisher is resolved via the ontology dependency
    module and passed explicitly to the factory.
    """

    from kavach.api.dependencies.ontology import get_ontology_sync_event_publisher
    from kavach.settings import load_settings
    from kavach.repositories.factories import (
        GovernanceDecisionRepositoryFactory,
    )

    return GovernanceDecisionRepositoryFactory(load_settings()).create(
        ontology_event_publisher=get_ontology_sync_event_publisher(),
    )


@lru_cache(maxsize=1)
def get_policy_administration_repository() -> PolicyAdministrationRepository:
    """
    Returns the singleton policy administration repository for the current process.

    Uses the existing factory pattern (``PolicyRepositoryFactory``) which
    was already config-driven before this refactor.
    """

    from kavach.settings import load_settings
    from kavach.repositories.factories import PolicyRepositoryFactory

    settings = load_settings()

    return PolicyRepositoryFactory(settings).create()


@lru_cache(maxsize=1)
def get_ontology_sync_event_repository() -> Any:
    """
    Create the ontology synchronization event repository used by REST.
    """

    from kavach.settings import load_settings
    from kavach.repositories.factories import (
        OntologySyncEventRepositoryFactory,
    )

    return OntologySyncEventRepositoryFactory(load_settings()).create()


@lru_cache(maxsize=1)
def get_ontology_graph_repository() -> Any:
    """
    Create the ontology graph repository used by read APIs.
    """

    from kavach.settings import load_settings
    from kavach.repositories.factories import OntologyGraphRepositoryFactory

    return OntologyGraphRepositoryFactory(load_settings()).create()


@lru_cache(maxsize=1)
def get_ontology_graph_query_repository() -> Any:
    """
    Create the read-only ontology graph query repository.
    """

    from kavach.settings import load_settings

    if load_settings().ontology_repository == "neo4j":
        from kavach.ontology.neo4j_repository import Neo4jOntologyGraphQueryRepository

        return Neo4jOntologyGraphQueryRepository(get_ontology_graph_repository())

    from kavach.ontology import InMemoryOntologyGraphQueryRepository

    # Lazy import to avoid circular dependency with get_ontology_graph_repository
    return InMemoryOntologyGraphQueryRepository(
        get_ontology_graph_repository(),
    )
