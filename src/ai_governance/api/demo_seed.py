from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from fastapi import FastAPI  # type: ignore

from ai_governance.api.dependencies import (
    get_governance_decision_repository,
    get_job_repository,
    get_mcp_audit_log,
    get_ontology_graph_query_repository,
    get_ontology_graph_query_service,
    get_ontology_graph_repository,
    get_policy_administration_repository,
    get_experiment_repository,
    get_experiment_candidate_repository,
    get_evaluation_run_repository,
    get_evaluation_repository,
    get_leaderboard_repository,
    get_prompt_repository,
    get_model_repository,
    get_dataset_repository,
    get_replay_repository,
    get_replay_result_repository,
    get_replay_execution_catalog,
    get_replay_source_resolver,
    get_provider_registry,
)
from ai_governance.domain.datasets import Dataset, DatasetStatus
from ai_governance.datasets import dataset_object_store_from_environment
from ai_governance.domain.evaluation_result import EvaluationMetric, EvaluationResult
from ai_governance.domain.experiments import (
    EvaluationRun,
    EvaluationRunStatus,
    Experiment,
    ExperimentCandidate,
    ExperimentStatus,
    Leaderboard,
    LeaderboardEntry,
)
from ai_governance.domain.models import Model, ModelStatus
from ai_governance.domain.prompts import Prompt, PromptStatus
from ai_governance.domain.replay import (
    Replay,
    ReplayComparisonSummary,
    ReplayConfiguration,
    ReplayConfigurationSource,
    ReplayDriftSummary,
    ReplayFailure,
    ReplayFailureStage,
    ReplayMode,
    ReplayResult,
)
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.domain.jobs import JobExecutionContext, JobSubmission, JobType
from datetime import UTC, datetime, timedelta
from ai_governance.ontology import (
    EntityType,
    OntologyGraphQueryService,
    OntologyService,
    RelationshipType,
)
from ai_governance.ontology.synchronization import (
    EvaluationResultOntologySynchronizer,
    ReplayOntologySynchronizer,
    WorkflowExecutionOntologySynchronizer,
)
from ai_governance.ontology.synchronization.synchronizer import sync_relationship
from ai_governance.tenancy.domain import TenantContext
from ai_governance.services.job_submission_service import JobSubmissionService
from ai_governance.ontology.demo_seed import (
    demo_governance_decision_service,
    seed_demo_jobs,
    seed_demo_workers,
    seed_demo_mcp_audit_log,
    seed_demo_policy_administration,
    seed_demo_ontology_graph,
    seed_demo_ontology_graph_decision,
)

LOGGER = logging.getLogger("ai_governance.api")


def seed_demo_data_for_app(app: FastAPI) -> tuple[str, ...]:
    """
    Seed local demo graph and decision data into this app's repositories.
    """

    graph_repository = _resolve_dependency(app, get_ontology_graph_repository)
    decision_repository = _resolve_dependency(
        app,
        get_governance_decision_repository,
    )
    policy_repository = _resolve_dependency(
        app,
        get_policy_administration_repository,
    )
    experiment_repository = _resolve_dependency(app, get_experiment_repository)
    candidate_repository = _resolve_dependency(app, get_experiment_candidate_repository)
    evaluation_run_repository = _resolve_dependency(app, get_evaluation_run_repository)
    evaluation_repository = _resolve_dependency(app, get_evaluation_repository)
    leaderboard_repository = _resolve_dependency(app, get_leaderboard_repository)
    prompt_repository = _resolve_dependency(app, get_prompt_repository)
    model_repository = _resolve_dependency(app, get_model_repository)
    dataset_repository = _resolve_dependency(app, get_dataset_repository)
    replay_repository = _resolve_dependency(app, get_replay_repository)
    replay_result_repository = _resolve_dependency(app, get_replay_result_repository)
    replay_execution_catalog = _resolve_dependency(app, get_replay_execution_catalog)
    replay_source_resolver = _resolve_dependency(app, get_replay_source_resolver)
    provider_registry = _resolve_dependency(app, get_provider_registry)
    demo_evaluation_provider = _demo_evaluation_provider(provider_registry)
    demo_provider_descriptor = provider_registry.get(demo_evaluation_provider).descriptor
    job_repository = _resolve_dependency(app, get_job_repository)
    audit_log = _resolve_dependency(app, get_mcp_audit_log)
    graph_query_service = _resolve_graph_query_service(app)

    seed_demo_ontology_graph(graph_repository)
    organization_id = os.getenv("AI_GOVERNANCE_BOOTSTRAP_ORGANIZATION_ID", "org_default")
    project_id = os.getenv("AI_GOVERNANCE_BOOTSTRAP_PROJECT_ID", "project_default")
    policy_id = seed_demo_policy_administration(
        policy_repository,
        organization_id=organization_id,
        project_id=project_id,
    )
    job_ids = seed_demo_jobs(job_repository)
    worker_ids = seed_demo_workers(job_repository)
    audit_ids = seed_demo_mcp_audit_log(audit_log)
    experiment_ids = seed_demo_experiments(
        experiment_repository,
        organization_id=organization_id,
        project_id=project_id,
    )
    seed_demo_registry_assets(
        prompt_repository,
        model_repository,
        dataset_repository,
    )
    seed_demo_experiment_workflows(
        experiment_repository,
        candidate_repository,
        evaluation_run_repository,
        evaluation_repository,
        leaderboard_repository,
        organization_id=organization_id,
        project_id=project_id,
    )
    runnable_job_ids = seed_demo_runnable_jobs(
        job_repository,
        organization_id=organization_id,
        project_id=project_id,
    )
    job_ids = (*job_ids, *runnable_job_ids)
    source_execution_ids = seed_demo_replay_source_executions(
        replay_execution_catalog,
        replay_source_resolver,
        evaluation_repository=evaluation_repository,
        baseline_evaluator_type=demo_provider_descriptor.name,
        baseline_evaluator_version=demo_provider_descriptor.version,
        organization_id=organization_id,
        project_id=project_id,
    )
    replay_ids = seed_demo_replays(
        replay_repository,
        replay_result_repository,
        evaluation_provider=demo_evaluation_provider,
        organization_id=organization_id,
        project_id=project_id,
    )
    synchronize_demo_experiment_graph(
        graph_repository,
        experiment_repository,
        candidate_repository,
        evaluation_run_repository,
        evaluation_repository,
        leaderboard_repository,
        prompt_repository,
        model_repository,
        dataset_repository,
    )
    synchronize_demo_replay_graph(
        graph_repository,
        replay_source_resolver,
        replay_repository,
        evaluation_repository=evaluation_repository,
        source_execution_ids=source_execution_ids,
        replay_ids=replay_ids,
        organization_id=organization_id,
        project_id=project_id,
    )
    decision_ids = seed_demo_ontology_graph_decision(
        graph_repository,
        demo_governance_decision_service(
            decision_repository=decision_repository,
            graph_query_service=graph_query_service,
        ),
        organization_id=organization_id,
        project_id=project_id,
    )
    LOGGER.info(
        "Seeded local demo data with policy %s, %s governance decisions, "
        "%s jobs, %s workers, %s audit records, %s experiments, %s source executions, and %s replays.",
        policy_id,
        len(decision_ids),
        len(job_ids),
        len(worker_ids),
        len(audit_ids),
        len(experiment_ids),
        len(source_execution_ids),
        len(replay_ids),
    )
    return decision_ids


