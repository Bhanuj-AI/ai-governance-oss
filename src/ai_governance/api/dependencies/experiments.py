"""
Experiment wiring for the AI Governance Control Plane platform.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends

from ai_governance.api.dependencies.agent_execution import get_agent_execution_service
from ai_governance.api.dependencies.events import get_event_publisher
from ai_governance.api.dependencies.ontology import get_ontology_sync_event_publisher
from ai_governance.api.dependencies.provider_installations import (
    get_provider_installation_service,
)
from ai_governance.api.dependencies.providers import get_provider_registry
from ai_governance.api.dependencies.replay import get_replay_source_resolver
from ai_governance.api.dependencies.repositories import (
    get_dataset_repository,
    get_evaluation_repository,
    get_evaluation_run_repository,
    get_experiment_candidate_repository,
    get_experiment_repository,
    get_leaderboard_repository,
    get_model_repository,
    get_prompt_repository,
)
from ai_governance.api.dependencies.runtime_connections import (
    get_runtime_connection_service,
)


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
    runtime_connection_service: Any = Depends(get_runtime_connection_service),
    execution_store: Any = Depends(get_replay_source_resolver),
    ontology_event_publisher: Any = Depends(get_ontology_sync_event_publisher),
    event_publisher: Any = Depends(get_event_publisher),
    agent_execution_service: Any = Depends(get_agent_execution_service),
) -> Any:
    """
    Create the REST experiment facade through dependency injection.
    """

    from ai_governance.datasets import dataset_object_store_from_environment
    from ai_governance.services.candidate_execution_runtime import (
        AnthropicModelRuntimeAdapter,
        CandidateExecutionRuntime,
        ModelRuntimeAdapterRegistry,
        OpenAIModelRuntimeAdapter,
    )
    from ai_governance.services.dataset_item_reader import S3DatasetItemReader
    from ai_governance.services.experiment_api_service import ExperimentApiService

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
        runtime_connection_service=runtime_connection_service,
        execution_store=execution_store,
        candidate_execution_runtime=CandidateExecutionRuntime(
            prompt_repository=prompt_repository,
            model_repository=model_repository,
            dataset_repository=dataset_repository,
            runtime_connection_service=runtime_connection_service,
            dataset_item_reader=S3DatasetItemReader(dataset_object_store_from_environment()),
            adapter_registry=ModelRuntimeAdapterRegistry((OpenAIModelRuntimeAdapter(), AnthropicModelRuntimeAdapter())),
            execution_store=execution_store,
            event_publisher=event_publisher,
        ),
        ontology_event_publisher=ontology_event_publisher,
        agent_execution_service=agent_execution_service,
    )
