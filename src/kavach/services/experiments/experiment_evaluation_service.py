from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from kavach.domain.evaluation_result import EvaluationResult
from kavach.domain.experiments import (
    CandidateComparison,
    CandidateRanking,
    EvaluationRun,
    EvaluationRunStatus,
    Experiment,
    ExperimentCandidate,
    ExperimentStatus,
)
from kavach.domain.history import EvaluationMetricComparison
from kavach.domain.workflow_execution import WorkflowExecution
from kavach.evaluation.evaluation_service import EvaluationService
from kavach.repositories.evaluation_repository import EvaluationRepository
from kavach.repositories.evaluation_run_repository import (
    EvaluationRunRepository,
)
from kavach.repositories.experiment_candidate_repository import (
    ExperimentCandidateRepository,
)
from kavach.repositories.model_repository import ModelRepository
from kavach.services.experiments.experiment_service import (
    ExperimentLifecycleError,
    ExperimentService,
)
from kavach.services.experiments.winner_selection import (
    HighestOverallScoreSelectionStrategy,
    WinnerSelectionStrategy,
)


class ExperimentEvaluationError(Exception):
    """
    Raised when experiment execution or ranking cannot proceed.
    """


class ExperimentEvaluationService:
    """
    Orchestrates experiment execution, comparison, and winner selection.
    """

    def __init__(
        self,
        experiment_service: ExperimentService,
        candidate_repository: ExperimentCandidateRepository,
        evaluation_run_repository: EvaluationRunRepository,
        evaluation_repository: EvaluationRepository,
        model_repository: ModelRepository,
        evaluation_service: EvaluationService,
        workflow_execution_factory: Callable[
            [Experiment, ExperimentCandidate, str],
            WorkflowExecution,
        ],
        winner_selection_strategy: WinnerSelectionStrategy | None = None,
        id_generator: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
        allow_mixed_providers: bool = False,
    ) -> None:
        self._experiment_service = experiment_service
        self._candidate_repository = candidate_repository
        self._evaluation_run_repository = evaluation_run_repository
        self._evaluation_repository = evaluation_repository
        self._model_repository = model_repository
        self._evaluation_service = evaluation_service
        self._workflow_execution_factory = workflow_execution_factory
        self._winner_selection_strategy = (
            winner_selection_strategy
            or HighestOverallScoreSelectionStrategy()
        )
        self._id_generator = id_generator or (lambda: str(uuid4()))
        self._clock = clock or (lambda: datetime.now(UTC))
        self._allow_mixed_providers = allow_mixed_providers

    def execute_experiment(
        self,
        experiment_id: str,
    ) -> list[EvaluationRun]:
        """
        Execute every candidate belonging to one experiment.
        """

        experiment = self._experiment_service.get_experiment(experiment_id)
        candidates = self._candidate_repository.find_by_experiment_id(
            experiment_id
        )

        if not candidates:
            raise ExperimentEvaluationError(
                f"Experiment '{experiment_id}' has no candidates."
            )

        self._validate_candidates(candidates)

        if experiment.status == ExperimentStatus.DRAFT:
            experiment = self._experiment_service.start_experiment(
                experiment_id
            )
        elif experiment.status != ExperimentStatus.RUNNING:
            raise ExperimentLifecycleError(
                "Only draft or running experiments may be executed."
            )

        runs: list[EvaluationRun] = []
        has_failures = False

        for candidate in candidates:
            pending_run = EvaluationRun(
                run_id=self._id_generator(),
                experiment_id=experiment.experiment_id,
                candidate_id=candidate.candidate_id,
                dataset_version=candidate.dataset_version,
                evaluation_provider=candidate.evaluation_provider,
                evaluation_result_id=None,
                started_at=None,
                completed_at=None,
                status=EvaluationRunStatus.PENDING,
            )
            self._evaluation_run_repository.save(pending_run)

            running_run = replace(
                pending_run,
                started_at=self._clock(),
                status=EvaluationRunStatus.RUNNING,
            )
            self._evaluation_run_repository.save(running_run)

            try:
                execution = self._workflow_execution_factory(
                    experiment,
                    candidate,
                    running_run.run_id,
                )
                result = self._evaluation_service.evaluate(execution)
                self._evaluation_repository.save(result)

                completed_run = replace(
                    running_run,
                    evaluation_result_id=result.evaluation_id,
                    completed_at=self._clock(),
                    status=EvaluationRunStatus.COMPLETED,
                )
                self._evaluation_run_repository.save(completed_run)
                runs.append(completed_run)
            except Exception:
                failed_run = replace(
                    running_run,
                    completed_at=self._clock(),
                    status=EvaluationRunStatus.FAILED,
                )
                self._evaluation_run_repository.save(failed_run)
                runs.append(failed_run)
                has_failures = True

        if has_failures:
            self._experiment_service.fail_experiment(experiment_id)
        else:
            self._experiment_service.complete_experiment(experiment_id)

        return runs

    def list_evaluation_runs(
        self,
        experiment_id: str,
    ) -> list[EvaluationRun]:
        """
        Return every evaluation run for one experiment.
        """

        return self._evaluation_run_repository.find_by_experiment_id(
            experiment_id
        )

    def compare_candidates(
        self,
        experiment_id: str,
        baseline_candidate_id: str,
        candidate_candidate_id: str,
    ) -> CandidateComparison:
        """
        Compare two experiment candidates using their latest completed runs.
        """

        baseline_candidate = self._candidate(candidate_candidate_id=baseline_candidate_id)
        candidate = self._candidate(candidate_candidate_id=candidate_candidate_id)
        self._ensure_candidates_belong_to_experiment(
            experiment_id,
            baseline_candidate,
            candidate,
        )

        baseline_result = self._latest_completed_result(
            experiment_id=experiment_id,
            candidate_id=baseline_candidate_id,
        )
        candidate_result = self._latest_completed_result(
            experiment_id=experiment_id,
            candidate_id=candidate_candidate_id,
        )

        baseline_score = self._overall_score(baseline_result)
        candidate_score = self._overall_score(candidate_result)
        winner = (
            candidate
            if candidate_score > baseline_score
            else baseline_candidate
        )

        baseline_model = self._model_repository.find_by_id(
            baseline_candidate.model_id
        )
        candidate_model = self._model_repository.find_by_id(
            candidate.model_id
        )

        return CandidateComparison(
            experiment_id=experiment_id,
            baseline_candidate_id=baseline_candidate.candidate_id,
            candidate_candidate_id=candidate.candidate_id,
            baseline_candidate=baseline_candidate,
            candidate=candidate,
            winner=winner,
            metric_comparisons=self._metric_comparisons(
                baseline_result,
                candidate_result,
            ),
            overall_score=max(baseline_score, candidate_score),
            baseline_overall_score=baseline_score,
            candidate_overall_score=candidate_score,
            cost_delta=self._cost_delta(
                baseline_model.cost if baseline_model is not None else None,
                candidate_model.cost if candidate_model is not None else None,
            ),
            latency_delta=self._numeric_delta(
                baseline_model.latency if baseline_model is not None else None,
                candidate_model.latency if candidate_model is not None else None,
            ),
            reason=(
                f"Winner selected by higher overall score: {winner.candidate_id}."
            ),
            prompt_id_changed=baseline_candidate.prompt_id
            != candidate.prompt_id,
            prompt_version_changed=baseline_candidate.prompt_version
            != candidate.prompt_version,
            model_id_changed=baseline_candidate.model_id
            != candidate.model_id,
            model_version_changed=baseline_candidate.model_version
            != candidate.model_version,
            dataset_id_changed=baseline_candidate.dataset_id
            != candidate.dataset_id,
            dataset_version_changed=baseline_candidate.dataset_version
            != candidate.dataset_version,
            evaluation_provider_changed=(
                baseline_candidate.evaluation_provider
                != candidate.evaluation_provider
            ),
            temperature_changed=baseline_candidate.temperature
            != candidate.temperature,
            top_p_changed=baseline_candidate.top_p != candidate.top_p,
            max_tokens_changed=baseline_candidate.max_tokens
            != candidate.max_tokens,
            metadata_changed=baseline_candidate.metadata != candidate.metadata,
        )

    def compare_experiment_candidates(
        self,
        experiment_id: str,
    ) -> list[CandidateComparison]:
        """
        Compare every non-winning candidate against the selected winner.
        """

        rankings = self.rank_candidates(experiment_id)
        if len(rankings) < 2:
            return []

        winner = rankings[0].candidate

        return [
            self.compare_candidates(
                experiment_id=experiment_id,
                baseline_candidate_id=winner.candidate_id,
                candidate_candidate_id=ranking.candidate.candidate_id,
            )
            for ranking in rankings[1:]
        ]

    def rank_candidates(
        self,
        experiment_id: str,
    ) -> list[CandidateRanking]:
        """
        Rank candidates by overall score using their latest completed runs.
        """

        candidates = self._candidate_repository.find_by_experiment_id(
            experiment_id
        )
        if not candidates:
            raise ExperimentEvaluationError(
                f"Experiment '{experiment_id}' has no candidates."
            )

        rankings = [
            CandidateRanking(
                experiment_id=experiment_id,
                candidate=candidate,
                evaluation_run_id=run.run_id,
                evaluation_result_id=cast(str, run.evaluation_result_id),
                overall_score=self._overall_score(result),
                rank=0,
            )
            for candidate in candidates
            for run, result in [self._latest_completed_run_and_result(
                experiment_id,
                candidate.candidate_id,
            )]
        ]
        rankings.sort(
            key=lambda ranking: (
                ranking.overall_score,
                ranking.candidate.candidate_id,
            ),
            reverse=True,
        )

        return [
            replace(ranking, rank=index)
            for index, ranking in enumerate(rankings, start=1)
        ]

    def select_winner(
        self,
        experiment_id: str,
    ) -> CandidateRanking:
        """
        Return the winning candidate ranking for one experiment.
        """

        rankings = self.rank_candidates(experiment_id)
        winner = self._winner_selection_strategy.select_winner(rankings)

        return next(
            ranking
            for ranking in rankings
            if ranking.candidate.candidate_id == winner.candidate.candidate_id
        )

    def _validate_candidates(
        self,
        candidates: list[ExperimentCandidate],
    ) -> None:
        dataset_versions = {candidate.dataset_version for candidate in candidates}
        if len(dataset_versions) != 1:
            raise ExperimentEvaluationError(
                "Every candidate must use the same dataset version."
            )

        providers = {candidate.evaluation_provider for candidate in candidates}
        if not self._allow_mixed_providers and len(providers) != 1:
            raise ExperimentEvaluationError(
                "Every candidate must use the same evaluation provider."
            )

    def _candidate(
        self,
        candidate_candidate_id: str,
    ) -> ExperimentCandidate:
        candidate = self._candidate_repository.find_by_id(candidate_candidate_id)
        if candidate is None:
            raise ExperimentEvaluationError(
                f"Candidate '{candidate_candidate_id}' does not exist."
            )

        return candidate

    @staticmethod
    def _ensure_candidates_belong_to_experiment(
        experiment_id: str,
        baseline_candidate: ExperimentCandidate,
        candidate: ExperimentCandidate,
    ) -> None:
        if (
            baseline_candidate.experiment_id != experiment_id
            or candidate.experiment_id != experiment_id
        ):
            raise ExperimentEvaluationError(
                "Candidate comparison requires candidates from the same experiment."
            )

    def _latest_completed_result(
        self,
        experiment_id: str,
        candidate_id: str,
    ) -> EvaluationResult:
        _, result = self._latest_completed_run_and_result(
            experiment_id,
            candidate_id,
        )

        return result

    def _latest_completed_run_and_result(
        self,
        experiment_id: str,
        candidate_id: str,
    ) -> tuple[EvaluationRun, EvaluationResult]:
        runs = [
            run
            for run in self._evaluation_run_repository.find_by_candidate_id(
                candidate_id
            )
            if (
                run.experiment_id == experiment_id
                and run.status == EvaluationRunStatus.COMPLETED
            )
        ]
        if not runs:
            raise ExperimentEvaluationError(
                "Candidate comparison requires completed evaluation runs."
            )

        latest_run = max(
            runs,
            key=lambda run: (
                run.completed_at or datetime.min.replace(tzinfo=UTC),
                run.run_id,
            ),
        )
        result = self._evaluation_repository.find_by_evaluation_id(
            cast(str, latest_run.evaluation_result_id)
        )
        if result is None:
            raise ExperimentEvaluationError(
                f"Evaluation result '{latest_run.evaluation_result_id}' is missing."
            )

        return latest_run, result

    @staticmethod
    def _metric_comparisons(
        baseline: EvaluationResult,
        candidate: EvaluationResult,
    ) -> list[EvaluationMetricComparison]:
        baseline_metrics = {
            metric.metric_name: metric.metric_value
            for metric in baseline.metrics
        }
        candidate_metrics = {
            metric.metric_name: metric.metric_value
            for metric in candidate.metrics
        }

        return [
            EvaluationMetricComparison(
                metric_name=metric_name,
                baseline_value=baseline_metrics.get(metric_name),
                candidate_value=candidate_metrics.get(metric_name),
            )
            for metric_name in sorted(
                baseline_metrics.keys() | candidate_metrics.keys()
            )
        ]

    @staticmethod
    def _overall_score(
        result: EvaluationResult,
    ) -> float:
        if not result.metrics:
            raise ExperimentEvaluationError(
                "Cannot rank an evaluation result with no metrics."
            )

        return sum(
            metric.metric_value
            for metric in result.metrics
        ) / len(result.metrics)

    @staticmethod
    def _cost_delta(
        baseline_cost: dict[str, float] | None,
        candidate_cost: dict[str, float] | None,
    ) -> float | None:
        if baseline_cost is None or candidate_cost is None:
            return None

        return sum(candidate_cost.values()) - sum(baseline_cost.values())

    @staticmethod
    def _numeric_delta(
        baseline_value: float | None,
        candidate_value: float | None,
    ) -> float | None:
        if baseline_value is None or candidate_value is None:
            return None

        return candidate_value - baseline_value
