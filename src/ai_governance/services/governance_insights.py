from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from ai_governance.domain.evaluation_result import EvaluationResult
from ai_governance.domain.experiments import (
    EvaluationRun,
    ExperimentCandidate,
    Leaderboard,
    LeaderboardEntry,
)
from ai_governance.domain.jobs import Job
from ai_governance.mcp.audit import MCPExecutionAuditLog, MCPExecutionAuditRecord
from ai_governance.repositories.evaluation_repository import EvaluationRepository
from ai_governance.repositories.evaluation_run_repository import (
    EvaluationRunRepository,
)
from ai_governance.repositories.experiment_candidate_repository import (
    ExperimentCandidateRepository,
)
from ai_governance.repositories.experiment_repository import ExperimentRepository
from ai_governance.repositories.job_repository import JobRepository
from ai_governance.repositories.leaderboard_repository import LeaderboardRepository
from ai_governance.services.evaluation_api_service import EvaluationNotFoundError
from ai_governance.services.experiments import (
    ExperimentCandidateNotFoundError,
    ExperimentNotFoundError,
)
from ai_governance.services.governance_api_service import GovernanceApiService
from ai_governance.services.job_api_service import JobNotFoundError

InsightStatus = Literal["SUCCEEDED", "FAILED", "PARTIAL", "UNKNOWN"]
InsightConfidence = Literal["HIGH", "MEDIUM", "LOW"]


