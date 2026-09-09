from dataclasses import replace
from datetime import UTC, datetime
from time import sleep

import pytest

from ai_governance.domain.datasets import Dataset, DatasetStatus
from ai_governance.domain.evaluation_result import (
    EvaluationArtifact,
    EvaluationMetric,
    EvaluationResult,
    EvaluationSampleResult,
)
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
from ai_governance.providers.evaluation_provider import (
    BatchEvaluationResult,
    EvaluationWorkloadEstimate,
)
from ai_governance.providers.provider_capabilities import (
    EvaluationGranularity,
    ProviderCapabilities,
)
from ai_governance.providers.provider_descriptor import ProviderDescriptor
from ai_governance.providers.provider_registry import EvaluationProviderRegistry
from ai_governance.repositories import InMemoryOntologySyncEventRepository
from ai_governance.repositories.in_memory.in_memory_agent_execution_repository import (
    InMemoryAgentExecutionEventRepository,
    InMemoryAgentExecutionRepository,
)
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
from ai_governance.services.agent_execution_service import AgentExecutionService
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


def test_batch_provider_persists_ten_child_results_from_one_invocation() -> None:
    created_at = datetime(2026, 7, 1, tzinfo=UTC)
    experiment_repository = InMemoryExperimentRepository()
    run_repository = InMemoryEvaluationRunRepository()
    evaluation_repository = InMemoryEvaluationRepository()
    experiment = Experiment(
        experiment_id="experiment-1",
        name="Experiment",
        description="Test experiment",
        owner="owner",
        created_at=created_at,
        status=ExperimentStatus.RUNNING,
        organization_id="org-1",
        project_id="project-1",
    )
    candidate = _candidate(created_at)
    experiment_repository.save(experiment)
    provider = _BatchProvider()
    registry = EvaluationProviderRegistry()
    registry.register(provider)
    service = _service(
        experiment_repository=experiment_repository,
        candidate_repository=InMemoryExperimentCandidateRepository(),
        evaluation_run_repository=run_repository,
    )
    service._provider_registry = registry
    service._evaluation_repository = evaluation_repository
    deadline = _RecordingDeadline()
    service._provider_execution_deadline = deadline
    running_run = EvaluationRun(
        run_id="run-1",
        experiment_id=experiment.experiment_id,
        candidate_id=candidate.candidate_id,
        dataset_version=candidate.dataset_version,
        evaluation_provider="batch",
        evaluation_result_id=None,
        started_at=created_at,
        completed_at=None,
        status=EvaluationRunStatus.RUNNING,
        runner_provenance={"configuration_fingerprint": "sha256:fixed"},
    )
    run_repository.save(running_run)
    batch_candidate = replace(candidate, evaluation_provider="batch")

    completed = service._execute_batch_candidate_run(
        experiment=experiment,
        candidate=batch_candidate,
        running_run=running_run,
        evaluator_config={"tasks": ["package:task"], "timeout_seconds": 30},
        context=TenantContext("org-1", "project-1", "actor", "request"),
    )
    page = service.list_run_evaluations(
        experiment.experiment_id,
        completed.run_id,
        page=1,
        page_size=20,
        context=TenantContext("org-1", "project-1", "actor", "request"),
    )

    assert provider.invocations == 1
    assert deadline.timeouts == [30]
    assert completed.status is EvaluationRunStatus.COMPLETED
    assert run_repository.find_by_id(completed.run_id) == completed
    assert completed.total_item_count == completed.completed_item_count == 10
    assert completed.evaluated_item_count == 10
    assert page.total_items == 10
    assert {item.execution_id for item in page.items} == {
        f"run-1:sample:{index}" for index in range(1, 11)
    }
    aggregate = evaluation_repository.find_by_evaluation_id("run-1:aggregate")
    assert aggregate is not None
    assert {metric.metric_name: metric.metric_value for metric in aggregate.metrics}["pass"] == 1.0
    assert aggregate.artifacts[-1].uri == "memory://run"


def test_batch_provider_deadline_marks_the_run_failed_without_persisting_samples() -> None:
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
    candidate_repository.save(replace(_candidate(created_at), evaluation_provider="slow"))
    provider = _SlowBatchProvider()
    registry = EvaluationProviderRegistry()
    registry.register(provider)
    service = _service(
        experiment_repository=experiment_repository,
        candidate_repository=candidate_repository,
        evaluation_run_repository=run_repository,
        provider_registry=registry,
    )

    runs, leaderboard = service.run_experiment(
        "experiment-1",
        provider_config={"timeout_seconds": 1},
        context=TenantContext("org-1", "project-1", "actor", "request"),
    )

    assert leaderboard is None
    assert provider.invocations == 1
    assert len(runs) == 1
    assert runs[0].status is EvaluationRunStatus.FAILED
    assert runs[0].failure_reason == (
        "Provider execution exceeded the hard worker deadline of 1 seconds."
    )
    assert runs[0].evaluated_item_count == 0
    assert runs[0].runner_provenance["batch_persistence_status"] == "not_persisted"