def _demo_evaluation_provider(provider_registry: Any) -> str:
    """Use the richest provider the local runtime has actually registered."""

    return "trulens" if provider_registry.contains("trulens") else "mock"


def seed_demo_replay_source_executions(
    catalog: Any,
    source_resolver: Any,
    evaluation_repository: Any | None = None,
    *,
    baseline_evaluator_type: str = "mock",
    baseline_evaluator_version: str = "1.0.0",
    organization_id: str = "org_default",
    project_id: str = "project_default",
) -> tuple[str, ...]:
    """Seed replayable historical execution projections for local discovery.

    Every source is tenant-scoped and has the immutable snapshot references
    required by ``HistoricalReplayabilityValidator``. When an evaluation
    repository is supplied, each source gets a provider-versioned synthetic
    baseline compatible with the local replay worker. This makes the Studio
    source picker, validation, creation, and evaluation journey usable without
    a workflow runtime or production search-index adapter.
    """
    now = datetime.now(UTC).replace(microsecond=0)
    execution_ids: list[str] = []
    for index in range(1, 28):
        execution_id = f"demo-source-execution-{index:02d}"
        execution = WorkflowExecution(
            workflow_id="demo-customer-support-workflow",
            execution_id=execution_id,
            workflow_name="Customer support resolution",
            workflow_version="2026.03",
            execution_status="COMPLETED",
            input={"ticket_id": f"SUP-{1000 + index}"},
            final_state={"resolution": "Seeded historical resolution."},
            events=[{"type": "WORKFLOW_COMPLETED", "sequence": 1}],
            organization_id=organization_id,
            project_id=project_id,
            execution_adapter="historical",
            input_snapshot_ref=f"demo:input:{index:02d}",
            state_snapshot_ref=f"demo:state:{index:02d}",
            artifact_refs=[f"demo:artifact:{index:02d}"],
            prompt_refs=["demo-prompt-support-v2"],
            model_refs=["demo-model-general-v2"],
            dataset_refs=["demo-dataset-evaluation"],
            policy_refs=["demo:policy:release-gate:v3"],
            runtime_parameters={"temperature": 0.2},
            metadata={"demo": True, "source": "startup-demo-seed"},
            created_at=now - timedelta(days=index),
        )
        source_resolver.upsert(execution)
        _seed_demo_source_evaluation(
            evaluation_repository,
            execution,
            index=index,
            evaluator_type=baseline_evaluator_type,
            evaluator_version=baseline_evaluator_version,
            organization_id=organization_id,
            project_id=project_id,
        )
        from ai_governance.services.replay_execution_discovery import projection_from_execution

        catalog.upsert(
            projection_from_execution(
                execution,
                replayable=True,
                evaluation_available=True,
                actor_id="studio-demo",
                actor_type="SERVICE",
                now=now,
            ),
            TenantContext(
                organization_id=organization_id,
                project_id=project_id,
                actor_id="studio-demo",
                request_id="demo-seed",
            ),
        )
        execution_ids.append(execution_id)
    return tuple(execution_ids)