@dataclass(frozen=True)
class GovernanceInsight:
    summary: str
    status: InsightStatus
    confidence: InsightConfidence
    evidence: list[dict[str, Any]] = field(default_factory=list)
    metrics: list[dict[str, Any]] = field(default_factory=list)
    related_resources: list[dict[str, Any]] = field(default_factory=list)
    recommended_next_steps: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class GovernanceReport:
    report_type: str
    report_format: str
    content: dict[str, Any] | str
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class ExperimentInsightService:
    """
    Builds evidence-first explanations for experiment outcomes.
    """

    def __init__(
        self,
        experiment_repository: ExperimentRepository,
        candidate_repository: ExperimentCandidateRepository,
        evaluation_run_repository: EvaluationRunRepository,
        evaluation_repository: EvaluationRepository,
        leaderboard_repository: LeaderboardRepository,
    ) -> None:
        self._experiment_repository = experiment_repository
        self._candidate_repository = candidate_repository
        self._evaluation_run_repository = evaluation_run_repository
        self._evaluation_repository = evaluation_repository
        self._leaderboard_repository = leaderboard_repository

    def summarize_experiment(
        self,
        experiment_id: str,
    ) -> GovernanceInsight:
        experiment = self._experiment(experiment_id)
        candidates = self._candidate_repository.find_by_experiment_id(
            experiment_id
        )
        runs = self._evaluation_run_repository.find_by_experiment_id(
            experiment_id
        )
        leaderboard = self._latest_leaderboard(experiment_id)
        winner = leaderboard.entries[0] if leaderboard and leaderboard.entries else None
        winner_candidate = (
            self._candidate_by_id(winner.candidate_id)
            if winner is not None
            else None
        )

        summary = (
            f"Experiment '{experiment.name}' has {len(candidates)} candidate(s), "
            f"{len(runs)} evaluation run(s), and status {experiment.status.value}."
        )
        if winner_candidate and winner:
            summary += (
                f" Current winner is '{winner_candidate.name}' with overall "
                f"score {winner.overall_score:.3f}."
            )

        return GovernanceInsight(
            summary=summary,
            status=_status_from_experiment(experiment.status.value, runs),
            confidence="HIGH" if leaderboard else "MEDIUM",
            evidence=[
                {
                    "kind": "experiment",
                    "experiment_id": experiment.experiment_id,
                    "name": experiment.name,
                    "status": experiment.status.value,
                },
                {
                    "kind": "candidate_count",
                    "count": len(candidates),
                },
                {
                    "kind": "evaluation_runs",
                    "statuses": _run_status_counts(runs),
                },
            ],
            metrics=_leaderboard_metrics(leaderboard),
            related_resources=[
                {"kind": "candidate", "id": candidate.candidate_id}
                for candidate in candidates
            ]
            + (
                [
                    {
                        "kind": "leaderboard",
                        "id": leaderboard.leaderboard_id,
                    }
                ]
                if leaderboard
                else []
            ),
            recommended_next_steps=_experiment_next_steps(
                candidates,
                runs,
                leaderboard,
            ),
        )

    def explain_candidate(
        self,
        experiment_id: str,
        candidate_id: str,
    ) -> GovernanceInsight:
        self._experiment(experiment_id)
        candidate = self._candidate_by_id(candidate_id)
        if candidate.experiment_id != experiment_id:
            raise ExperimentCandidateNotFoundError(candidate_id)

        runs = self._evaluation_run_repository.find_by_candidate_id(
            candidate_id
        )
        latest_run = _latest_run(runs)
        evaluation = (
            self._evaluation_repository.find_by_evaluation_id(
                latest_run.evaluation_result_id
            )
            if latest_run and latest_run.evaluation_result_id
            else None
        )
        entry = self._leaderboard_entry(experiment_id, candidate_id)

        return GovernanceInsight(
            summary=_candidate_summary(candidate, latest_run, entry),
            status=_status_from_candidate(latest_run, entry),
            confidence="HIGH" if evaluation or entry else "MEDIUM",
            evidence=[
                _candidate_evidence(candidate),
                *(
                    [_run_evidence(latest_run)]
                    if latest_run is not None
                    else []
                ),
            ],
            metrics=_evaluation_metrics(evaluation)
            + (_entry_metrics(entry) if entry else []),
            related_resources=[
                {
                    "kind": "experiment",
                    "id": experiment_id,
                },
                {
                    "kind": "candidate",
                    "id": candidate.candidate_id,
                },
            ]
            + (
                [
                    {
                        "kind": "evaluation",
                        "id": latest_run.evaluation_result_id,
                    }
                ]
                if latest_run and latest_run.evaluation_result_id
                else []
            ),
            recommended_next_steps=_candidate_next_steps(latest_run, entry),
        )

    def compare_candidates(
        self,
        experiment_id: str,
    ) -> GovernanceInsight:
        self._experiment(experiment_id)
        leaderboard = self._latest_leaderboard(experiment_id)
        candidates = self._candidate_repository.find_by_experiment_id(
            experiment_id
        )
        if leaderboard and len(leaderboard.entries) >= 2:
            first, second = leaderboard.entries[:2]
            first_candidate = self._candidate_by_id(first.candidate_id)
            second_candidate = self._candidate_by_id(second.candidate_id)
            score_delta = first.overall_score - second.overall_score
            summary = (
                f"'{first_candidate.name}' leads '{second_candidate.name}' "
                f"by {score_delta:.3f} overall score point(s)."
            )
            metrics = _entry_metrics(first, prefix="winner_") + _entry_metrics(
                second,
                prefix="runner_up_",
            )
            evidence = [
                {
                    "kind": "leaderboard_comparison",
                    "winner_candidate_id": first.candidate_id,
                    "runner_up_candidate_id": second.candidate_id,
                    "score_delta": score_delta,
                    "winner_reason": first.reason,
                    "runner_up_reason": second.reason,
                }
            ]
            confidence: InsightConfidence = "HIGH"
        else:
            summary = (
                f"Experiment '{experiment_id}' does not yet have enough "
                "leaderboard evidence to compare candidates."
            )
            metrics = []
            evidence = [{"kind": "candidate_count", "count": len(candidates)}]
            confidence = "LOW"

        return GovernanceInsight(
            summary=summary,
            status="SUCCEEDED" if leaderboard and len(leaderboard.entries) >= 2 else "PARTIAL",
            confidence=confidence,
            evidence=evidence,
            metrics=metrics,
            related_resources=[
                {"kind": "candidate", "id": candidate.candidate_id}
                for candidate in candidates
            ],
            recommended_next_steps=[
                "Inspect metric-level leaderboard evidence.",
                "Review candidate configuration differences before acting.",
            ],
        )

    def _experiment(
        self,
        experiment_id: str,
    ):
        experiment = self._experiment_repository.find_by_id(experiment_id)
        if experiment is None:
            raise ExperimentNotFoundError(experiment_id)
        return experiment

    def _candidate_by_id(
        self,
        candidate_id: str,
    ) -> ExperimentCandidate:
        candidate = self._candidate_repository.find_by_id(candidate_id)
        if candidate is None:
            raise ExperimentCandidateNotFoundError(candidate_id)
        return candidate

    def _latest_leaderboard(
        self,
        experiment_id: str,
    ) -> Leaderboard | None:
        leaderboards = self._leaderboard_repository.find_by_experiment_id(
            experiment_id
        )
        return max(
            leaderboards,
            key=lambda item: (item.generated_at, item.leaderboard_id),
            default=None,
        )

    def _leaderboard_entry(
        self,
        experiment_id: str,
        candidate_id: str,
    ) -> LeaderboardEntry | None:
        leaderboard = self._latest_leaderboard(experiment_id)
        if leaderboard is None:
            return None
        return next(
            (
                entry
                for entry in leaderboard.entries
                if entry.candidate_id == candidate_id
            ),
            None,
        )


