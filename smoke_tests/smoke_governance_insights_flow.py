from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

from kavach.api.app import create_app
from kavach.api.dependencies import (
    get_evaluation_repository,
    get_evaluation_run_repository,
    get_experiment_candidate_repository,
    get_experiment_repository,
    get_job_repository,
    get_leaderboard_repository,
    get_mcp_audit_log,
)
from kavach.domain.evaluation_result import EvaluationMetric, EvaluationResult
from kavach.domain.experiments import (
    EvaluationRun,
    EvaluationRunStatus,
    Experiment,
    ExperimentCandidate,
    ExperimentStatus,
    Leaderboard,
    LeaderboardEntry,
)
from kavach.domain.jobs import JobSubmission, JobType
from kavach.mcp.audit import MCPExecutionAuditLog
from kavach.mcp.clients import RestClient, RestClientError
from kavach.mcp.dto import WriteEnvelope
from kavach.mcp.server import create_server
from kavach.repositories.in_memory import InMemoryJobRepository
from kavach.repositories.in_memory_evaluation_repository import (
    InMemoryEvaluationRepository,
)
from kavach.repositories.in_memory_evaluation_run_repository import (
    InMemoryEvaluationRunRepository,
)
from kavach.repositories.in_memory_experiment_candidate_repository import (
    InMemoryExperimentCandidateRepository,
)
from kavach.repositories.in_memory_experiment_repository import (
    InMemoryExperimentRepository,
)
from kavach.repositories.in_memory_leaderboard_repository import (
    InMemoryLeaderboardRepository,
)
from kavach.services.job_submission_service import JobSubmissionService


def main() -> None:
    client, state = _seeded_client()
    mcp_server = create_server(
        RestClient(
            base_url="http://testserver",
            transport=_test_client_transport(client),
        ),
        audit_log=state.audit_log,
    )

    checks = [
        _rest_get(client, "REST experiment insights", "/api/v1/experiments/experiment-1/insights"),
        _rest_get(
            client,
            "REST candidate insights",
            "/api/v1/experiments/experiment-1/candidates/candidate-a/insights",
        ),
        _rest_get(
            client,
            "REST comparative insights",
            "/api/v1/experiments/experiment-1/comparative-insights",
        ),
        _rest_get(
            client,
            "REST investigation by correlation",
            "/api/v1/investigations/by-correlation/corr-1",
        ),
        _rest_get(
            client,
            "REST investigation by job",
            f"/api/v1/investigations/by-job/{state.job_id}",
        ),
        _rest_get(
            client,
            "REST investigation by audit",
            f"/api/v1/investigations/by-audit/{state.audit_id}",
        ),
        _rest_get(
            client,
            "REST drift explanation",
            "/api/v1/governance/drift/eval-a..eval-b/explanation",
        ),
        _rest_get(
            client,
            "REST evaluation drift explanation",
            "/api/v1/evaluations/eval-b/drift-explanation",
        ),
        _rest_get(
            client,
            "REST experiment markdown report",
            "/api/v1/reports/experiments/experiment-1",
            query={"format": "markdown"},
        ),
        _rest_get(
            client,
            "REST investigation json report",
            "/api/v1/reports/investigations/corr-1",
        ),
        _mcp_call(
            mcp_server,
            "MCP summarize experiment",
            "governance.summarize_experiment",
            {"experiment_id": "experiment-1"},
        ),
        _mcp_call(
            mcp_server,
            "MCP explain candidate",
            "governance.explain_candidate",
            {
                "experiment_id": "experiment-1",
                "candidate_id": "candidate-a",
            },
        ),
        _mcp_call(
            mcp_server,
            "MCP investigate execution",
            "governance.investigate_execution",
            {"correlation_id": "corr-1"},
        ),
        _mcp_call(
            mcp_server,
            "MCP generate experiment report",
            "governance.generate_experiment_report",
            {"experiment_id": "experiment-1", "format": "json"},
        ),
    ]

    for check in checks:
        check.print_summary()


@dataclass(frozen=True)
class SeedState:
    audit_log: MCPExecutionAuditLog
    audit_id: str
    job_id: str


@dataclass(frozen=True)
class SmokeCheck:
    label: str
    payload: dict[str, Any]

    def print_summary(self) -> None:
        print(f"[{self.label}]")
        if "report_type" in self.payload:
            print(f"report_type={self.payload['report_type']}")
            print(f"format={self.payload['report_format']}")
            content = self.payload["content"]
            if isinstance(content, str):
                print(f"content_preview={content.splitlines()[0]}")
            else:
                print(f"content_status={content['status']}")
        else:
            print(f"status={self.payload['status']}")
            print(f"confidence={self.payload['confidence']}")
            print(f"summary={self.payload['summary']}")
            print(f"evidence={len(self.payload['evidence'])}")
            print(f"metrics={len(self.payload['metrics'])}")
        print()


def _seeded_client() -> tuple[TestClient, SeedState]:
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
    run_repository.save(_run("run-a", "candidate-a", "eval-a", now))
    run_repository.save(_run("run-b", "candidate-b", "eval-b", now))
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
            reason="Smoke-test Phase 3 investigations",
        ),
        payload={"evaluation_id": "eval-a"},
    )
    audit_log.complete(audit, status="SUCCEEDED", job_id=job.job_id)

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
    return TestClient(app), SeedState(
        audit_log=audit_log,
        audit_id=audit.audit_id,
        job_id=job.job_id,
    )


def _candidate(
    candidate_id: str,
    name: str,
) -> ExperimentCandidate:
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


def _rest_get(
    client: TestClient,
    label: str,
    path: str,
    query: dict[str, Any] | None = None,
) -> SmokeCheck:
    response = client.get(path, params=query)
    payload = response.json()
    _assert_http_status(response.status_code, 200, payload)
    return SmokeCheck(label=label, payload=payload)


def _mcp_call(
    mcp_server,
    label: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> SmokeCheck:
    result = mcp_server.call_tool(tool_name, arguments)
    if result.status != "ok":
        raise AssertionError(result.error)
    return SmokeCheck(label=label, payload=result.data)


def _test_client_transport(
    client: TestClient,
):
    def transport(
        method: str,
        path: str,
        query: dict[str, Any] | None,
        body: dict[str, Any] | None,
    ) -> Any:
        response = client.request(method, path, params=query, json=body)
        if response.status_code >= 400:
            raise RestClientError(
                status_code=response.status_code,
                payload=response.json(),
            )
        return response.json()

    return transport


def _assert_http_status(
    actual: int,
    expected: int,
    payload: Any,
) -> None:
    if actual != expected:
        raise AssertionError(
            f"Expected HTTP {expected}, got {actual}: {payload}",
        )


if __name__ == "__main__":
    main()