def _seed_demo_source_evaluation(
    evaluation_repository: Any | None,
    execution: WorkflowExecution,
    *,
    index: int,
    evaluator_type: str,
    evaluator_version: str,
    organization_id: str,
    project_id: str,
) -> None:
    """Persist one idempotent, provider-compatible synthetic source baseline."""
    if evaluation_repository is None:
        return
    provider = evaluator_type.strip().lower()
    if not provider or not evaluator_version.strip():
        raise ValueError("Seeded source evaluation provider identity is required.")
    evaluation_id = (
        f"demo-source-evaluation-{index:02d}"
        if provider == "mock"
        else f"demo-source-evaluation-{provider}-{index:02d}"
    )
    if evaluation_repository.find_by_evaluation_id(evaluation_id) is not None:
        return
    evaluation_repository.save(
        EvaluationResult(
            evaluation_id=evaluation_id,
            execution_id=execution.execution_id,
            evaluator_type=provider,
            evaluator_version=evaluator_version,
            metrics=[
                EvaluationMetric(
                    "answer_relevance",
                    0.90 + ((index % 5) * 0.01),
                    "Seeded source baseline for replay comparison.",
                ),
                EvaluationMetric(
                    "groundedness",
                    0.92 + ((index % 4) * 0.01),
                    "Seeded source grounding score.",
                ),
            ],
            metadata={
                "primary": True,
                "seeded": True,
                "synthetic_fixture": True,
                "purpose": "replay_source_baseline",
            },
            created_at=execution.created_at + timedelta(minutes=1),
            organization_id=organization_id,
            project_id=project_id,
        )
    )


def seed_demo_runnable_jobs(
    repository: Any,
    *,
    organization_id: str = "org_default",
    project_id: str = "project_default",
) -> tuple[str, ...]:
    """Queue valid Evaluation and Experiment jobs for local worker review.

    These are intentionally distinct from static Job-page fixtures. Their
    input references mirror the public asynchronous API contracts, so a local
    worker can claim and complete them. Stable idempotency keys keep startup
    repeatable.
    """
    service = JobSubmissionService(repository)
    context = JobExecutionContext(
        organization_id=organization_id,
        project_id=project_id,
        actor_id="studio-demo",
        submitted_request_id="demo-runnable-worker-seed",
        correlation_id="demo-runnable-worker-seed",
    )
    submissions = (
        JobSubmission(
            job_type=JobType.EVALUATION,
            input_refs={
                "operation": "evaluation.submit_async",
                "request_id": "demo-worker-evaluation-01",
                "correlation_id": "demo-worker-evaluation-01",
                "provider_name": "mock",
                "workflow_id": "demo-worker-evaluation-workflow",
                "execution_id": "demo-worker-evaluation-execution-01",
                "workflow_name": "Worker evaluation demo",
                "workflow_version": "2026.07",
                "execution_status": "COMPLETED",
                "input": {"question": "What is the release decision?"},
                "final_state": {"answer": "Approved after evidence review."},
                "events": [{"type": "WORKFLOW_COMPLETED", "sequence": 1}],
                "metric_specs": [{"name": "answer_relevance"}],
                "provider_config": {},
                "metadata": {"demo": True, "seed": "runnable-worker"},
            },
            idempotency_key="demo:runnable:evaluation:v2:01",
            submitted_by="studio-demo",
            execution_context=context,
        ),
        JobSubmission(
            job_type=JobType.EVALUATION,
            input_refs={
                "operation": "evaluation.submit_async",
                "request_id": "demo-worker-evaluation-02",
                "correlation_id": "demo-worker-evaluation-02",
                "provider_name": "mock",
                "workflow_id": "demo-worker-evaluation-workflow",
                "execution_id": "demo-worker-evaluation-execution-02",
                "workflow_name": "Worker evaluation demo",
                "workflow_version": "2026.07",
                "execution_status": "COMPLETED",
                "input": {"question": "How is a replay governed?"},
                "final_state": {"answer": "By frozen evidence and lineage."},
                "events": [{"type": "WORKFLOW_COMPLETED", "sequence": 1}],
                "metric_specs": [{"name": "groundedness"}],
                "provider_config": {},
                "metadata": {"demo": True, "seed": "runnable-worker"},
            },
            idempotency_key="demo:runnable:evaluation:v2:02",
            submitted_by="studio-demo",
            execution_context=context,
        ),
        JobSubmission(
            job_type=JobType.EXPERIMENT,
            input_refs={
                "operation": "experiment.run_async",
                "request_id": "demo-worker-experiment-01",
                "correlation_id": "demo-worker-experiment-01",
                "experiment_id": "demo-experiment-04",
                "metric_specs": [{"name": "answer_relevance"}],
                "provider_config": {},
                "metadata": {"demo": True, "seed": "runnable-worker"},
            },
            idempotency_key="demo:runnable:experiment:v2:01",
            submitted_by="studio-demo",
            execution_context=context,
        ),
    )
    return tuple(service.submit(submission).job_id for submission in submissions)


