from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from ai_governance.api.app import create_app
from ai_governance.api.dependencies import (
    get_evaluation_repository,
    get_evaluation_run_repository,
    get_experiment_candidate_repository,
    get_experiment_repository,
    get_job_repository,
    get_leaderboard_repository,
    get_mcp_audit_log,
)
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
from ai_governance.domain.jobs import JobSubmission, JobType
from ai_governance.mcp.audit import MCPExecutionAuditLog
from ai_governance.mcp.dto import WriteEnvelope
from ai_governance.repositories.in_memory import InMemoryJobRepository
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
from ai_governance.services.job_submission_service import JobSubmissionService


def test_experiment_insights_and_reports_return_evidence() -> None:
    client, _state = _client()

    insight = client.get("/api/v1/experiments/experiment-1/insights")
    candidate = client.get(
        "/api/v1/experiments/experiment-1/candidates/candidate-a/insights"
    )
    comparison = client.get(
        "/api/v1/experiments/experiment-1/comparative-insights"
    )
    report = client.get(
        "/api/v1/reports/experiments/experiment-1",
        params={"format": "markdown"},
    )

    assert insight.status_code == 200
    assert insight.json()["status"] == "SUCCEEDED"
    assert insight.json()["metrics"][0]["candidate_id"] == "candidate-a"
    assert candidate.status_code == 200
    assert candidate.json()["metrics"]
    assert comparison.status_code == 200
    assert "leads" in comparison.json()["summary"]
    assert report.status_code == 200
    assert report.json()["report_format"] == "markdown"
    assert "Experiment Report" in report.json()["content"]


def test_investigation_and_drift_explanations_return_evidence() -> None:
    client, state = _client()
    job_id = state["job_id"]
    audit_id = state["audit_id"]

    by_correlation = client.get(
        "/api/v1/investigations/by-correlation/corr-1"
    )
    by_job = client.get(f"/api/v1/investigations/by-job/{job_id}")
    by_audit = client.get(f"/api/v1/investigations/by-audit/{audit_id}")
    drift = client.get("/api/v1/governance/drift/eval-a..eval-b/explanation")
    evaluation_drift = client.get(
        "/api/v1/evaluations/eval-b/drift-explanation"
    )
    investigation_report = client.get(
        "/api/v1/reports/investigations/corr-1"
    )

    assert by_correlation.status_code == 200
    assert by_correlation.json()["evidence"]
    assert by_job.status_code == 200
    assert by_job.json()["related_resources"][0]["kind"] == "job"
    assert by_audit.status_code == 200
    assert by_audit.json()["related_resources"][0]["kind"] == "audit"
    assert drift.status_code == 200
    assert drift.json()["metrics"]
    assert evaluation_drift.status_code == 200
    assert evaluation_drift.json()["summary"]
    assert investigation_report.status_code == 200
    assert investigation_report.json()["report_type"] == (
        "execution_investigation_report"
    )


def test_phase_3_routes_are_in_openapi() -> None:
    client, _state = _client()

    paths = client.get("/openapi.json").json()["paths"]

    assert "/api/v1/experiments/{experiment_id}/insights" in paths
    assert "/api/v1/investigations/by-correlation/{correlation_id}" in paths
    assert "/api/v1/governance/drift/{drift_id}/explanation" in paths
    assert "/api/v1/reports/experiments/{experiment_id}" in paths


