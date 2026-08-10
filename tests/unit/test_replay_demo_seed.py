from ai_governance.api.demo_seed import (
    seed_demo_replay_source_executions,
    seed_demo_replays,
    seed_demo_runnable_jobs,
)
from dataclasses import replace
from ai_governance.domain.evaluation_result import EvaluationMetric, EvaluationResult
from ai_governance.domain.jobs import JobStatus, JobType
from ai_governance.services.replay_execution_discovery import (
    InMemoryReplayExecutionCatalog,
    InMemoryReplaySourceResolver,
    ReplayExecutionSearchFilters,
)
from ai_governance.services.replay_governance import BaselineStrategy, ReplayBaselineResolver
from ai_governance.tenancy.domain import TenantContext
from ai_governance.domain.replay import ReplayStatus
from ai_governance.repositories.in_memory_replay_repository import InMemoryReplayRepository
from ai_governance.repositories.in_memory import InMemoryJobRepository
from ai_governance.repositories.in_memory_replay_result_repository import (
    InMemoryReplayResultRepository,
)
from ai_governance.repositories.in_memory_evaluation_repository import (
    InMemoryEvaluationRepository,
)


def test_demo_replays_cover_lifecycle_and_persist_completed_evidence() -> None:
    replays = InMemoryReplayRepository()
    results = InMemoryReplayResultRepository()

    seeded = seed_demo_replays(replays, results)

    assert len(seeded) == 27
    assert seeded[:6] == (
        "demo-replay-ready",
        "demo-replay-running",
        "demo-replay-evaluating",
        "demo-replay-comparing",
        "demo-replay-failed",
        "demo-replay-completed",
    )
    completed = replays.get("demo-replay-completed", "org_default", "project_default")
    assert completed is not None
    assert completed.status is ReplayStatus.COMPLETED
    result = results.get_by_replay(
        completed.replay_id, "org_default", "project_default"
    )
    assert result is not None
    assert result.drift_summary.severity == "MEDIUM"
    completed_count = sum(
        replays.get(replay_id, "org_default", "project_default").status
        is ReplayStatus.COMPLETED
        for replay_id in seeded
    )
    assert completed_count == 22
    evaluating = replays.get("demo-replay-evaluating", "org_default", "project_default")
    comparing = replays.get("demo-replay-comparing", "org_default", "project_default")
    assert evaluating is not None and evaluating.status is ReplayStatus.EVALUATING
    assert comparing is not None and comparing.status is ReplayStatus.COMPARING
    assert seed_demo_replays(replays, results) == seeded


def test_demo_replays_use_a_registered_provider_and_repair_retired_placeholders() -> None:
    replays = InMemoryReplayRepository()
    results = InMemoryReplayResultRepository()

    seed_demo_replays(replays, results, evaluation_provider="trulens")
    ready = replays.get("demo-replay-ready", "org_default", "project_default")
    assert ready is not None
    assert ready.metadata["evaluation_provider"] == "trulens"

    invalid = replays.update(
        replace(
            ready,
            metadata={**ready.metadata, "evaluation_provider": "demo-evaluator"},
        ),
        ready.version,
    )
    seed_demo_replays(replays, results, evaluation_provider="trulens")

    repaired = replays.get("demo-replay-ready", "org_default", "project_default")
    assert repaired is not None
    assert repaired.version > invalid.version
    assert repaired.metadata["evaluation_provider"] == "trulens"


def test_demo_source_executions_are_discoverable_and_replayable() -> None:
    catalog = InMemoryReplayExecutionCatalog()
    source_resolver = InMemoryReplaySourceResolver()
    evaluations = InMemoryEvaluationRepository()

    seeded = seed_demo_replay_source_executions(
        catalog, source_resolver, evaluations
    )
    page = catalog.search(
        filters=ReplayExecutionSearchFilters(query="demo-source-execution", limit=10),
        context=TenantContext(
            organization_id="org_default",
            project_id="project_default",
            actor_id="studio-demo",
            request_id="request-demo",
        ),
    )

    assert len(seeded) == 27
    assert len(page.items) == 10
    assert page.next_cursor is not None
    assert all(item.replayable for item in page.items)
    baseline = evaluations.find_by_execution_id("demo-source-execution-06")
    assert len(baseline) == 1
    assert baseline[0].evaluator_type == "mock"
    assert baseline[0].evaluator_version == "1.0.0"
    assert baseline[0].metadata["primary"] is True


def test_demo_source_executions_seed_a_provider_compatible_baseline() -> None:
    catalog = InMemoryReplayExecutionCatalog()
    source_resolver = InMemoryReplaySourceResolver()
    evaluations = InMemoryEvaluationRepository()

    seed_demo_replay_source_executions(
        catalog,
        source_resolver,
        evaluations,
        baseline_evaluator_type="trulens",
        baseline_evaluator_version="2.8.1",
    )

    baseline = evaluations.find_by_evaluation_id("demo-source-evaluation-trulens-01")
    assert baseline is not None
    assert baseline.evaluator_type == "trulens"
    assert baseline.evaluator_version == "2.8.1"
    assert baseline.metadata["synthetic_fixture"] is True

    replay_evaluation = EvaluationResult(
        evaluation_id="replay-evaluation-01",
        execution_id="demo-replay-execution-01",
        evaluator_type="trulens",
        evaluator_version="2.8.1",
        metrics=[EvaluationMetric("answer_relevance", 0.94)],
        organization_id="org_default",
        project_id="project_default",
    )
    resolution = ReplayBaselineResolver(_EvaluationHistory(evaluations)).resolve(
        source_execution_id="demo-source-execution-01",
        replay_evaluation=replay_evaluation,
        strategy=BaselineStrategy.LATEST_COMPATIBLE,
        explicit_evaluation_id=None,
        context=TenantContext("org_default", "project_default", "studio-demo", "seed"),
    )

    assert resolution.evaluation.evaluation_id == baseline.evaluation_id


class _EvaluationHistory:
    def __init__(self, repository: InMemoryEvaluationRepository) -> None:
        self._repository = repository

    def get_history(self, execution_id: str, _context: TenantContext):
        return self._repository.find_by_execution_id(execution_id)

    def get_evaluation(self, evaluation_id: str, _context: TenantContext):
        return self._repository.find_by_evaluation_id(evaluation_id)


def test_demo_runnable_jobs_are_valid_async_evaluation_and_experiment_submissions() -> None:
    jobs = InMemoryJobRepository()

    seeded = seed_demo_runnable_jobs(jobs)

    assert len(seeded) == 3
    persisted = [jobs.find_by_id(job_id) for job_id in seeded]
    assert all(job is not None and job.status is JobStatus.QUEUED for job in persisted)
    assert {job.job_type for job in persisted if job is not None} == {
        JobType.EVALUATION,
        JobType.EXPERIMENT,
    }
    assert seed_demo_runnable_jobs(jobs) == seeded