def seed_demo_replays(
    repository: Any,
    result_repository: Any,
    *,
    evaluation_provider: str = "mock",
    organization_id: str = "org_default",
    project_id: str = "project_default",
) -> tuple[str, ...]:
    """Seed idempotent Replay inventory and terminal evidence for Studio.

    Replay Studio consumes records rather than manufacturing lifecycle state in
    the browser. It provides 27 records for reviewing table pagination: 22 are
    completed and retain immutable result, comparison, and drift evidence,
    while five retain useful non-terminal and failure lifecycle examples.
    """

    provider = evaluation_provider.strip().lower()
    if not provider:
        raise ValueError("Seeded replay evaluation provider is required.")

    now = datetime.now(UTC).replace(microsecond=0)
    definitions = [
        ("demo-replay-ready", "READY", 1),
        ("demo-replay-running", "RUNNING", 2),
        ("demo-replay-evaluating", "EVALUATING", 3),
        ("demo-replay-comparing", "COMPARING", 4),
        ("demo-replay-failed", "FAILED", 5),
        ("demo-replay-completed", "COMPLETED", 6),
        *[
            (f"demo-replay-completed-{index:02d}", "COMPLETED", index + 6)
            for index in range(1, 22)
        ],
    ]
    seeded: list[str] = []
    for replay_id, target_status, age_days in definitions:
        existing = repository.get(replay_id, organization_id, project_id)
        if existing is not None:
            _repair_seeded_replay_provider(
                repository,
                existing,
                evaluation_provider=provider,
                now=now,
            )
            seeded.append(replay_id)
            continue
        created_at = now - timedelta(days=age_days)
        replay = repository.save(
            Replay.create(
                replay_id=replay_id,
                source_execution_id=f"demo-source-execution-{age_days:02d}",
                mode=ReplayMode.FULL,
                requested_by="studio-demo",
                organization_id=organization_id,
                project_id=project_id,
                request_id=f"demo-replay-request-{age_days:02d}",
                correlation_id="demo-replay-studio",
                idempotency_key=f"demo-seed:{replay_id}",
                input_hash=f"demo-input-hash-{age_days:02d}",
                metadata={
                    "reason": "Seeded replay evidence for local Studio review.",
                    "evaluation_provider": provider,
                    "demo": True,
                },
                now=created_at,
            )
        )
        replay = repository.update(
            replay.mark_ready(
                _demo_replay_configuration(age_days, created_at), created_at
            ),
            replay.version,
        )
        if target_status == "READY":
            seeded.append(replay_id)
            continue
        replay = repository.update(
            replay.mark_queued(f"demo-replay-execution-job-{age_days:02d}", created_at),
            replay.version,
        )
        replay = repository.update(
            replay.mark_running(1, created_at + timedelta(minutes=1)), replay.version
        )
        replay = repository.update(
            replay.reserve_replay_execution_id(
                f"demo-replay-execution-{age_days:02d}",
                created_at + timedelta(minutes=1),
            ),
            replay.version,
        )
        if target_status == "RUNNING":
            seeded.append(replay_id)
            continue
        replay = repository.update(
            replay.mark_execution_completed(created_at + timedelta(minutes=3)),
            replay.version,
        )
        if target_status == "EXECUTION_COMPLETED":
            seeded.append(replay_id)
            continue
        if target_status == "FAILED":
            failed = replay.mark_execution_failed(
                ReplayFailure(
                    code="DemoEvaluationProviderUnavailable",
                    message="Seeded example of a replay evaluation provider outage.",
                    stage=ReplayFailureStage.EVALUATION,
                    details={"retryable": True, "demo": True},
                    occurred_at=created_at + timedelta(minutes=4),
                ),
                created_at + timedelta(minutes=4),
            )
            repository.update(failed, replay.version)
            seeded.append(replay_id)
            continue
        if target_status == "CANCELLED":
            requested = replay.request_cancellation(created_at + timedelta(minutes=4))
            requested = repository.update(requested, replay.version)
            repository.update(
                requested.mark_cancelled(created_at + timedelta(minutes=5)),
                requested.version,
            )
            seeded.append(replay_id)
            continue
        replay = repository.update(
            replay.mark_evaluating(
                f"demo-replay-evaluation-job-{age_days:02d}",
                created_at + timedelta(minutes=4),
            ),
            replay.version,
        )
        if target_status == "EVALUATING":
            seeded.append(replay_id)
            continue
        replay = repository.update(
            replay.record_replay_evaluation(
                f"demo-replay-evaluation-{age_days:02d}",
                created_at + timedelta(minutes=5),
            ),
            replay.version,
        )
        replay = repository.update(
            replay.record_baseline_evaluation(
                f"demo-baseline-evaluation-{age_days:02d}",
                created_at + timedelta(minutes=5),
            ),
            replay.version,
        )
        replay = repository.update(
            replay.mark_comparing(created_at + timedelta(minutes=6)), replay.version
        )
        if target_status == "COMPARING":
            seeded.append(replay_id)
            continue
        replay = repository.update(
            replay.record_comparison(
                f"demo-replay-comparison-{age_days:02d}",
                created_at + timedelta(minutes=7),
            ),
            replay.version,
        )
        replay = repository.update(
            replay.record_drift(
                f"demo-replay-drift-{age_days:02d}",
                created_at + timedelta(minutes=7),
            ),
            replay.version,
        )
        if target_status == "ARCHIVED":
            completed = replay.mark_completed(
                f"demo-replay-result-{age_days:02d}", created_at + timedelta(minutes=8)
            )
            completed = repository.update(completed, replay.version)
            result_repository.save(
                _demo_replay_result(completed, created_at + timedelta(minutes=8))
            )
            repository.update(
                completed.archive(created_at + timedelta(minutes=9)), completed.version
            )
            seeded.append(replay_id)
            continue
        completed = replay.mark_completed(
            f"demo-replay-result-{age_days:02d}", created_at + timedelta(minutes=8)
        )
        completed = repository.update(completed, replay.version)
        result_repository.save(
            _demo_replay_result(completed, created_at + timedelta(minutes=8))
        )
        seeded.append(replay_id)
    return tuple(seeded)


