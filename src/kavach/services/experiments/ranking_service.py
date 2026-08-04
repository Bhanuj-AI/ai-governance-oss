from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from kavach.domain.evaluation_result import EvaluationResult
from kavach.domain.experiments import (
    CandidateRanking,
    EvaluationRun,
    EvaluationRunStatus,
    ExperimentCandidate,
    Leaderboard,
    LeaderboardEntry,
)
from kavach.domain.models import Model
from kavach.repositories.evaluation_repository import EvaluationRepository
from kavach.repositories.evaluation_run_repository import (
    EvaluationRunRepository,
)
from kavach.repositories.experiment_candidate_repository import (
    ExperimentCandidateRepository,
)
from kavach.repositories.leaderboard_repository import (
    LeaderboardRepository,
)
from kavach.repositories.model_repository import ModelRepository
from kavach.services.experiments.ranking_strategy import (
    AnswerRelevanceRanking,
    GroundednessRanking,
    HallucinationRanking,
    LowestCostRanking,
    LowestLatencyRanking,
    OverallScoreRanking,
    RankingStrategy,
)


class RankingError(Exception):
    """
    Raised when leaderboard generation or ranking cannot proceed.
    """


class RankingService:
    """
    Generates immutable experiment leaderboards using pluggable strategies.
    """

    def __init__(
        self,
        candidate_repository: ExperimentCandidateRepository,
        evaluation_run_repository: EvaluationRunRepository,
        evaluation_repository: EvaluationRepository,
        model_repository: ModelRepository,
        leaderboard_repository: LeaderboardRepository,
        strategies: Iterable[RankingStrategy] | None = None,
        id_generator: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._candidate_repository = candidate_repository
        self._evaluation_run_repository = evaluation_run_repository
        self._evaluation_repository = evaluation_repository
        self._model_repository = model_repository
        self._leaderboard_repository = leaderboard_repository
        self._strategies = {
            strategy.strategy_name: strategy
            for strategy in (
                strategies
                or (
                    OverallScoreRanking(),
                    GroundednessRanking(),
                    AnswerRelevanceRanking(),
                    LowestLatencyRanking(),
                    LowestCostRanking(),
                    HallucinationRanking(),
                )
            )
        }
        self._id_generator = id_generator or (lambda: str(uuid4()))
        self._clock = clock or (lambda: datetime.now(UTC))

    def generate_leaderboard(
        self,
        experiment_id: str,
        ranking_strategy: str = "overall_score",
    ) -> Leaderboard:
        """
        Generate and persist an immutable leaderboard for one experiment.
        """

        strategy = self._strategy(ranking_strategy)
        rankings = self.rank_candidates(
            experiment_id=experiment_id,
            ranking_strategy=ranking_strategy,
        )
        entries = tuple(
            LeaderboardEntry(
                rank=ranking.rank,
                candidate_id=ranking.candidate.candidate_id,
                overall_score=ranking.overall_score,
                metrics=self._metric_values(
                    self._result_by_id(ranking.evaluation_result_id)
                ),
                cost=self._total_cost(
                    self._model_repository.find_by_id(
                        ranking.candidate.model_id
                    )
                ),
                latency=self._latency(
                    self._model_repository.find_by_id(
                        ranking.candidate.model_id
                    )
                ),
                reason=ranking.reason,
            )
            for ranking in rankings
        )
        leaderboard = Leaderboard(
            leaderboard_id=self._id_generator(),
            experiment_id=experiment_id,
            ranking_strategy=strategy.strategy_name,
            generated_at=self._clock(),
            entries=entries,
        )
        self._leaderboard_repository.save(leaderboard)

        return leaderboard

    def get_leaderboard(
        self,
        leaderboard_id: str,
    ) -> Leaderboard:
        leaderboard = self._leaderboard_repository.find_by_id(leaderboard_id)
        if leaderboard is None:
            raise RankingError(
                f"Leaderboard '{leaderboard_id}' does not exist."
            )

        return leaderboard

    def list_leaderboards(
        self,
        experiment_id: str,
    ) -> list[Leaderboard]:
        return self._leaderboard_repository.find_by_experiment_id(
            experiment_id
        )

    def rank_candidates(
        self,
        experiment_id: str,
        ranking_strategy: str = "overall_score",
    ) -> list[CandidateRanking]:
        strategy = self._strategy(ranking_strategy)
        candidates = self._candidate_repository.find_by_experiment_id(
            experiment_id
        )
        if not candidates:
            raise RankingError(
                f"Experiment '{experiment_id}' has no candidates."
            )

        rankings = [
            self._ranking_for_candidate(
                experiment_id=experiment_id,
                candidate=candidate,
                strategy=strategy,
            )
            for candidate in candidates
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

    def top_candidate(
        self,
        experiment_id: str,
        ranking_strategy: str = "overall_score",
    ) -> CandidateRanking:
        return self.rank_candidates(
            experiment_id=experiment_id,
            ranking_strategy=ranking_strategy,
        )[0]

    def _strategy(
        self,
        ranking_strategy: str,
    ) -> RankingStrategy:
        strategy = self._strategies.get(ranking_strategy)
        if strategy is None:
            raise RankingError(
                f"Unknown ranking strategy '{ranking_strategy}'."
            )

        return strategy

    def _ranking_for_candidate(
        self,
        experiment_id: str,
        candidate: ExperimentCandidate,
        strategy: RankingStrategy,
    ) -> CandidateRanking:
        run, result = self._latest_completed_run_and_result(
            experiment_id=experiment_id,
            candidate_id=candidate.candidate_id,
        )
        model = self._model_repository.find_by_id(candidate.model_id)

        try:
            overall_score, reason = strategy.score_candidate(
                candidate=candidate,
                evaluation_result=result,
                model=model,
            )
        except ValueError as error:
            raise RankingError(str(error)) from error

        return CandidateRanking(
            experiment_id=experiment_id,
            candidate=candidate,
            evaluation_run_id=run.run_id,
            evaluation_result_id=result.evaluation_id,
            overall_score=overall_score,
            rank=0,
            reason=reason,
            ranking_strategy=strategy.strategy_name,
        )

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
            raise RankingError(
                "Only completed evaluation runs participate in ranking."
            )

        latest_run = max(
            runs,
            key=lambda run: (
                run.completed_at or datetime.min.replace(tzinfo=UTC),
                run.run_id,
            ),
        )

        return latest_run, self._result_by_id(
            latest_run.evaluation_result_id or ""
        )

    def _result_by_id(
        self,
        evaluation_result_id: str,
    ) -> EvaluationResult:
        result = self._evaluation_repository.find_by_evaluation_id(
            evaluation_result_id
        )
        if result is None:
            raise RankingError(
                f"Evaluation result '{evaluation_result_id}' is missing."
            )

        return result

    @staticmethod
    def _metric_values(
        result: EvaluationResult,
    ) -> dict[str, float]:
        return {
            metric.metric_name: metric.metric_value
            for metric in result.metrics
        }

    @staticmethod
    def _total_cost(
        model: Model | None,
    ) -> float | None:
        if model is None or model.cost is None:
            return None

        return sum(model.cost.values())

    @staticmethod
    def _latency(
        model: Model | None,
    ) -> float | None:
        if model is None:
            return None

        return model.latency
