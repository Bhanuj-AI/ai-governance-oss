from datetime import UTC, datetime

import pytest

from ai_governance.domain.experiments import (
    EvaluationRun,
    EvaluationRunStatus,
    Experiment,
    ExperimentCandidate,
    ExperimentStatus,
    Leaderboard,
    LeaderboardEntry,
)
from ai_governance.ontology.synchronization import OntologySyncEventPublisher
from ai_governance.providers.provider_registry import EvaluationProviderRegistry
from ai_governance.repositories import InMemoryOntologySyncEventRepository
from ai_governance.repositories.in_memory_dataset_repository import (
    InMemoryDatasetRepository,
)
from ai_governance.repositories.in_memory_evaluation_repository import (
    InMemoryEvaluationRepository,
)
from ai_governance.repositories.in_memory_evaluation_run_repository import (
    InMemoryEvaluationRunRepository,
)
from ai_governance.repositories.in_memory_experiment_candidate_repository import (
    InMemoryExperimentCandidateRepository,
)
from ai_governance.repositories.in_memory_experiment_repository import (
    InMemoryExperimentRepository,
)
from ai_governance.repositories.in_memory_leaderboard_repository import (
    InMemoryLeaderboardRepository,
)
from ai_governance.repositories.in_memory_model_repository import (
    InMemoryModelRepository,
)
from ai_governance.repositories.in_memory_prompt_repository import (
    InMemoryPromptRepository,
)
from ai_governance.services.experiment_api_service import ExperimentApiService
from ai_governance.services.experiments import ExperimentNotFoundError
from ai_governance.tenancy.domain import TenantContext


def test_experiment_api_service_lists_candidates_and_runs_with_tenant_guard() -> None:
    created_at = datetime(2026, 7, 1, tzinfo=UTC)
    experiment_repository = InMemoryExperimentRepository()
    candidate_repository = InMemoryExperimentCandidateRepository()
    run_repository = InMemoryEvaluationRunRepository()
    experiment_repository.save(
        Experiment(
            experiment_id="experiment-1",
            name="Experiment",
            description="Test experiment",
            owner="owner",
            created_at=created_at,
            status=ExperimentStatus.DRAFT,
            organization_id="org-1",
            project_id="project-1",
        )
    )
    candidate_repository.save(_candidate(created_at))
    run_repository.save(
        EvaluationRun(
            run_id="run-1",
            experiment_id="experiment-1",
            candidate_id="candidate-1",
            dataset_version="v1",
            evaluation_provider="mock",
            evaluation_result_id=None,
            started_at=created_at,
            completed_at=created_at,
            status=EvaluationRunStatus.FAILED,
        )
    )
    service = _service(
        experiment_repository=experiment_repository,
        candidate_repository=candidate_repository,
        evaluation_run_repository=run_repository,
    )
    context = TenantContext("org-1", "project-1", "actor", "request")

    assert service.list_candidates("experiment-1", context)[0].candidate_id == (
        "candidate-1"
    )
    assert service.list_evaluation_runs("experiment-1", context)[0].run_id == "run-1"

    with pytest.raises(ExperimentNotFoundError):
        service.list_candidates(
            "experiment-1",
            TenantContext("other-org", "project-1", "actor", "request"),
        )


def test_list_evaluation_runs_reconciles_a_stale_run_after_cancellation() -> None:
    created_at = datetime(2026, 7, 1, tzinfo=UTC)
    experiment_repository = InMemoryExperimentRepository()
    run_repository = InMemoryEvaluationRunRepository()
    experiment_repository.save(
        Experiment(
            experiment_id="experiment-1",
            name="Experiment",
            description="Test experiment",
            owner="owner",
            created_at=created_at,
            status=ExperimentStatus.CANCELLED,
            organization_id="org-1",
            project_id="project-1",
        )
    )
    run_repository.save(
        EvaluationRun(
            run_id="run-1",
            experiment_id="experiment-1",
            candidate_id="candidate-1",
            dataset_version="v1",
            evaluation_provider="mock",
            evaluation_result_id=None,
            started_at=created_at,
            completed_at=None,
            status=EvaluationRunStatus.RUNNING,
        )
    )
    service = _service(
        experiment_repository=experiment_repository,
        evaluation_run_repository=run_repository,
    )
    context = TenantContext("org-1", "project-1", "actor", "request")

    runs = service.list_evaluation_runs("experiment-1", context)

    assert runs[0].status == EvaluationRunStatus.CANCELLED
    assert runs[0].failure_reason == "Experiment cancellation requested."
    assert run_repository.find_by_id("run-1") == runs[0]