def _repair_seeded_replay_provider(
    repository: Any,
    replay: Replay,
    *,
    evaluation_provider: str,
    now: datetime,
) -> None:
    """Repair the retired placeholder provider on known demo replays only."""

    if not replay.metadata.get("demo") or not replay.replay_id.startswith("demo-replay-"):
        return

    metadata = dict(replay.metadata)
    failure = replay.failure
    changed = False
    if metadata.get("evaluation_provider") == "demo-evaluator":
        metadata["evaluation_provider"] = evaluation_provider
        changed = True
    if failure is not None and failure.code == "EvaluationProviderNotFoundError":
        failure = ReplayFailure(
            code="DemoEvaluationProviderUnavailable",
            message="Seeded example of a replay evaluation provider outage.",
            stage=ReplayFailureStage.EVALUATION,
            details={"retryable": True, "demo": True},
            occurred_at=failure.occurred_at,
        )
        changed = True
    if changed:
        repository.update(
            replace(replay, metadata=metadata, failure=failure, updated_at=now),
            replay.version,
        )


def _demo_replay_configuration(index: int, now: datetime) -> ReplayConfiguration:
    return ReplayConfiguration(
        workflow_id="demo-customer-support-workflow",
        workflow_version="2026.03",
        execution_adapter="historical",
        input_snapshot_ref=f"demo:input:{index:02d}",
        state_snapshot_ref=f"demo:state:{index:02d}",
        artifact_refs=(f"demo:artifact:{index:02d}",),
        prompt_refs=("demo:prompt:support:v2",),
        model_refs=("demo:model:general:2026.02",),
        dataset_refs=("demo:dataset:support:2026.01",),
        policy_refs=("demo:policy:release-gate:v3",),
        runtime_parameters={"temperature": 0.2},
        configuration_source=ReplayConfigurationSource.ORIGINAL,
        resolved_at=now,
        configuration_hash=f"demo-replay-configuration-{index:02d}",
    )


def _demo_replay_result(replay: Replay, now: datetime) -> ReplayResult:
    return ReplayResult(
        result_id=replay.result_id or "",
        replay_id=replay.replay_id,
        source_execution_id=replay.source_execution_id,
        replay_execution_id=replay.replay_execution_id or "",
        baseline_evaluation_id=replay.baseline_evaluation_id or "",
        replay_evaluation_id=replay.replay_evaluation_id or "",
        comparison_id=replay.comparison_id or "",
        drift_id=replay.drift_id or "",
        baseline_strategy="LATEST_COMPATIBLE",
        comparison_summary=ReplayComparisonSummary(5, 2, 1, 1, 1, 0, 0.034),
        drift_summary=ReplayDriftSummary(
            severity="MEDIUM",
            changed_metrics=("answer_relevance", "groundedness"),
            new_metrics=("latency",),
            removed_metrics=(),
            analyzer_version="governance-drift-v1",
            threshold_policy={"policy": "demo-governance-v1", "medium": 0.1},
        ),
        organization_id=replay.organization_id,
        project_id=replay.project_id,
        created_at=now,
        metadata={"demo": True, "source": "startup-demo-seed"},
    )