class ExecutionInvestigationService:
    """
    Correlates audit, job, and evaluation evidence for investigation.
    """

    def __init__(
        self,
        audit_log: MCPExecutionAuditLog,
        job_repository: JobRepository,
        evaluation_repository: EvaluationRepository,
    ) -> None:
        self._audit_log = audit_log
        self._job_repository = job_repository
        self._evaluation_repository = evaluation_repository

    def by_correlation(
        self,
        correlation_id: str,
    ) -> GovernanceInsight:
        audits = self._audit_log.find_by_correlation(correlation_id)
        jobs = self._jobs_for_audits(audits)
        evaluations = self._evaluations_for_jobs(jobs)
        return self._investigation(
            summary=(
                f"Correlation '{correlation_id}' has {len(audits)} audit "
                f"record(s), {len(jobs)} job(s), and {len(evaluations)} "
                "evaluation result(s)."
            ),
            audits=audits,
            jobs=jobs,
            evaluations=evaluations,
            anchor={"kind": "correlation", "id": correlation_id},
        )

    def by_job(
        self,
        job_id: str,
    ) -> GovernanceInsight:
        job = self._job_repository.find_by_id(job_id)
        if job is None:
            raise JobNotFoundError(job_id)
        audits = [
            record
            for record in self._audit_log.list_records(limit=500)
            if record.job_id == job_id
        ]
        evaluations = self._evaluations_for_jobs([job])
        return self._investigation(
            summary=f"Job '{job_id}' is {job.status.value}.",
            audits=audits,
            jobs=[job],
            evaluations=evaluations,
            anchor={"kind": "job", "id": job_id},
        )

    def by_evaluation(
        self,
        evaluation_id: str,
    ) -> GovernanceInsight:
        evaluation = self._evaluation_repository.find_by_evaluation_id(
            evaluation_id
        )
        if evaluation is None:
            raise EvaluationNotFoundError(evaluation_id=evaluation_id)
        jobs = [
            job
            for job in self._job_repository.list_jobs(limit=500)
            if job.result_ref == f"evaluation:{evaluation_id}"
            or job.input_refs.get("evaluation_id") == evaluation_id
            or job.input_refs.get("execution_id") == evaluation.execution_id
        ]
        audits = self._audits_for_jobs(jobs)
        return self._investigation(
            summary=(
                f"Evaluation '{evaluation_id}' belongs to execution "
                f"'{evaluation.execution_id}'."
            ),
            audits=audits,
            jobs=jobs,
            evaluations=[evaluation],
            anchor={"kind": "evaluation", "id": evaluation_id},
        )

    def by_audit(
        self,
        audit_id: str,
    ) -> GovernanceInsight:
        audit = self._audit_log.get(audit_id)
        if audit is None:
            raise ValueError(f"MCP audit record '{audit_id}' was not found.")
        jobs = self._jobs_for_audits([audit])
        evaluations = self._evaluations_for_jobs(jobs)
        return self._investigation(
            summary=(
                f"Audit '{audit_id}' for tool '{audit.tool_name}' is "
                f"{audit.status}."
            ),
            audits=[audit],
            jobs=jobs,
            evaluations=evaluations,
            anchor={"kind": "audit", "id": audit_id},
        )

    def _investigation(
        self,
        *,
        summary: str,
        audits: list[MCPExecutionAuditRecord],
        jobs: list[Job],
        evaluations: list[EvaluationResult],
        anchor: dict[str, str],
    ) -> GovernanceInsight:
        statuses = [job.status.value for job in jobs] + [
            audit.status for audit in audits
        ]
        return GovernanceInsight(
            summary=summary,
            status=_investigation_status(statuses),
            confidence="HIGH" if audits or jobs or evaluations else "LOW",
            evidence=[
                *[_audit_evidence(record) for record in audits],
                *[_job_evidence(job) for job in jobs],
                *[_evaluation_evidence(result) for result in evaluations],
            ],
            metrics=[
                metric
                for result in evaluations
                for metric in _evaluation_metrics(result)
            ],
            related_resources=[
                anchor,
                *[
                    {"kind": "audit", "id": audit.audit_id}
                    for audit in audits
                ],
                *[{"kind": "job", "id": job.job_id} for job in jobs],
                *[
                    {
                        "kind": "evaluation",
                        "id": evaluation.evaluation_id,
                    }
                    for evaluation in evaluations
                ],
            ],
            recommended_next_steps=_investigation_next_steps(
                audits,
                jobs,
                evaluations,
            ),
        )

    def _jobs_for_audits(
        self,
        audits: list[MCPExecutionAuditRecord],
    ) -> list[Job]:
        jobs: list[Job] = []
        for audit in audits:
            if audit.job_id is None:
                continue
            job = self._job_repository.find_by_id(audit.job_id)
            if job is not None:
                jobs.append(job)
        return _unique_jobs(jobs)

    def _audits_for_jobs(
        self,
        jobs: list[Job],
    ) -> list[MCPExecutionAuditRecord]:
        job_ids = {job.job_id for job in jobs}
        return [
            audit
            for audit in self._audit_log.list_records(limit=500)
            if audit.job_id in job_ids
        ]

    def _evaluations_for_jobs(
        self,
        jobs: list[Job],
    ) -> list[EvaluationResult]:
        evaluations: list[EvaluationResult] = []
        for job in jobs:
            evaluation_id = _evaluation_id_from_job(job)
            if evaluation_id is None:
                continue
            evaluation = self._evaluation_repository.find_by_evaluation_id(
                evaluation_id
            )
            if evaluation is not None:
                evaluations.append(evaluation)
        return _unique_evaluations(evaluations)


