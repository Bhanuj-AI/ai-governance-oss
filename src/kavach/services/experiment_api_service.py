from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from kavach.domain.experiments import (
    CandidateComparison,
    CandidateRanking,
    EvaluationRun,
    EvaluationRunStatus,
    Experiment,
    ExperimentCandidate,
    Leaderboard,
)
from kavach.domain.evaluation_result import EvaluationResult
from kavach.domain.history import EvaluationMetricComparison
from kavach.domain.workflow_execution import WorkflowExecution
from kavach.evaluation.evaluation_metrics import (
    EvaluationMetricSpec,
    normalize_metric_name,
)
from kavach.ontology.synchronization import (
    OntologySyncEventPublisherProtocol,
)
from kavach.providers.errors import ProviderNotFoundError
from kavach.providers.provider_registry import EvaluationProviderRegistry
from kavach.repositories.dataset_repository import DatasetRepository
from kavach.repositories.evaluation_repository import EvaluationRepository
from kavach.repositories.evaluation_run_repository import (
    EvaluationRunRepository,
)
from kavach.repositories.experiment_candidate_repository import (
    ExperimentCandidateRepository,
)
from kavach.repositories.experiment_repository import ExperimentRepository
from kavach.repositories.leaderboard_repository import LeaderboardRepository
from kavach.repositories.model_repository import ModelRepository
from kavach.repositories.prompt_repository import PromptRepository
from kavach.services.evaluation_api_service import (
    EvaluationApiService,
    EvaluationProviderNotFoundError,
    UnsupportedMetricError,
)
from kavach.services.provider_installation_service import ProviderInstallationService
from kavach.services.experiments import (
    ExperimentCandidateReferenceError,
    ExperimentCandidateService,
    ExperimentCandidateNotFoundError,
    ExperimentLifecycleError,
    ExperimentService,
    RankingError,
    RankingService,
)
from kavach.services.experiments.experiment_service import (
    ExperimentConflictError,
    ExperimentNotFoundError,
)
from kavach.tenancy.domain import TenantContext


class InvalidExperimentRequestError(Exception):
    """
    Raised when a REST experiment request cannot be fulfilled.
    """