def seed_demo_experiments(
    repository: Any,
    *,
    organization_id: str = "org_default",
    project_id: str = "project_default",
    minimum_count: int = 15,
) -> tuple[str, ...]:
    """Seed a useful experiment inventory for the Studio list view.

    The seed is idempotent and only fills the inventory when fewer than the
    requested number of experiments exist in the selected tenant context.
    """
    existing = [
        experiment
        for experiment in repository.find_all()
        if experiment.organization_id == organization_id
        and experiment.project_id == project_id
    ]
    if len(existing) >= minimum_count:
        return tuple(experiment.experiment_id for experiment in existing)

    names = (
        "Customer Support RAG Evaluation",
        "Claims Triage Prompt Benchmark",
        "Invoice Extraction Model Bakeoff",
        "Policy Assistant Groundedness Study",
        "Security Alert Classification",
        "Knowledge Base Answer Quality",
        "Onboarding Copilot Evaluation",
        "Contract Review Candidate Comparison",
        "Incident Summary Reliability",
        "Sales Enablement Response Study",
        "Healthcare FAQ Hallucination Audit",
        "Finance Assistant Latency Review",
        "Developer Copilot Cost Benchmark",
        "Multilingual Support Quality",
        "Document Routing Configuration Test",
    )
    statuses = (
        ExperimentStatus.COMPLETED,
        ExperimentStatus.COMPLETED,
        ExperimentStatus.RUNNING,
        ExperimentStatus.DRAFT,
        ExperimentStatus.FAILED,
    )
    now = datetime.now(UTC)
    created_ids = list(experiment.experiment_id for experiment in existing)
    needed = minimum_count - len(existing)
    for index in range(needed):
        experiment_id = f"demo-experiment-{index + 1:02d}"
        if repository.find_by_id(experiment_id) is not None:
            continue
        experiment = Experiment(
            experiment_id=experiment_id,
            name=names[index % len(names)],
            description=(
                "Seeded Studio experiment for comparing governed prompts, "
                "models, datasets, and evaluation outcomes."
            ),
            owner="studio-demo",
            created_at=now - timedelta(days=(index + 1) * 2),
            status=statuses[index % len(statuses)],
            organization_id=organization_id,
            project_id=project_id,
        )
        repository.save(experiment)
        created_ids.append(experiment_id)
    return tuple(created_ids)


def seed_demo_experiment_workflows(
    experiment_repository: Any,
    candidate_repository: Any,
    evaluation_run_repository: Any,
    evaluation_repository: Any,
    leaderboard_repository: Any,
    *,
    organization_id: str = "org_default",
    project_id: str = "project_default",
) -> None:
    """Seed candidates, evaluation evidence, and leaderboard snapshots."""
    now = datetime.now(UTC)
    experiments = [
        experiment
        for experiment in experiment_repository.find_all()
        if experiment.organization_id == organization_id
        and experiment.project_id == project_id
        and experiment.experiment_id.startswith("demo-experiment-")
    ]
    for experiment in experiments:
        candidates = candidate_repository.find_by_experiment_id(
            experiment.experiment_id
        )
        if not candidates:
            for variant in ("baseline", "optimized"):
                candidate_repository.save(
                    ExperimentCandidate(
                        candidate_id=f"{experiment.experiment_id}-{variant}",
                        experiment_id=experiment.experiment_id,
                        name=f"{experiment.name} · {variant.title()}",
                        prompt_id=(
                            "demo-prompt-support-v1"
                            if variant == "baseline"
                            else "demo-prompt-support-v2"
                        ),
                        prompt_version="v1.0" if variant == "baseline" else "v1.1",
                        model_id=(
                            "demo-model-general-v1"
                            if variant == "baseline"
                            else "demo-model-general-v2"
                        ),
                        model_version="2026.01" if variant == "baseline" else "2026.02",
                        dataset_id="demo-dataset-evaluation",
                        dataset_version="v1.0",
                        evaluation_provider="mock",
                        temperature=0.0 if variant == "baseline" else 0.2,
                        top_p=1.0,
                        max_tokens=1024,
                        metadata={"seeded": True, "variant": variant},
                        created_at=experiment.created_at,
                    )
                )
            candidates = candidate_repository.find_by_experiment_id(
                experiment.experiment_id
            )

        if experiment.status not in {
            ExperimentStatus.COMPLETED,
            ExperimentStatus.FAILED,
        }:
            continue
        if evaluation_run_repository.find_by_experiment_id(experiment.experiment_id):
            continue

        entries: list[LeaderboardEntry] = []
        for rank, candidate in enumerate(candidates, start=1):
            evaluation_id = f"{candidate.candidate_id}-evaluation"
            run_id = f"{candidate.candidate_id}-run"
            started_at = now - timedelta(days=rank)
            completed_at = started_at + timedelta(seconds=18 + rank * 4)
            score = 0.91 - ((rank - 1) * 0.08)
            evaluation_repository.save(
                EvaluationResult(
                    evaluation_id=evaluation_id,
                    execution_id=run_id,
                    evaluator_type="mock",
                    evaluator_version="1.0",
                    metrics=[
                        EvaluationMetric("overall_score", score),
                        EvaluationMetric("groundedness", score + 0.02),
                        EvaluationMetric("answer_relevance", score + 0.01),
                        EvaluationMetric("latency", float(18 + rank * 4)),
                        EvaluationMetric("cost", 0.0025 * rank),
                    ],
                    metadata={"seeded": True},
                    created_at=completed_at,
                    organization_id=organization_id,
                    project_id=project_id,
                )
            )
            run_status = (
                EvaluationRunStatus.FAILED
                if experiment.status == ExperimentStatus.FAILED and rank == 2
                else EvaluationRunStatus.COMPLETED
            )
            evaluation_run_repository.save(
                EvaluationRun(
                    run_id=run_id,
                    experiment_id=experiment.experiment_id,
                    candidate_id=candidate.candidate_id,
                    dataset_version=candidate.dataset_version,
                    evaluation_provider=candidate.evaluation_provider,
                    evaluation_result_id=(
                        evaluation_id
                        if run_status == EvaluationRunStatus.COMPLETED
                        else None
                    ),
                    started_at=started_at,
                    completed_at=completed_at,
                    status=run_status,
                )
            )
            if run_status == EvaluationRunStatus.COMPLETED:
                entries.append(
                    LeaderboardEntry(
                        rank=len(entries) + 1,
                        candidate_id=candidate.candidate_id,
                        overall_score=score,
                        metrics={
                            "groundedness": score + 0.02,
                            "answer_relevance": score + 0.01,
                        },
                        cost=0.0025 * rank,
                        latency=float(18 + rank * 4),
                        reason="Seeded completed evaluation evidence.",
                    )
                )
        if entries:
            leaderboard_repository.save(
                Leaderboard(
                    leaderboard_id=f"{experiment.experiment_id}-leaderboard",
                    experiment_id=experiment.experiment_id,
                    ranking_strategy="overall_score",
                    generated_at=now,
                    entries=tuple(entries),
                )
            )