class DriftExplanationService:
    """
    Explains existing drift analysis output without adding drift logic.
    """

    def __init__(
        self,
        evaluation_repository: EvaluationRepository,
    ) -> None:
        self._evaluation_repository = evaluation_repository
        self._governance_service = GovernanceApiService(
            evaluation_repository
        )

    def explain_drift(
        self,
        drift_id: str,
    ) -> GovernanceInsight:
        baseline_id, candidate_id = _parse_drift_id(drift_id)
        drift = self._governance_service.analyze_drift(
            baseline_evaluation_id=baseline_id,
            candidate_evaluation_id=candidate_id,
        )
        changed = drift.changed_metrics + drift.new_metrics + drift.removed_metrics
        return GovernanceInsight(
            summary=(
                f"Drift between '{baseline_id}' and '{candidate_id}' is "
                f"{drift.severity.value}."
            ),
            status="SUCCEEDED",
            confidence="HIGH",
            evidence=[
                {
                    "kind": "drift",
                    "baseline_evaluation_id": baseline_id,
                    "candidate_evaluation_id": candidate_id,
                    "severity": drift.severity.value,
                    "score_difference": drift.score_difference,
                }
            ],
            metrics=[
                {
                    "name": metric.metric_name,
                    "baseline_value": metric.baseline_value,
                    "candidate_value": metric.candidate_value,
                    "score_difference": metric.score_difference,
                }
                for metric in changed
            ],
            related_resources=[
                {"kind": "evaluation", "id": baseline_id},
                {"kind": "evaluation", "id": candidate_id},
            ],
            recommended_next_steps=_drift_next_steps(drift.severity.value),
        )

    def explain_evaluation(
        self,
        evaluation_id: str,
    ) -> GovernanceInsight:
        evaluation = self._evaluation_repository.find_by_evaluation_id(
            evaluation_id
        )
        if evaluation is None:
            raise EvaluationNotFoundError(evaluation_id=evaluation_id)
        history = sorted(
            self._evaluation_repository.find_by_execution_id(
                evaluation.execution_id
            ),
            key=lambda result: (
                result.created_at or datetime.min.replace(tzinfo=UTC),
                result.evaluation_id,
            ),
        )
        index = next(
            (
                position
                for position, item in enumerate(history)
                if item.evaluation_id == evaluation_id
            ),
            -1,
        )
        if index <= 0:
            return GovernanceInsight(
                summary=(
                    f"Evaluation '{evaluation_id}' has no prior evaluation "
                    "in the same execution to use as a drift baseline."
                ),
                status="PARTIAL",
                confidence="MEDIUM",
                evidence=[_evaluation_evidence(evaluation)],
                metrics=_evaluation_metrics(evaluation),
                related_resources=[
                    {"kind": "evaluation", "id": evaluation_id}
                ],
                recommended_next_steps=[
                    "Capture another evaluation for this execution before drift comparison.",
                ],
            )

        baseline = history[index - 1]
        return self.explain_drift(
            _drift_id(baseline.evaluation_id, evaluation_id)
        )