def test_batch_sample_links_durable_artifact_to_agent_runtime_events() -> None:
    service = _service(experiment_repository=InMemoryExperimentRepository())
    execution_repository = InMemoryAgentExecutionRepository()
    event_repository = InMemoryAgentExecutionEventRepository()
    service._agent_execution_service = AgentExecutionService(
        execution_repository, event_repository
    )
    context = TenantContext("org-1", "project-1", "actor", "request")
    result = EvaluationResult(
        evaluation_id="run-1:sample:1:evaluation",
        execution_id="run-1:sample:1",
        evaluator_type="inspect_ai",
        evaluator_version="1.0",
        metrics=[EvaluationMetric("pass", 1.0), EvaluationMetric("total_tokens", 6.0)],
        metadata={"evaluation_run_id": "run-1", "sample_id": "1", "sample_status": "success"},
        artifacts=[
            EvaluationArtifact(
                "observable_execution_events",
                payload={
                    "schema_version": "1",
                    "events": [
                        {"sequence": 0, "kind": "tool", "tool": "lookup", "arguments_digest": "a" * 64},
                        {"sequence": 1, "kind": "model", "model": "test-model"},
                    ],
                },
                metadata={"durable": True, "artifact_digest": "b" * 64},
            )
        ],
        provider_metadata={"runner_provenance": {"configuration_fingerprint": "fingerprint"}},
        organization_id="org-1",
        project_id="project-1",
    )

    service._record_batch_sample_execution(
        item_result=result,
        provider_name="inspect_ai",
        provider_version="1.0",
        context=context,
    )

    execution = execution_repository.get_by_external_id(
        result.execution_id, "inspect_ai", "org-1", "project-1"
    )
    assert execution is not None
    events = event_repository.list_by_execution(
        execution.execution_id, "org-1", "project-1"
    )
    assert [event.event_type.value for event in events] == [
        "EXECUTION_STARTED", "TOOL_CALL", "MODEL_CALL", "EVALUATION", "EXECUTION_COMPLETED"
    ]
    assert events[1].evidence_references == (
        "evaluation-artifact:run-1:sample:1:evaluation:observable-events",
    )


def test_run_plan_uses_a_batch_provider_workload_estimate() -> None:
    created_at = datetime(2026, 7, 1, tzinfo=UTC)
    experiment_repository = InMemoryExperimentRepository()
    candidate_repository = InMemoryExperimentCandidateRepository()
    dataset_repository = InMemoryDatasetRepository()
    registry = EvaluationProviderRegistry()
    registry.register(_BatchProvider())
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
    candidate_repository.save(
        replace(_candidate(created_at), evaluation_provider="batch")
    )
    dataset_repository.save(
        Dataset(
            dataset_id="dataset",
            name="Dataset",
            version="v1",
            description="Test dataset",
            storage_uri="memory://dataset",
            storage_type="memory",
            schema_version="v1",
            record_count=120,
            checksum="checksum",
            creator="owner",
            created_at=created_at,
            status=DatasetStatus.ACTIVE,
            organization_id="org-1",
            project_id="project-1",
        )
    )
    service = _service(
        experiment_repository=experiment_repository,
        candidate_repository=candidate_repository,
        dataset_repository=dataset_repository,
        provider_registry=registry,
    )

    plan = service.get_run_plan(
        "experiment-1", TenantContext("org-1", "project-1", "actor", "request")
    )

    assert plan.dataset_item_count == 120
    assert plan.runner_invocation_count == 1
    assert plan.expected_sample_result_count == 10
    assert plan.workload_basis == "PROVIDER_DECLARED"


class _BatchProvider:
    def __init__(self) -> None:
        self.invocations = 0

    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            name="batch",
            display_name="Batch",
            version="1.0",
            adapter_version="1.0",
            capabilities=ProviderCapabilities(
                supported_metrics=("pass",),
                evaluation_granularity=EvaluationGranularity.BATCH,
            ),
        )

    def evaluate_batch(self, _request) -> BatchEvaluationResult:
        self.invocations += 1
        return BatchEvaluationResult(
            sample_results=tuple(
                EvaluationSampleResult(
                    sample_id=str(index),
                    metrics=(EvaluationMetric("pass", 1.0),),
                )
                for index in range(1, 11)
            ),
            artifacts=(EvaluationArtifact("evaluation_provider_run_reference", uri="memory://run"),),
        )

    def estimate_workload(self, _provider_config) -> EvaluationWorkloadEstimate:
        return EvaluationWorkloadEstimate(
            runner_invocation_count=1,
            expected_sample_result_count=10,
        )

    @staticmethod
    def execution_timeout_seconds(provider_config) -> int | None:
        value = provider_config.get("timeout_seconds")
        return int(value) if value is not None else None


class _RecordingDeadline:
    def __init__(self) -> None:
        self.timeouts: list[int | None] = []

    def call(self, timeout_seconds: int | None, operation):
        self.timeouts.append(timeout_seconds)
        return operation()


class _SlowBatchProvider(_BatchProvider):
    @property
    def descriptor(self) -> ProviderDescriptor:
        return replace(super().descriptor, name="slow")

    def evaluate_batch(self, _request) -> BatchEvaluationResult:
        self.invocations += 1
        sleep(2)
        return super().evaluate_batch(_request)


def _service(
    *,
    experiment_repository: InMemoryExperimentRepository,
    candidate_repository: InMemoryExperimentCandidateRepository | None = None,
    evaluation_run_repository: InMemoryEvaluationRunRepository | None = None,
    leaderboard_repository: InMemoryLeaderboardRepository | None = None,
    dataset_repository: InMemoryDatasetRepository | None = None,
    provider_registry: EvaluationProviderRegistry | None = None,
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
        dataset_repository=dataset_repository or InMemoryDatasetRepository(),
        provider_registry=provider_registry or EvaluationProviderRegistry(),
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