def seed_demo_registry_assets(
    prompt_repository: Any,
    model_repository: Any,
    dataset_repository: Any,
) -> None:
    """Create the governed registry references used by seeded candidates."""
    now = datetime.now(UTC)
    prompts = (
        ("demo-prompt-support-v1", "v1.0", "Answer using only the supplied context."),
        (
            "demo-prompt-support-v2",
            "v1.1",
            "Answer using the supplied context and cite evidence.",
        ),
    )
    for prompt_id, version, template in prompts:
        if prompt_repository.find_by_id(prompt_id) is None:
            prompt_repository.save(
                Prompt(
                    prompt_id=prompt_id,
                    name="Demo Support Assistant",
                    version=version,
                    template=template,
                    variables=("context", "question"),
                    created_at=now,
                    created_by="studio-demo",
                    status=PromptStatus.ACTIVE,
                )
            )

    models = (
        ("demo-model-general-v1", "2026.01"),
        ("demo-model-general-v2", "2026.02"),
    )
    for model_id, version in models:
        if model_repository.find_by_id(model_id) is None:
            model_repository.save(
                Model(
                    model_id=model_id,
                    provider="mock",
                    model_name="demo-general",
                    version=version,
                    parameters={"temperature": 0.0},
                    cost={"input_per_1k_tokens": 0.001},
                    latency=0.2,
                    context_window=8192,
                    creator="studio-demo",
                    created_at=now,
                    status=ModelStatus.ACTIVE,
                )
            )

    dataset_id = "demo-dataset-evaluation"
    existing_dataset = dataset_repository.find_by_id(dataset_id)
    object_store = dataset_object_store_from_environment()
    if object_store is None:
        storage_uri = "memory://ai-governance/demo-evaluation"
        storage_type = "memory"
    else:
        bucket = os.getenv("AI_GOVERNANCE_DATASET_S3_BUCKET", "ai-governance-datasets")
        key = "demo/evaluation/v1.0/dataset.jsonl"
        object_store.put_bytes(
            bucket=bucket,
            key=key,
            body=_demo_evaluation_dataset_jsonl(),
            content_type="application/x-ndjson",
            metadata={"dataset_id": dataset_id, "version": "v1.0"},
        )
        storage_uri = f"s3://{bucket}/{key}"
        storage_type = "S3"
    dataset_repository.save(
        Dataset(
            dataset_id=dataset_id,
            name="Demo Evaluation Set",
            version="v1.0",
            description="Seeded evaluation examples for Studio experiments.",
            storage_uri=storage_uri,
            storage_type=storage_type,
            schema_version="1.0",
            record_count=120,
            checksum="demo-evaluation-v1-checksum",
            creator="studio-demo",
            created_at=(existing_dataset.created_at if existing_dataset else now),
            status=DatasetStatus.FROZEN,
        )
    )


def _demo_evaluation_dataset_jsonl() -> bytes:
    """Return deterministic local content for the seeded evaluation dataset."""

    rows = [
        {
            "question": f"Demo support question {index}",
            "expected_answer": f"Demo support answer {index}",
            "context": "Seeded local evaluation content.",
        }
        for index in range(1, 121)
    ]
    return ("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n").encode()