class GovernanceReportService:
    """
    Generates evidence reports from Phase 3 insight services.
    """

    def __init__(
        self,
        experiment_insights: ExperimentInsightService,
        investigations: ExecutionInvestigationService,
        drift_explanations: DriftExplanationService,
        evaluation_repository: EvaluationRepository,
        audit_log: MCPExecutionAuditLog,
    ) -> None:
        self._experiment_insights = experiment_insights
        self._investigations = investigations
        self._drift_explanations = drift_explanations
        self._evaluation_repository = evaluation_repository
        self._audit_log = audit_log

    def experiment_report(
        self,
        experiment_id: str,
        report_format: str = "json",
    ) -> GovernanceReport:
        return self._report(
            "experiment_report",
            self._experiment_insights.summarize_experiment(experiment_id),
            report_format,
        )

    def evaluation_report(
        self,
        evaluation_id: str,
        report_format: str = "json",
    ) -> GovernanceReport:
        evaluation = self._evaluation_repository.find_by_evaluation_id(
            evaluation_id
        )
        if evaluation is None:
            raise EvaluationNotFoundError(evaluation_id=evaluation_id)
        insight = GovernanceInsight(
            summary=(
                f"Evaluation '{evaluation_id}' contains "
                f"{len(evaluation.metrics)} metric(s)."
            ),
            status="SUCCEEDED",
            confidence="HIGH",
            evidence=[_evaluation_evidence(evaluation)],
            metrics=_evaluation_metrics(evaluation),
            related_resources=[
                {"kind": "evaluation", "id": evaluation_id},
                {"kind": "execution", "id": evaluation.execution_id},
            ],
            recommended_next_steps=[
                "Review metric values and provider metadata.",
            ],
        )
        return self._report("evaluation_report", insight, report_format)

    def drift_report(
        self,
        drift_id: str,
        report_format: str = "json",
    ) -> GovernanceReport:
        return self._report(
            "drift_report",
            self._drift_explanations.explain_drift(drift_id),
            report_format,
        )

    def investigation_report(
        self,
        correlation_id: str,
        report_format: str = "json",
    ) -> GovernanceReport:
        return self._report(
            "execution_investigation_report",
            self._investigations.by_correlation(correlation_id),
            report_format,
        )

    def mcp_audit_report(
        self,
        audit_id: str,
        report_format: str = "json",
    ) -> GovernanceReport:
        audit = self._audit_log.get(audit_id)
        if audit is None:
            raise ValueError(f"MCP audit record '{audit_id}' was not found.")
        return self._report(
            "mcp_audit_report",
            self._investigations.by_audit(audit_id),
            report_format,
        )

    def _report(
        self,
        report_type: str,
        insight: GovernanceInsight,
        report_format: str,
    ) -> GovernanceReport:
        normalized_format = report_format.lower()
        if normalized_format == "json":
            content: dict[str, Any] | str = _insight_payload(insight)
        elif normalized_format == "markdown":
            content = _markdown_report(report_type, insight)
        else:
            raise ValueError("Report format must be 'json' or 'markdown'.")
        return GovernanceReport(
            report_type=report_type,
            report_format=normalized_format,
            content=content,
        )