class ExperimentApiService:
    """
    Application facade for REST experiment use cases.

    The facade coordinates existing experiment, evaluation, and ranking
    services while keeping routers free of repositories and business rules.
    """

    def __init__(
        self,
        experiment_repository: ExperimentRepository,
        candidate_repository: ExperimentCandidateRepository,
        evaluation_run_repository: EvaluationRunRepository,
        evaluation_repository: EvaluationRepository,
        leaderboard_repository: LeaderboardRepository,
        prompt_repository: PromptRepository,
        model_repository: ModelRepository,
        dataset_repository: DatasetRepository,
        provider_registry: EvaluationProviderRegistry,
        provider_installation_service: ProviderInstallationService | None = None,
        id_generator: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
        ontology_event_publisher: OntologySyncEventPublisherProtocol | None = None,
    ) -> None:
        self._experiment_repository = experiment_repository
        self._candidate_repository = candidate_repository
        self._evaluation_run_repository = evaluation_run_repository
        self._evaluation_repository = evaluation_repository
        self._leaderboard_repository = leaderboard_repository
        self._prompt_repository = prompt_repository
        self._model_repository = model_repository
        self._dataset_repository = dataset_repository
        self._provider_registry = provider_registry
        self._provider_installation_service = provider_installation_service
        self._id_generator = id_generator or (lambda: str(uuid4()))
        self._clock = clock or (lambda: datetime.now(UTC))
        self._ontology_event_publisher = ontology_event_publisher

    def create_experiment(
        self,
        name: str,
        description: str,
        metadata: Mapping[str, Any] | None = None,
        context: TenantContext | None = None,
    ) -> Experiment:
        """
        Create an experiment using the existing experiment service.
        """
        owner = str((metadata or {}).get("owner", "rest-api"))
        try:
            experiment = self._experiment_service().create_experiment(
                name=name,
                description=description,
                owner=owner,
            )
            if context is not None:
                experiment = replace(
                    experiment,
                    organization_id=context.organization_id,
                    project_id=context.project_id or "",
                )
                self._experiment_repository.save(experiment)
            return experiment
        except (ExperimentConflictError, ValueError) as exc:
            raise InvalidExperimentRequestError(str(exc)) from exc

    def get_experiment(
        self,
        experiment_id: str,
        context: TenantContext | None = None,
    ) -> Experiment:
        """
        Return one experiment by ID.
        """
        experiment = self._experiment_service().get_experiment(experiment_id)
        if context is not None and (
            experiment.organization_id != context.organization_id
            or experiment.project_id != context.project_id
        ):
            raise ExperimentNotFoundError(
                f"Experiment '{experiment_id}' was not found."
            )
        return experiment

    def list_experiments(
        self, context: TenantContext | None = None
    ) -> list[Experiment]:
        """
        Return experiments through the existing experiment service.
        """
        return [
            experiment
            for experiment in self._experiment_service().list_experiments()
            if context is None
            or (
                experiment.organization_id == context.organization_id
                and experiment.project_id == context.project_id
            )
        ]

    def list_candidates(
        self,
        experiment_id: str,
        context: TenantContext,
    ) -> list[ExperimentCandidate]:
        """Return candidates for a tenant-scoped experiment."""
        self.get_experiment(experiment_id, context)
        return self._candidate_repository.find_by_experiment_id(experiment_id)

    def list_evaluation_runs(
        self,
        experiment_id: str,
        context: TenantContext,
    ) -> list[EvaluationRun]:
        """Return evaluation runs for a tenant-scoped experiment."""
        self.get_experiment(experiment_id, context)
        return self._evaluation_run_repository.find_by_experiment_id(experiment_id)

    def compare_candidates(
        self,
        experiment_id: str,
        baseline_candidate_id: str,
        comparison_candidate_id: str,
        context: TenantContext | None = None,
    ) -> CandidateComparison:
        """Compare two candidates using their latest completed evaluations."""
        self.get_experiment(experiment_id, context)
        if baseline_candidate_id == comparison_candidate_id:
            raise InvalidExperimentRequestError(
                "Baseline and comparison candidates must be different."
            )

        baseline = self._candidate_for_comparison(
            experiment_id,
            baseline_candidate_id,
        )
        comparison = self._candidate_for_comparison(
            experiment_id,
            comparison_candidate_id,
        )
        baseline_result = self._latest_completed_result(
            experiment_id,
            baseline_candidate_id,
        )
        comparison_result = self._latest_completed_result(
            experiment_id,
            comparison_candidate_id,
        )

        return CandidateComparison(
            experiment_id=experiment_id,
            baseline_candidate_id=baseline.candidate_id,
            candidate_candidate_id=comparison.candidate_id,
            baseline_candidate=baseline,
            candidate=comparison,
            metric_comparisons=self._metric_comparisons(
                baseline_result,
                comparison_result,
            ),
        )

    def add_candidate(
        self,
        experiment_id: str,
        candidate_name: str,
        prompt_reference: str,
        model_reference: str,
        dataset_reference: str,
        provider_name: str | None,
        runtime_parameters: Mapping[str, Any],
        provider_installation_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        context: TenantContext | None = None,
    ) -> ExperimentCandidate:
        """
        Register a candidate through the existing candidate service.
        """
        self.get_experiment(experiment_id, context)
        resolved_provider_name = self._provider_name_for_candidate(
            provider_name, provider_installation_id, context
        )
        prompt_id, prompt_version = _split_reference(prompt_reference)
        model_id, model_version = _split_reference(model_reference)
        dataset_id, dataset_version = _split_reference(dataset_reference)

        try:
            return self._candidate_service().create_candidate(
                experiment_id=experiment_id,
                name=candidate_name,
                prompt_id=prompt_id,
                prompt_version=prompt_version,
                model_id=model_id,
                model_version=model_version,
                dataset_id=dataset_id,
                dataset_version=dataset_version,
                evaluation_provider=resolved_provider_name,
                temperature=float(runtime_parameters.get("temperature", 0.0)),
                top_p=float(runtime_parameters.get("top_p", 1.0)),
                max_tokens=int(runtime_parameters.get("max_tokens", 1024)),
                metadata={
                    **dict(metadata or {}),
                    **({"provider_installation_id": provider_installation_id} if provider_installation_id else {}),
                },
            )
        except ExperimentCandidateReferenceError as exc:
            message = str(exc)
            if "Experiment" in message:
                raise ExperimentNotFoundError(message) from exc
            raise InvalidExperimentRequestError(message) from exc
        except (ExperimentLifecycleError, ValueError) as exc:
            raise InvalidExperimentRequestError(str(exc)) from exc

    def run_experiment(
        self,
        experiment_id: str,
        metric_specs: Sequence[EvaluationMetricSpec] | None = None,
        provider_config: Mapping[str, Any] | None = None,
        context: TenantContext | None = None,
    ) -> tuple[list[EvaluationRun], Leaderboard | None]:
        """
        Execute candidates synchronously and generate a leaderboard.
        """
        experiment_service = self._experiment_service()
        experiment = self.get_experiment(experiment_id, context)
        candidates = self._candidate_repository.find_by_experiment_id(experiment_id)
        if not candidates:
            raise InvalidExperimentRequestError(
                f"Experiment '{experiment_id}' has no candidates."
            )

        self._validate_candidate_providers_and_metrics(
            candidates=candidates,
            metric_specs=metric_specs or (),
        )

        try:
            if experiment.status.value == "DRAFT":
                experiment = experiment_service.start_experiment(experiment_id)
            elif experiment.status.value != "RUNNING":
                raise ExperimentLifecycleError(
                    "Only draft or running experiments may be executed."
                )
        except ExperimentLifecycleError as exc:
            raise InvalidExperimentRequestError(str(exc)) from exc

        runs: list[EvaluationRun] = []
        has_failures = False

        for candidate in candidates:
            running_run = self._create_running_run(
                experiment=experiment,
                candidate=candidate,
            )
            try:
                result = EvaluationApiService(
                    provider_registry=self._provider_registry,
                    evaluation_repository=self._evaluation_repository,
                    ontology_event_publisher=self._ontology_event_publisher,
                ).submit_evaluation(
                    execution=self._workflow_execution(
                        experiment=experiment,
                        candidate=candidate,
                        run_id=running_run.run_id,
                    ),
                    provider_name=candidate.evaluation_provider,
                    metric_specs=metric_specs,
                    provider_config=self._provider_config_for_candidate(
                        candidate, provider_config or {}, context
                    ),
                    context=context,
                )
                completed_run = replace(
                    running_run,
                    evaluation_result_id=result.evaluation_id,
                    completed_at=self._clock(),
                    status=EvaluationRunStatus.COMPLETED,
                )
                self._evaluation_run_repository.save(completed_run)
                self._publish_evaluation_run_event(completed_run, context)
                runs.append(completed_run)
            except Exception:
                failed_run = replace(
                    running_run,
                    completed_at=self._clock(),
                    status=EvaluationRunStatus.FAILED,
                )
                self._evaluation_run_repository.save(failed_run)
                self._publish_evaluation_run_event(failed_run, context)
                runs.append(failed_run)
                has_failures = True

        if has_failures:
            experiment_service.fail_experiment(experiment_id)
            return runs, None

        experiment_service.complete_experiment(experiment_id)
        leaderboard = self._ranking_service().generate_leaderboard(experiment_id)
        self._publish_leaderboard_event(leaderboard, context)
        return runs, leaderboard

    def get_leaderboard(
        self,
        experiment_id: str,
        context: TenantContext | None = None,
    ) -> Leaderboard:
        """
        Return the latest leaderboard for an experiment, generating one if needed.
        """
        self.get_experiment(experiment_id, context)
        leaderboards = self._ranking_service().list_leaderboards(experiment_id)
        if leaderboards:
            leaderboard = max(
                leaderboards,
                key=lambda leaderboard: (
                    leaderboard.generated_at,
                    leaderboard.leaderboard_id,
                ),
            )
            self._publish_leaderboard_event(leaderboard, context)
            return leaderboard

        try:
            leaderboard = self._ranking_service().generate_leaderboard(experiment_id)
            self._publish_leaderboard_event(leaderboard, context)
            return leaderboard
        except RankingError as exc:
            raise InvalidExperimentRequestError(str(exc)) from exc

    def rank_candidates(
        self,
        experiment_id: str,
        context: TenantContext,
    ) -> list[CandidateRanking]:
        """Return a tenant-scoped, read-only ranking from completed evaluations.

        Unlike ``get_leaderboard``, this method does not create a persisted
        leaderboard when one does not exist. It is the safe boundary consumed
        by the OSS Experiment Advisor.
        """
        self.get_experiment(experiment_id, context)
        try:
            return self._ranking_service().rank_candidates(experiment_id)
        except RankingError as exc:
            raise InvalidExperimentRequestError(str(exc)) from exc

    def _experiment_service(self) -> ExperimentService:
        return ExperimentService(
            experiment_repository=self._experiment_repository,
            id_generator=self._id_generator,
            clock=self._clock,
            ontology_event_publisher=self._ontology_event_publisher,
        )

    def _candidate_service(self) -> ExperimentCandidateService:
        return ExperimentCandidateService(
            candidate_repository=self._candidate_repository,
            experiment_repository=self._experiment_repository,
            prompt_repository=self._prompt_repository,
            model_repository=self._model_repository,
            dataset_repository=self._dataset_repository,
            id_generator=self._id_generator,
            clock=self._clock,
            ontology_event_publisher=self._ontology_event_publisher,
        )

    def _ranking_service(self) -> RankingService:
        return RankingService(
            candidate_repository=self._candidate_repository,
            evaluation_run_repository=self._evaluation_run_repository,
            evaluation_repository=self._evaluation_repository,
            model_repository=self._model_repository,
            leaderboard_repository=self._leaderboard_repository,
            id_generator=self._id_generator,
            clock=self._clock,
        )

    def _publish_evaluation_run_event(
        self,
        run: EvaluationRun,
        context: TenantContext | None,
    ) -> None:
        if self._ontology_event_publisher is None:
            return
        self._ontology_event_publisher.publish_entity_event(
            "EvaluationRunCompleted",
            entity_type="EvaluationRun",
            entity_id=run.run_id,
            scope_identifier="evaluation_run_repository",
            payload={
                "run_id": run.run_id,
                "experiment_id": run.experiment_id,
                "candidate_id": run.candidate_id,
                "status": run.status.value,
            },
            organization_id=(context.organization_id if context else "org_default"),
            project_id=(context.project_id or "project_default") if context else "project_default",
        )

    def _publish_leaderboard_event(
        self,
        leaderboard: Leaderboard,
        context: TenantContext | None,
    ) -> None:
        if self._ontology_event_publisher is None:
            return
        self._ontology_event_publisher.publish_entity_event(
            "LeaderboardGenerated",
            entity_type="Leaderboard",
            entity_id=leaderboard.leaderboard_id,
            scope_identifier="leaderboard_repository",
            payload={
                "leaderboard_id": leaderboard.leaderboard_id,
                "experiment_id": leaderboard.experiment_id,
                "entry_count": len(leaderboard.entries),
            },
            organization_id=(context.organization_id if context else "org_default"),
            project_id=(context.project_id or "project_default") if context else "project_default",
        )

    def _create_running_run(
        self,
        experiment: Experiment,
        candidate: ExperimentCandidate,
    ) -> EvaluationRun:
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
        return running_run

    def _workflow_execution(
        self,
        experiment: Experiment,
        candidate: ExperimentCandidate,
        run_id: str,
    ) -> WorkflowExecution:
        return WorkflowExecution(
            workflow_id=experiment.experiment_id,
            execution_id=run_id,
            workflow_name=experiment.name,
            workflow_version="experiment",
            execution_status="COMPLETED",
            input={
                "experiment_id": experiment.experiment_id,
                "candidate_id": candidate.candidate_id,
                "candidate_name": candidate.name,
            },
            final_state={
                "answer": str(candidate.metadata.get("answer", "")),
                "context": str(candidate.metadata.get("context", "")),
            },
            events=[],
        )

    def _validate_candidate_providers_and_metrics(
        self,
        candidates: Sequence[ExperimentCandidate],
        metric_specs: Sequence[EvaluationMetricSpec],
    ) -> None:
        for candidate in candidates:
            provider = self._resolve_provider(candidate.evaluation_provider)
            supported_metrics = {
                normalize_metric_name(metric)
                for metric in provider.descriptor.capabilities.supported_metrics
            }
            for metric_spec in metric_specs:
                if metric_spec.name not in supported_metrics:
                    raise UnsupportedMetricError(
                        metric=metric_spec.name,
                        provider_name=provider.descriptor.name,
                    )

    def _resolve_provider(
        self,
        provider_name: str,
    ):
        try:
            return self._provider_registry.get(provider_name)
        except ProviderNotFoundError as exc:
            raise EvaluationProviderNotFoundError(provider_name) from exc

    def _provider_name_for_candidate(
        self,
        provider_name: str | None,
        provider_installation_id: str | None,
        context: TenantContext | None,
    ) -> str:
        if provider_installation_id:
            if self._provider_installation_service is None or context is None:
                raise InvalidExperimentRequestError(
                    "Provider installations require a tenant-scoped runtime."
                )
            installation = self._provider_installation_service.resolve_provider_type(
                provider_installation_id, context
            )
            return installation.provider_type
        if not provider_name:
            raise InvalidExperimentRequestError("An evaluation provider is required.")
        self._resolve_provider(provider_name)
        return provider_name

    def _provider_config_for_candidate(
        self,
        candidate: ExperimentCandidate,
        request_config: Mapping[str, Any],
        context: TenantContext | None,
    ) -> dict[str, Any]:
        installation_id = candidate.metadata.get("provider_installation_id")
        if not installation_id:
            return dict(request_config)
        if self._provider_installation_service is None or context is None:
            raise InvalidExperimentRequestError(
                "Provider installations require a tenant-scoped runtime."
            )
        installation, installation_config = self._provider_installation_service.resolve_runtime_config(
            str(installation_id), context
        )
        if installation.provider_type != candidate.evaluation_provider:
            raise InvalidExperimentRequestError(
                "Provider installation type no longer matches the candidate snapshot."
            )
        return {**installation_config, **dict(request_config)}

    def _candidate_for_comparison(
        self,
        experiment_id: str,
        candidate_id: str,
    ) -> ExperimentCandidate:
        candidate = self._candidate_repository.find_by_id(candidate_id)
        if candidate is None:
            raise ExperimentCandidateNotFoundError(
                f"Candidate '{candidate_id}' was not found."
            )
        if candidate.experiment_id != experiment_id:
            raise ExperimentCandidateNotFoundError(
                f"Candidate '{candidate_id}' was not found."
            )
        return candidate

    def _latest_completed_result(
        self,
        experiment_id: str,
        candidate_id: str,
    ) -> EvaluationResult:
        runs = [
            run
            for run in self._evaluation_run_repository.find_by_candidate_id(
                candidate_id
            )
            if run.experiment_id == experiment_id
            and run.status == EvaluationRunStatus.COMPLETED
        ]
        if not runs:
            raise InvalidExperimentRequestError(
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
            latest_run.evaluation_result_id or ""
        )
        if result is None:
            raise InvalidExperimentRequestError(
                f"Evaluation result '{latest_run.evaluation_result_id}' is missing."
            )
        return result

    @staticmethod
    def _metric_comparisons(
        baseline: EvaluationResult,
        comparison: EvaluationResult,
    ) -> list[EvaluationMetricComparison]:
        baseline_metrics = {
            metric.metric_name: metric.metric_value for metric in baseline.metrics
        }
        comparison_metrics = {
            metric.metric_name: metric.metric_value
            for metric in comparison.metrics
        }
        return [
            EvaluationMetricComparison(
                metric_name=metric_name,
                baseline_value=baseline_metrics.get(metric_name),
                candidate_value=comparison_metrics.get(metric_name),
            )
            for metric_name in sorted(
                baseline_metrics.keys() | comparison_metrics.keys()
            )
        ]


def _split_reference(
    reference: str,
) -> tuple[str, str]:
    value = reference.strip()
    if ":" not in value:
        return value, value

    identifier, version = value.split(":", maxsplit=1)
    if not identifier.strip() or not version.strip():
        raise InvalidExperimentRequestError(f"Invalid version reference '{reference}'.")

    return identifier.strip(), version.strip()
