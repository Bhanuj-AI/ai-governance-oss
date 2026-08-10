"""Phase 3 job orchestration for replay governance evidence.

This module deliberately coordinates existing application boundaries instead of
calling an evaluator, repository implementation, or graph database directly.
It turns a persisted replay execution into tenant-scoped evaluation,
cross-execution comparison, drift evidence, and one immutable ``ReplayResult``.
Every successful step writes a stable reference back to ``Replay`` first, which
makes worker redelivery safe and prevents completed work from being repeated.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Callable
from uuid import uuid4

from ai_governance.domain.jobs import Job, JobResult, JobStatus
from ai_governance.domain.replay import ReplayFailure, ReplayFailureStage, ReplayStatus
from ai_governance.domain.replay.errors import ReplayBaselineUnavailable
from ai_governance.repositories.replay_repository import ReplayRepository
from ai_governance.repositories.replay_result_repository import ReplayResultRepository
from ai_governance.services.evaluation_api_service import EvaluationApiService
from ai_governance.services.provider_installation_service import ProviderInstallationService
from ai_governance.services.replay_application_service import ReplaySourceResolver
from ai_governance.services.replay_governance import (
    ReplayBaselineResolver,
    ReplayComparisonService,
    ReplayDriftService,
    make_replay_result,
)
from ai_governance.tenancy.domain import TenantContext


class ReplayEvaluationJobHandler:
    """Run a ``REPLAY_EVALUATION`` job from persisted replay evidence.

    The handler owns orchestration only. Evaluation remains in
    :class:`EvaluationApiService`; baseline selection, comparison, and drift
    remain in their replay-governance services; immutable terminal evidence is
    stored through ``ReplayResultRepository``.

    A replay may be redelivered after any persistence boundary. In that case
    the handler reuses ``replay_evaluation_id``, ``baseline_evaluation_id``,
    ``comparison_id``, ``drift_id``, and an existing result instead of
    evaluating or creating evidence again. It never reruns the workflow
    execution. Cancellation and archival return a cancelled job result without
    deleting already-created governance evidence.
    """

    def __init__(
        self,
        *,
        replay_repository: ReplayRepository,
        result_repository: ReplayResultRepository,
        source_resolver: ReplaySourceResolver,
        evaluation_api_service: EvaluationApiService,
        provider_installation_service: ProviderInstallationService | None = None,
        baseline_resolver: ReplayBaselineResolver | None = None,
        comparison_service: ReplayComparisonService | None = None,
        drift_service: ReplayDriftService | None = None,
        clock: Callable[[], datetime] | None = None,
        id_generator: Callable[[], str] | None = None,
    ) -> None:
        self._replays = replay_repository
        self._results = result_repository
        self._source = source_resolver
        self._evaluations = evaluation_api_service
        self._provider_installations = provider_installation_service
        self._baselines = baseline_resolver or ReplayBaselineResolver(
            evaluation_api_service
        )
        self._comparisons = comparison_service or ReplayComparisonService()
        self._drift = drift_service or ReplayDriftService()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._ids = id_generator or (lambda: str(uuid4()))

    def handle(self, job: Job) -> JobResult:
        """Evaluate, compare, and finalize the replay represented by ``job``.

        The job must carry a tenant execution context and be linked to the
        replay's ``evaluation_job_id``. The durable sequence is:

        1. move ``EXECUTION_COMPLETED`` to ``EVALUATING`` when necessary;
        2. evaluate the replay execution, or load its stored evaluation;
        3. resolve and record a compatible source-execution baseline;
        4. move to ``COMPARING``, then record comparison and drift references;
        5. save one immutable result and finally mark the replay ``COMPLETED``.

        A completed replay returns its existing result reference immediately.
        Errors are converted to a failed job result after retaining an
        appropriately staged Replay failure. Baseline unavailability is treated
        as non-retryable; intermediate evidence is intentionally preserved.
        """
        context = self._context(job)
        replay_id = str(job.input_refs.get("replay_id", ""))
        replay = self._replays.get(
            replay_id, context.organization_id, context.project_id or ""
        )
        if replay is None or replay.evaluation_job_id != job.job_id:
            return JobResult(
                job.job_id,
                JobStatus.FAILED,
                None,
                "Replay evaluation linkage is invalid.",
            )
        if replay.status is ReplayStatus.COMPLETED and replay.result_id:
            return JobResult(
                job.job_id,
                JobStatus.SUCCEEDED,
                f"replay_result:{replay.result_id}",
                None,
            )
        if replay.status in {ReplayStatus.CANCELLED, ReplayStatus.ARCHIVED}:
            return JobResult(
                job.job_id,
                JobStatus.CANCELLED,
                None,
                "Replay is cancelled or archived.",
            )
        try:
            if replay.status is ReplayStatus.EXECUTION_COMPLETED:
                replay = self._replays.update(
                    replay.mark_evaluating(job.job_id, self._clock()), replay.version
                )
            if replay.status not in {ReplayStatus.EVALUATING, ReplayStatus.COMPARING}:
                return JobResult(
                    job.job_id,
                    JobStatus.FAILED,
                    None,
                    f"Replay cannot be evaluated from {replay.status.value}.",
                )
            if replay.cancel_requested_at:
                return self._cancel(replay, job)
            source_execution = self._source.get_execution(
                replay.source_execution_id, context
            )
            replay_execution = self._source.get_execution(
                replay.replay_execution_id or "", context
            )
            if source_execution is None or replay_execution is None:
                raise ValueError("Replay source or produced execution is unavailable.")
            provider = str(job.input_refs.get("evaluation_provider", ""))
            if not provider:
                raise ValueError("Replay evaluation provider is required.")
            provider_config = {}
            installation_id = job.input_refs.get("provider_installation_id")
            if installation_id:
                if self._provider_installations is None:
                    raise ValueError("Provider installations are unavailable in this worker.")
                installation, provider_config = self._provider_installations.resolve_runtime_config(
                    str(installation_id), context
                )
                if installation.provider_type != provider:
                    raise ValueError("Replay provider installation no longer matches its selected type.")
            if replay.replay_evaluation_id:
                replay_evaluation = self._evaluations.get_evaluation(
                    replay.replay_evaluation_id, context
                )
            else:
                evaluation_kwargs = {"context": context}
                if provider_config:
                    evaluation_kwargs["provider_config"] = provider_config
                replay_evaluation = self._evaluations.submit_evaluation(
                    replay_execution, provider, **evaluation_kwargs
                )
                replay = self._replays.update(
                    replay.record_replay_evaluation(
                        replay_evaluation.evaluation_id, self._clock()
                    ),
                    replay.version,
                )
            if replay.cancel_requested_at:
                return self._cancel(replay, job)
            strategy = str(job.input_refs.get("baseline_strategy", "LATEST_COMPATIBLE"))
            explicit = job.input_refs.get("explicit_baseline_evaluation_id")
            if replay.baseline_evaluation_id:
                baseline = self._evaluations.get_evaluation(
                    replay.baseline_evaluation_id, context
                )
                resolution = self._baselines.resolve(
                    source_execution_id=replay.source_execution_id,
                    replay_evaluation=replay_evaluation,
                    strategy="EXPLICIT",
                    explicit_evaluation_id=baseline.evaluation_id,
                    context=context,
                )
            else:
                resolution = self._baselines.resolve(
                    source_execution_id=replay.source_execution_id,
                    replay_evaluation=replay_evaluation,
                    strategy=strategy,
                    explicit_evaluation_id=str(explicit) if explicit else None,
                    context=context,
                )
                replay = self._replays.update(
                    replay.record_baseline_evaluation(
                        resolution.evaluation.evaluation_id, self._clock()
                    ),
                    replay.version,
                )
            if replay.status is ReplayStatus.EVALUATING:
                replay = self._replays.update(
                    replay.mark_comparing(self._clock()), replay.version
                )
            if replay.comparison_id is None:
                comparison = self._comparisons.compare(
                    replay_id=replay.replay_id,
                    source_execution_id=replay.source_execution_id,
                    replay_execution_id=replay.replay_execution_id or "",
                    baseline=resolution.evaluation,
                    replay=replay_evaluation,
                )
                comparison_id = f"replay-comparison:{replay.replay_id}"
                replay = self._replays.update(
                    replay.record_comparison(comparison_id, self._clock()),
                    replay.version,
                )
            else:
                comparison = self._comparisons.compare(
                    replay_id=replay.replay_id,
                    source_execution_id=replay.source_execution_id,
                    replay_execution_id=replay.replay_execution_id or "",
                    baseline=resolution.evaluation,
                    replay=replay_evaluation,
                )
            if replay.drift_id is None:
                threshold_policy = dict(
                    job.input_refs.get("drift_threshold_policy", {})
                )
                drift, drift_summary = self._drift.analyze(
                    resolution.evaluation, replay_evaluation, threshold_policy
                )
                drift_id = f"replay-drift:{replay.replay_id}"
                replay = self._replays.update(
                    replay.record_drift(drift_id, self._clock()), replay.version
                )
            else:
                _, drift_summary = self._drift.analyze(
                    resolution.evaluation,
                    replay_evaluation,
                    dict(job.input_refs.get("drift_threshold_policy", {})),
                )
            existing = self._results.get_by_replay(
                replay.replay_id, context.organization_id, context.project_id or ""
            )
            result = existing or make_replay_result(
                replay=replay,
                resolution=resolution,
                comparison_id=replay.comparison_id or "",
                drift_id=replay.drift_id or "",
                comparison_summary=self._comparisons.summary(
                    comparison, resolution.evaluation, replay_evaluation
                ),
                drift_summary=drift_summary,
                result_id=replay.result_id or self._ids(),
                now=self._clock(),
            )
            result = self._results.save(result)
            if replay.status is not ReplayStatus.COMPLETED:
                replay = self._replays.update(
                    replay.mark_completed(result.result_id, self._clock()),
                    replay.version,
                )
            return JobResult(
                job.job_id,
                JobStatus.SUCCEEDED,
                f"replay_result:{result.result_id}",
                None,
            )
        except Exception as error:
            return self._fail(replay, job, error)

    def _cancel(self, replay, job: Job) -> JobResult:
        """Persist cooperative cancellation at a safe Phase 3 boundary."""
        replay = self._replays.update(
            replay.mark_cancelled(self._clock()), replay.version
        )
        return JobResult(
            job.job_id, JobStatus.CANCELLED, None, "Replay cancellation requested."
        )

    def _fail(self, replay, job: Job, error: Exception) -> JobResult:
        """Record a structured terminal failure without cleaning up evidence."""
        if replay.status not in {
            ReplayStatus.EXECUTION_COMPLETED,
            ReplayStatus.EVALUATING,
            ReplayStatus.COMPARING,
        }:
            return JobResult(job.job_id, JobStatus.FAILED, None, str(error))
        stage = (
            ReplayFailureStage.BASELINE_RESOLUTION
            if isinstance(error, ReplayBaselineUnavailable)
            else ReplayFailureStage.EVALUATION
            if replay.replay_evaluation_id is None
            else ReplayFailureStage.COMPARISON
        )
        failure = ReplayFailure(
            type(error).__name__,
            str(error),
            stage,
            {
                "job_id": job.job_id,
                "retryable": not isinstance(error, ReplayBaselineUnavailable),
            },
            self._clock(),
        )
        self._replays.update(
            replay.mark_execution_failed(failure, self._clock()), replay.version
        )
        return JobResult(job.job_id, JobStatus.FAILED, None, str(error))

    @staticmethod
    def _context(job: Job) -> TenantContext:
        """Reconstruct the immutable tenant scope captured at submission time."""
        if job.execution_context is None:
            raise ValueError("Replay evaluation job is missing execution context.")
        scope = job.execution_context
        return TenantContext(
            scope.organization_id,
            scope.project_id,
            scope.actor_id,
            scope.submitted_request_id,
            scope.correlation_id,
        )