def test_get_leaderboard_publishes_a_targeted_ontology_projection_event() -> None:
    created_at = datetime(2026, 7, 1, tzinfo=UTC)
    experiment_repository = InMemoryExperimentRepository()
    leaderboard_repository = InMemoryLeaderboardRepository()
    event_repository = InMemoryOntologySyncEventRepository()
    experiment_repository.save(
        Experiment(
            experiment_id="experiment-1",
            name="Experiment",
            description="Test experiment",
            owner="owner",
            created_at=created_at,
            status=ExperimentStatus.COMPLETED,
            organization_id="org-1",
            project_id="project-1",
        )
    )
    leaderboard_repository.save(
        Leaderboard(
            leaderboard_id="leaderboard-1",
            experiment_id="experiment-1",
            ranking_strategy="overall_score",
            generated_at=created_at,
            entries=(
                LeaderboardEntry(
                    rank=1,
                    candidate_id="candidate-1",
                    overall_score=0.9,
                    metrics={"quality": 0.9},
                    cost=0.01,
                    latency=0.2,
                    reason="Ranked by average evaluation metric score.",
                ),
            ),
        )
    )
    service = _service(
        experiment_repository=experiment_repository,
        leaderboard_repository=leaderboard_repository,
        ontology_event_publisher=OntologySyncEventPublisher(event_repository),
    )
    context = TenantContext("org-1", "project-1", "actor", "request")

    leaderboard = service.get_leaderboard("experiment-1", context)
    event = event_repository.list_events()[0]

    assert leaderboard.leaderboard_id == "leaderboard-1"
    assert event.entity_type == "Leaderboard"
    assert event.entity_id == "leaderboard-1"
    assert event.scope_identifier == "leaderboard_repository"


def _service(
    *,
    experiment_repository: InMemoryExperimentRepository,
    candidate_repository: InMemoryExperimentCandidateRepository | None = None,
    evaluation_run_repository: InMemoryEvaluationRunRepository | None = None,
    leaderboard_repository: InMemoryLeaderboardRepository | None = None,
    ontology_event_publisher=None,
) -> ExperimentApiService:
    return ExperimentApiService(
        experiment_repository=experiment_repository,
        candidate_repository=(
            candidate_repository or InMemoryExperimentCandidateRepository()
        ),
        evaluation_run_repository=(
            evaluation_run_repository or InMemoryEvaluationRunRepository()
        ),
        evaluation_repository=InMemoryEvaluationRepository(),
        leaderboard_repository=leaderboard_repository or InMemoryLeaderboardRepository(),
        prompt_repository=InMemoryPromptRepository(),
        model_repository=InMemoryModelRepository(),
        dataset_repository=InMemoryDatasetRepository(),
        provider_registry=EvaluationProviderRegistry(),
        ontology_event_publisher=ontology_event_publisher,
    )


def _candidate(created_at: datetime) -> ExperimentCandidate:
    return ExperimentCandidate(
        candidate_id="candidate-1",
        experiment_id="experiment-1",
        name="Candidate",
        prompt_id="prompt",
        prompt_version="v1",
        model_id="model",
        model_version="v1",
        dataset_id="dataset",
        dataset_version="v1",
        evaluation_provider="mock",
        temperature=0.0,
        top_p=1.0,
        max_tokens=128,
        metadata={},
        created_at=created_at,
    )