def _client() -> tuple[TestClient, dict[str, str]]:
    experiment_repository = InMemoryExperimentRepository()
    candidate_repository = InMemoryExperimentCandidateRepository()
    run_repository = InMemoryEvaluationRunRepository()
    evaluation_repository = InMemoryEvaluationRepository()
    leaderboard_repository = InMemoryLeaderboardRepository()
    job_repository = InMemoryJobRepository()
    audit_log = MCPExecutionAuditLog.in_memory()
    now = datetime(2026, 6, 28, tzinfo=UTC)

    experiment_repository.save(
        Experiment(
            experiment_id="experiment-1",
            name="claim-validation",
            description="Compare claim validation candidates.",
            owner="tester",
            created_at=now,
            status=ExperimentStatus.COMPLETED,
        )
    )
    candidate_repository.save(_candidate("candidate-a", "Candidate A"))
    candidate_repository.save(_candidate("candidate-b", "Candidate B"))
    evaluation_repository.save(_evaluation("eval-a", 0.9, now))
    evaluation_repository.save(_evaluation("eval-b", 0.7, now))
    run_repository.save(
        _run("run-a", "candidate-a", "eval-a", now)
    )
    run_repository.save(
        _run("run-b", "candidate-b", "eval-b", now)
    )
    leaderboard_repository.save(
        Leaderboard(
            leaderboard_id="leaderboard-1",
            experiment_id="experiment-1",
            ranking_strategy="overall_score",
            generated_at=now,
            entries=(
                LeaderboardEntry(
                    rank=1,
                    candidate_id="candidate-a",
                    overall_score=0.9,
                    metrics={"answer_relevance": 0.9},
                    cost=0.1,
                    latency=100.0,
                    reason="Best quality score.",
                ),
                LeaderboardEntry(
                    rank=2,
                    candidate_id="candidate-b",
                    overall_score=0.7,
                    metrics={"answer_relevance": 0.7},
                    cost=0.05,
                    latency=80.0,
                    reason="Lower score but cheaper.",
                ),
            ),
        )
    )
    job = JobSubmissionService(
        job_repository,
        id_generator=lambda: "job-1",
        clock=lambda: now,
    ).submit(
        JobSubmission(
            job_type=JobType.EVALUATION,
            input_refs={"evaluation_id": "eval-a"},
            idempotency_key="job-key-1",
            submitted_by="tester",
        )
    )
    job_repository.mark_succeeded(job.job_id, "evaluation:eval-a")
    audit = audit_log.start(
        tool_name="evaluation.submit_async",
        operation_type="SUBMIT_EVALUATION_JOB",
        resource_type="evaluation",
        resource_id="eval-a",
        envelope=WriteEnvelope(
            request_id="request-1",
            correlation_id="corr-1",
            idempotency_key="audit-key-1",
            requested_by="tester",
            actor_type="SERVICE",
            reason="test",
        ),
        payload={"evaluation_id": "eval-a"},
    )
    audit_log.complete(audit, status="SUCCEEDED", job_id="job-1")

    app = create_app()
    app.dependency_overrides[get_experiment_repository] = (
        lambda: experiment_repository
    )
    app.dependency_overrides[get_experiment_candidate_repository] = (
        lambda: candidate_repository
    )
    app.dependency_overrides[get_evaluation_run_repository] = (
        lambda: run_repository
    )
    app.dependency_overrides[get_evaluation_repository] = (
        lambda: evaluation_repository
    )
    app.dependency_overrides[get_leaderboard_repository] = (
        lambda: leaderboard_repository
    )
    app.dependency_overrides[get_job_repository] = lambda: job_repository
    app.dependency_overrides[get_mcp_audit_log] = lambda: audit_log
    return TestClient(app), {"job_id": "job-1", "audit_id": audit.audit_id}


def _candidate(candidate_id: str, name: str) -> ExperimentCandidate:
    return ExperimentCandidate(
        candidate_id=candidate_id,
        experiment_id="experiment-1",
        name=name,
        prompt_id="prompt",
        prompt_version="v1",
        model_id="model",
        model_version="v1",
        dataset_id="dataset",
        dataset_version="v1",
        evaluation_provider="mock",
        temperature=0.1,
        top_p=0.9,
        max_tokens=256,
        metadata={},
        created_at=datetime(2026, 6, 28, tzinfo=UTC),
    )


def _evaluation(
    evaluation_id: str,
    score: float,
    created_at: datetime,
) -> EvaluationResult:
    return EvaluationResult(
        evaluation_id=evaluation_id,
        execution_id="execution-1",
        evaluator_type="mock",
        evaluator_version="1.0.0",
        metrics=[EvaluationMetric("answer_relevance", score)],
        created_at=created_at,
    )


def _run(
    run_id: str,
    candidate_id: str,
    evaluation_id: str,
    timestamp: datetime,
) -> EvaluationRun:
    return EvaluationRun(
        run_id=run_id,
        experiment_id="experiment-1",
        candidate_id=candidate_id,
        dataset_version="v1",
        evaluation_provider="mock",
        evaluation_result_id=evaluation_id,
        started_at=timestamp,
        completed_at=timestamp,
        status=EvaluationRunStatus.COMPLETED,
    )