def synchronize_demo_experiment_graph(
    graph_repository: Any,
    experiment_repository: Any,
    candidate_repository: Any,
    evaluation_run_repository: Any,
    evaluation_repository: Any,
    leaderboard_repository: Any,
    prompt_repository: Any,
    model_repository: Any,
    dataset_repository: Any,
) -> None:
    """Project seeded experiment evidence into the ontology graph.

    Demo repositories are populated directly during startup, so they do not
    emit domain events. This startup reconciliation uses the same ontology
    synchronizers used by the normal platform projection path.
    """
    from ai_governance.ontology.synchronization import (
        CandidateOntologySynchronizer,
        DatasetOntologySynchronizer,
        EvaluationResultOntologySynchronizer,
        EvaluationRunOntologySynchronizer,
        ExperimentOntologySynchronizer,
        ModelOntologySynchronizer,
        PromptOntologySynchronizer,
    )

    service = OntologyService(graph_repository)
    if (
        service.get_entity("Experiment", "demo-experiment-01") is not None
        and service.get_entity(
            "Candidate",
            "demo-experiment-01-baseline",
        )
        is not None
        and service.get_entity(
            "Leaderboard",
            "demo-experiment-01-leaderboard",
        )
        is not None
    ):
        return

    for prompt in prompt_repository.find_all():
        if service.get_entity("PromptVersion", prompt.prompt_id) is None:
            PromptOntologySynchronizer(service, prompt_repository).synchronize(prompt)
    for model in model_repository.find_all():
        if service.get_entity("ModelVersion", model.model_id) is None:
            ModelOntologySynchronizer(service, model_repository).synchronize(model)
    for dataset in dataset_repository.find_all():
        if service.get_entity("DatasetVersion", dataset.dataset_id) is None:
            DatasetOntologySynchronizer(service, dataset_repository).synchronize(
                dataset
            )
    for experiment in experiment_repository.find_all():
        if (
            experiment.experiment_id.startswith("demo-experiment-")
            and service.get_entity("Experiment", experiment.experiment_id) is None
        ):
            ExperimentOntologySynchronizer(service, experiment_repository).synchronize(
                experiment
            )
    for candidate in candidate_repository.find_all():
        if service.get_entity("Candidate", candidate.candidate_id) is None:
            CandidateOntologySynchronizer(service, candidate_repository).synchronize(
                candidate
            )
    synchronized_evaluations: set[str] = set()
    for run in evaluation_run_repository.find_all():
        if (
            run.evaluation_result_id is not None
            and run.evaluation_result_id not in synchronized_evaluations
        ):
            result = evaluation_repository.find_by_evaluation_id(
                run.evaluation_result_id
            )
            if result is not None:
                if service.get_entity("EvaluationResult", result.evaluation_id) is None:
                    EvaluationResultOntologySynchronizer(
                        service,
                        evaluation_repository,
                    ).synchronize(result)
                synchronized_evaluations.add(run.evaluation_result_id)
    for run in evaluation_run_repository.find_all():
        if service.get_entity("EvaluationRun", run.run_id) is None:
            EvaluationRunOntologySynchronizer(
                service, evaluation_run_repository
            ).synchronize(run)
    for leaderboard in leaderboard_repository.find_all():
        if service.get_entity("Leaderboard", leaderboard.leaderboard_id) is None:
            _synchronize_demo_leaderboard(
                service, leaderboard, evaluation_run_repository
            )


def synchronize_demo_replay_graph(
    graph_repository: Any,
    source_resolver: Any,
    replay_repository: Any,
    evaluation_repository: Any,
    *,
    source_execution_ids: tuple[str, ...],
    replay_ids: tuple[str, ...],
    organization_id: str,
    project_id: str,
) -> None:
    """Project the seeded workflow, evaluation, and replay lineage into ontology."""
    service = OntologyService(graph_repository)
    context = TenantContext(
        organization_id=organization_id,
        project_id=project_id,
        actor_id="studio-demo",
        request_id="demo-seed",
    )
    workflow_synchronizer = WorkflowExecutionOntologySynchronizer(service)
    replay_synchronizer = ReplayOntologySynchronizer(service)
    evaluation_synchronizer = EvaluationResultOntologySynchronizer(
        service, evaluation_repository
    )
    for execution_id in source_execution_ids:
        execution = source_resolver.get_execution(execution_id, context)
        if execution is None:
            continue
        workflow_synchronizer.synchronize(execution)
        for evaluation in evaluation_repository.find_by_execution_id(execution_id):
            if service.get_entity(
                EntityType.EVALUATION_RESULT.value, evaluation.evaluation_id
            ) is None:
                evaluation_synchronizer.synchronize(evaluation)
            sync_relationship(
                service,
                source_type=EntityType.WORKFLOW_EXECUTION,
                source_id=execution_id,
                relationship_type=RelationshipType.PRODUCES,
                target_type=EntityType.EVALUATION_RESULT,
                target_id=evaluation.evaluation_id,
                created_by="demo-seed",
            )
    for replay_id in replay_ids:
        replay = replay_repository.get(replay_id, organization_id, project_id)
        if replay is not None:
            replay_synchronizer.synchronize_replay(replay)


def _synchronize_demo_leaderboard(
    service: OntologyService,
    leaderboard: Leaderboard,
    evaluation_run_repository: Any,
) -> None:
    from ai_governance.ontology.synchronization import LeaderboardOntologySynchronizer

    LeaderboardOntologySynchronizer(
        service,
        evaluation_run_repository=evaluation_run_repository,
    ).synchronize(leaderboard)


def _resolve_graph_query_service(app: FastAPI) -> OntologyGraphQueryService:
    override = app.dependency_overrides.get(get_ontology_graph_query_service)
    if override is not None:
        return override()

    query_repository = _resolve_dependency(
        app,
        get_ontology_graph_query_repository,
    )
    return get_ontology_graph_query_service(query_repository)


def _resolve_dependency(
    app: FastAPI,
    dependency: Callable[..., Any],
) -> Any:
    override = app.dependency_overrides.get(dependency)
    if override is not None:
        return override()
    return dependency()