def _insight_payload(insight: GovernanceInsight) -> dict[str, Any]:
    return {
        "summary": insight.summary,
        "status": insight.status,
        "confidence": insight.confidence,
        "evidence": insight.evidence,
        "metrics": insight.metrics,
        "related_resources": insight.related_resources,
        "recommended_next_steps": insight.recommended_next_steps,
        "generated_at": insight.generated_at,
    }


def _markdown_report(
    report_type: str,
    insight: GovernanceInsight,
) -> str:
    lines = [
        f"# {report_type.replace('_', ' ').title()}",
        "",
        f"Status: {insight.status}",
        f"Confidence: {insight.confidence}",
        "",
        "## Summary",
        "",
        insight.summary,
        "",
        "## Evidence",
    ]
    lines.extend(f"- {item}" for item in insight.evidence)
    lines.extend(["", "## Metrics"])
    lines.extend(f"- {item}" for item in insight.metrics)
    lines.extend(["", "## Recommended Next Steps"])
    lines.extend(f"- {item}" for item in insight.recommended_next_steps)
    return "\n".join(lines)


def _status_from_experiment(
    experiment_status: str,
    runs: list[EvaluationRun],
) -> InsightStatus:
    if experiment_status == "COMPLETED":
        return "SUCCEEDED"
    if any(run.status.value == "FAILED" for run in runs):
        return "FAILED"
    if runs:
        return "PARTIAL"
    return "UNKNOWN"


def _status_from_candidate(
    run: EvaluationRun | None,
    entry: LeaderboardEntry | None,
) -> InsightStatus:
    if run is None:
        return "UNKNOWN"
    if run.status.value == "FAILED":
        return "FAILED"
    if run.status.value == "COMPLETED" or entry is not None:
        return "SUCCEEDED"
    return "PARTIAL"


