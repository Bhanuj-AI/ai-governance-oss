"""
Experiment wiring for the Kavach platform.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends

from kavach.api.dependencies.providers import get_provider_registry
from kavach.api.dependencies.repositories import (
    get_dataset_repository,
    get_evaluation_repository,
    get_evaluation_run_repository,
    get_experiment_candidate_repository,
    get_experiment_repository,
    get_leaderboard_repository,
    get_model_repository,
    get_prompt_repository,
)
from kavach.api.dependencies.ontology import get_ontology_sync_event_publisher
from kavach.api.dependencies.provider_installations import get_provider_installation_service


def get_experiment_api_service(
    experiment_repository: Any = Depends(get_experiment_repository),
    candidate_repository: Any = Depends(get_experiment_candidate_repository),
    evaluation_run_repository: Any = Depends(get_evaluation_run_repository),
    evaluation_repository: Any = Depends(get_evaluation_repository),
    leaderboard_repository: Any = Depends(get_leaderboard_repository),
    prompt_repository: Any = Depends(get_prompt_repository),
    model_repository: Any = Depends(get_model_repository),
    dataset_repository: Any = Depends(get_dataset_repository),
    provider_registry: Any = Depends(get_provider_registry),
    provider_installation_service: Any = Depends(get_provider_installation_service),
    ontology_event_publisher: Any = Depends(get_ontology_sync_event_publisher),
) -> Any:
    """
    Create the REST experiment facade through dependency injection.
    """

    from kavach.services.experiment_api_service import ExperimentApiService

    return ExperimentApiService(
        experiment_repository=experiment_repository,
        candidate_repository=candidate_repository,
        evaluation_run_repository=evaluation_run_repository,
        evaluation_repository=evaluation_repository,
        leaderboard_repository=leaderboard_repository,
        prompt_repository=prompt_repository,
        model_repository=model_repository,
        dataset_repository=dataset_repository,
        provider_registry=provider_registry,
        provider_installation_service=provider_installation_service,
        ontology_event_publisher=ontology_event_publisher,
    )