def _run_status_counts(runs: list[EvaluationRun]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for run in runs:
        counts[run.status.value] = counts.get(run.status.value, 0) + 1
    return counts


def _leaderboard_metrics(
    leaderboard: Leaderboard | None,
) -> list[dict[str, Any]]:
    if leaderboard is None:
        return []
    return [
        {
            "candidate_id": entry.candidate_id,
            "rank": entry.rank,
            "overall_score": entry.overall_score,
            "metrics": entry.metrics,
            "cost": entry.cost,
            "latency": entry.latency,
        }
        for entry in leaderboard.entries
    ]


def _entry_metrics(
    entry: LeaderboardEntry,
    prefix: str = "",
) -> list[dict[str, Any]]:
    return [
        {
            "name": f"{prefix}overall_score",
            "value": entry.overall_score,
            "candidate_id": entry.candidate_id,
        },
        *[
            {
                "name": f"{prefix}{name}",
                "value": value,
                "candidate_id": entry.candidate_id,
            }
            for name, value in entry.metrics.items()
        ],
    ]


def _evaluation_metrics(
    evaluation: EvaluationResult | None,
) -> list[dict[str, Any]]:
    if evaluation is None:
        return []
    return [
        {
            "name": metric.metric_name,
            "value": metric.metric_value,
            "explanation": metric.explanation,
        }
        for metric in evaluation.metrics
    ]


def _candidate_summary(
    candidate: ExperimentCandidate,
    run: EvaluationRun | None,
    entry: LeaderboardEntry | None,
) -> str:
    if entry is not None:
        return (
            f"Candidate '{candidate.name}' ranks #{entry.rank} with overall "
            f"score {entry.overall_score:.3f}."
        )
    if run is not None:
        return (
            f"Candidate '{candidate.name}' latest run is {run.status.value}."
        )
    return f"Candidate '{candidate.name}' has not been evaluated yet."


def _candidate_evidence(
    candidate: ExperimentCandidate,
) -> dict[str, Any]:
    return {
        "kind": "candidate_configuration",
        "candidate_id": candidate.candidate_id,
        "prompt": f"{candidate.prompt_id}:{candidate.prompt_version}",
        "model": f"{candidate.model_id}:{candidate.model_version}",
        "dataset": f"{candidate.dataset_id}:{candidate.dataset_version}",
        "provider": candidate.evaluation_provider,
        "temperature": candidate.temperature,
        "top_p": candidate.top_p,
        "max_tokens": candidate.max_tokens,
    }


def _run_evidence(
    run: EvaluationRun,
) -> dict[str, Any]:
    return {
        "kind": "evaluation_run",
        "run_id": run.run_id,
        "status": run.status.value,
        "evaluation_result_id": run.evaluation_result_id,
    }


def _evaluation_evidence(
    evaluation: EvaluationResult,
) -> dict[str, Any]:
    return {
        "kind": "evaluation",
        "evaluation_id": evaluation.evaluation_id,
        "execution_id": evaluation.execution_id,
        "provider": evaluation.evaluator_type,
        "provider_version": evaluation.evaluator_version,
        "metric_count": len(evaluation.metrics),
    }


def _job_evidence(job: Job) -> dict[str, Any]:
    return {
        "kind": "job",
        "job_id": job.job_id,
        "job_type": job.job_type.value,
        "status": job.status.value,
        "input_refs": job.input_refs,
        "result_ref": job.result_ref,
        "failure_reason": job.failure_reason,
    }


def _audit_evidence(record: MCPExecutionAuditRecord) -> dict[str, Any]:
    return {
        "kind": "mcp_audit",
        "audit_id": record.audit_id,
        "tool_name": record.tool_name,
        "status": record.status,
        "request_id": record.request_id,
        "correlation_id": record.correlation_id,
        "job_id": record.job_id,
        "error_code": record.error_code,
        "error_message": record.error_message,
    }


def _experiment_next_steps(
    candidates: list[ExperimentCandidate],
    runs: list[EvaluationRun],
    leaderboard: Leaderboard | None,
) -> list[str]:
    if not candidates:
        return ["Add candidates before requesting experiment insights."]
    if not runs:
        return ["Run the experiment to generate evaluation evidence."]
    if leaderboard is None:
        return ["Generate or inspect the leaderboard before selecting a winner."]
    return [
        "Review metric-level leaderboard evidence.",
        "Inspect operational trade-offs such as cost and latency.",
    ]


def _candidate_next_steps(
    run: EvaluationRun | None,
    entry: LeaderboardEntry | None,
) -> list[str]:
    if run is None:
        return ["Run the candidate before drawing quality conclusions."]
    if run.status.value == "FAILED":
        return ["Investigate the failed evaluation run and provider response."]
    if entry is None:
        return ["Generate a leaderboard to compare this candidate."]
    return ["Compare this candidate with adjacent leaderboard ranks."]


def _investigation_next_steps(
    audits: list[MCPExecutionAuditRecord],
    jobs: list[Job],
    evaluations: list[EvaluationResult],
) -> list[str]:
    steps: list[str] = []
    if any(audit.status == "FAILED" for audit in audits):
        steps.append("Inspect MCP audit error details.")
    if any(job.status.value == "FAILED" for job in jobs):
        steps.append("Inspect job failure_reason and worker logs.")
    if not evaluations:
        steps.append("Check whether evaluation persistence completed.")
    if not steps:
        steps.append("Review related resources for operational context.")
    return steps


def _drift_next_steps(severity: str) -> list[str]:
    if severity == "HIGH":
        return [
            "Inspect changed metrics before deployment decisions.",
            "Compare provider metadata and execution inputs.",
        ]
    if severity == "NONE":
        return ["No drift response is required; keep monitoring future runs."]
    return [
        "Review changed metrics and candidate/evaluation context.",
    ]


def _latest_run(runs: list[EvaluationRun]) -> EvaluationRun | None:
    return max(
        runs,
        key=lambda run: (
            run.completed_at or run.started_at or datetime.min.replace(tzinfo=UTC),
            run.run_id,
        ),
        default=None,
    )


def _investigation_status(statuses: list[str]) -> InsightStatus:
    if any(status == "FAILED" for status in statuses):
        return "FAILED"
    if any(status in {"STARTED", "RUNNING", "QUEUED"} for status in statuses):
        return "PARTIAL"
    if statuses:
        return "SUCCEEDED"
    return "UNKNOWN"


def _evaluation_id_from_job(job: Job) -> str | None:
    if job.result_ref and job.result_ref.startswith("evaluation:"):
        return job.result_ref.split(":", maxsplit=1)[1]
    value = job.input_refs.get("evaluation_id")
    return str(value) if value is not None else None


def _unique_jobs(jobs: list[Job]) -> list[Job]:
    seen: set[str] = set()
    unique: list[Job] = []
    for job in jobs:
        if job.job_id not in seen:
            seen.add(job.job_id)
            unique.append(job)
    return unique


def _unique_evaluations(
    evaluations: list[EvaluationResult],
) -> list[EvaluationResult]:
    seen: set[str] = set()
    unique: list[EvaluationResult] = []
    for evaluation in evaluations:
        if evaluation.evaluation_id not in seen:
            seen.add(evaluation.evaluation_id)
            unique.append(evaluation)
    return unique


def _parse_drift_id(drift_id: str) -> tuple[str, str]:
    if ".." in drift_id:
        baseline, candidate = drift_id.split("..", maxsplit=1)
    elif ":" in drift_id:
        baseline, candidate = drift_id.split(":", maxsplit=1)
    else:
        raise ValueError(
            "drift_id must be formatted as 'baseline..candidate'."
        )
    if not baseline.strip() or not candidate.strip():
        raise ValueError(
            "drift_id must include baseline and candidate evaluation IDs."
        )
    return baseline.strip(), candidate.strip()


def _drift_id(
    baseline_evaluation_id: str,
    candidate_evaluation_id: str,
) -> str:
    return f"{baseline_evaluation_id}..{candidate_evaluation_id}"
