from __future__ import annotations

import logging
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import uuid4

from ai_governance.domain.agent_execution import (
    ActorType,
    AgentExecutionStatus,
    EventType,
)
from ai_governance.domain.evaluation_result import (
    EvaluationArtifact,
    EvaluationMetric,
    EvaluationResult,
)
from ai_governance.domain.experiments import (
    CandidateComparison,
    CandidateRanking,
    EvaluationRun,
    EvaluationRunStatus,
    Experiment,
    ExperimentCandidate,
    ExperimentStatus,
    Leaderboard,
)
from ai_governance.domain.history import EvaluationMetricComparison
from ai_governance.domain.models import runtime_model_provider_key
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.evaluation.evaluation_metrics import (
    EvaluationMetricSpec,
    normalize_metric_name,
)
from ai_governance.evaluation.evaluation_request import EvaluationRequest
from ai_governance.ontology.synchronization import (
    OntologySyncEventPublisherProtocol,
)
from ai_governance.providers.errors import ProviderNotFoundError
from ai_governance.providers.evaluation_provider import (
    BatchEvaluationResult,
    EvaluationWorkloadEstimate,
)
from ai_governance.providers.provider_capabilities import EvaluationGranularity
from ai_governance.providers.provider_registry import EvaluationProviderRegistry
from ai_governance.repositories.dataset_repository import DatasetRepository
from ai_governance.repositories.evaluation_repository import EvaluationRepository
from ai_governance.repositories.evaluation_run_repository import (
    EvaluationRunRepository,
)
from ai_governance.repositories.experiment_candidate_repository import (
    ExperimentCandidateRepository,
)
from ai_governance.repositories.experiment_repository import ExperimentRepository
from ai_governance.repositories.leaderboard_repository import LeaderboardRepository
from ai_governance.repositories.model_repository import ModelRepository
from ai_governance.repositories.prompt_repository import PromptRepository
from ai_governance.services.candidate_execution_runtime import (
    CandidateExecutionError,
    CandidateExecutionRuntime,
)
from ai_governance.services.dataset_builder import EvaluationDatasetBuilder
from ai_governance.services.evaluation_api_service import (
    EvaluationApiService,
    EvaluationProviderNotFoundError,
    UnsupportedMetricError,
)
from ai_governance.services.execution_deadline import (
    ExecutionDeadlineExceeded,
    ExecutionDeadlineUnavailable,
    WorkerExecutionDeadline,
)
from ai_governance.services.experiments import (
    ExperimentCandidateNotFoundError,
    ExperimentCandidateReferenceError,
    ExperimentCandidateService,
    ExperimentLifecycleError,
    ExperimentService,
    RankingError,
    RankingService,
)
from ai_governance.services.experiments.experiment_service import (
    ExperimentConflictError,
    ExperimentNotFoundError,
)
from ai_governance.services.provider_installation_service import (
    ProviderInstallationDisabledError,
    ProviderInstallationNotFoundError,
    ProviderInstallationService,
    ProviderInstallationTypeUnavailableError,
)
from ai_governance.services.replay_execution import ReplayExecutionStore
from ai_governance.services.runtime_connection_service import (
    RuntimeConnectionDisabledError,
    RuntimeConnectionNotFoundError,
    RuntimeConnectionProviderMismatchError,
    RuntimeConnectionService,
)
from ai_governance.tenancy.domain import TenantContext

LOGGER = logging.getLogger(__name__)
_PROCESS_STARTED_AT = datetime.now(UTC)
_INTERRUPTED_RUN_REASON = "Evaluation run was interrupted by a control-plane restart."
_CANCELLED_RUN_REASON = "Experiment cancellation requested."


class InvalidExperimentRequestError(Exception):
    """
    Raised when a REST experiment request cannot be fulfilled.
    """


@dataclass(frozen=True)
class ExperimentRunProgress:
    """Durable progress snapshot for the currently executing candidate."""

    run_id: str
    candidate_id: str
    candidate_name: str
    candidate_position: int
    total_item_count: int | None
    completed_item_count: int
    evaluated_item_count: int


@dataclass(frozen=True)
class ExperimentRunPlan:
    """Preflight estimate and current persisted progress for an experiment."""

    experiment_id: str
    candidate_count: int
    dataset_item_count: int
    runner_invocation_count: int
    expected_sample_result_count: int | None
    workload_basis: str
    # Retained for REST compatibility with item-oriented providers. A batch
    # runner must not be displayed as though this were its model-call count.
    model_invocation_count: int
    evaluation_item_count: int
    active_run: ExperimentRunProgress | None = None


@dataclass(frozen=True)
class ExperimentRunEvaluationPage:
    """A tenant-scoped, paged inventory of persisted item evaluations."""

    run_id: str
    page: int
    page_size: int
    total_items: int
    items: tuple[EvaluationResult, ...]


@dataclass(frozen=True)
class EvaluationReportCallRole:
    call_role: str
    call_count: int
    input_tokens: float | None
    output_tokens: float | None
    total_tokens: float | None
    duration_ms: float | None
    original_task_included: bool | None
    prior_conversation_retained: bool | None


@dataclass(frozen=True)
class EvaluationReportRow:
    candidate_id: str
    candidate_name: str
    group: str
    sample_count: int
    pass_rate: float | None
    metrics: Mapping[str, float]
    original_task_tokens: float | None
    tokenizer: str | None
    token_count_kind: str | None
    failure_categories: Mapping[str, int]
    failed_scenario_ids: tuple[str, ...]
    call_roles: tuple[EvaluationReportCallRole, ...]
    provider_cost: float | None


@dataclass(frozen=True)
class EvaluationReport:
    experiment_id: str
    group_dimension: str
    rows: tuple[EvaluationReportRow, ...]
    runner_provenance: Mapping[str, tuple[Mapping[str, Any], ...]]


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
        runtime_connection_service: RuntimeConnectionService | None = None,
        candidate_execution_runtime: CandidateExecutionRuntime | None = None,
        execution_store: ReplayExecutionStore | None = None,
        id_generator: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
        ontology_event_publisher: OntologySyncEventPublisherProtocol | None = None,
        agent_execution_service: Any | None = None,
        provider_execution_deadline: Any | None = None,
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
        self._runtime_connection_service = runtime_connection_service
        self._candidate_execution_runtime = candidate_execution_runtime
        self._execution_store = execution_store
        self._id_generator = id_generator or (lambda: str(uuid4()))
        self._clock = clock or (lambda: datetime.now(UTC))
        self._ontology_event_publisher = ontology_event_publisher
        self._agent_execution_service = agent_execution_service
        self._provider_execution_deadline = (
            provider_execution_deadline or WorkerExecutionDeadline()
        )

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
        if self._reconcile_interrupted_runs(experiment):
            return self._experiment_service().get_experiment(experiment_id)
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
        experiment = self.get_experiment(experiment_id, context)
        if experiment.status == ExperimentStatus.CANCELLED:
            runs, _ = self._cancelled_run_snapshot(experiment_id)
            return runs
        return self._evaluation_run_repository.find_by_experiment_id(experiment_id)

    def list_run_evaluations(
        self,
        experiment_id: str,
        run_id: str,
        *,
        page: int,
        page_size: int,
        context: TenantContext,
    ) -> ExperimentRunEvaluationPage:
        """Return partial or terminal per-item scores for one owned run."""
        self.get_experiment(experiment_id, context)
        run = self._evaluation_run_repository.find_by_id(run_id)
        if run is None or run.experiment_id != experiment_id:
            raise InvalidExperimentRequestError(
                f"Evaluation run '{run_id}' was not found for this experiment."
            )
        result_page = self._evaluation_repository.find_page_by_execution_id_prefix(
            f"{run_id}:",
            context,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return ExperimentRunEvaluationPage(
            run_id=run_id,
            page=page,
            page_size=page_size,
            total_items=result_page.total_count,
            items=self._with_persisted_runtime_latency(result_page.items, context),
        )

    def _with_persisted_runtime_latency(
        self,
        results: Sequence[EvaluationResult],
        context: TenantContext,
    ) -> tuple[EvaluationResult, ...]:
        """Attach safe model latency from immutable execution evidence when needed."""
        if self._execution_store is None:
            return tuple(results)
        enriched: list[EvaluationResult] = []
        for result in results:
            if _model_latency_ms(result.metadata) is not None:
                enriched.append(result)
                continue
            execution = self._execution_store.get_execution(result.execution_id, context)
            model_latency_ms = _model_latency_ms(execution.metadata) if execution else None
            if model_latency_ms is None:
                enriched.append(result)
                continue
            enriched.append(
                replace(
                    result,
                    metadata={
                        **result.metadata,
                        "model_latency_ms": model_latency_ms,
                    },
                )
            )
        return tuple(enriched)

    def get_run_plan(
        self,
        experiment_id: str,
        context: TenantContext,
    ) -> ExperimentRunPlan:
        """Return the declared execution volume and any persisted active progress."""
        self.get_experiment(experiment_id, context)
        candidates = self._candidate_repository.find_by_experiment_id(experiment_id)
        if not candidates:
            return ExperimentRunPlan(
                experiment_id=experiment_id,
                candidate_count=0,
                dataset_item_count=0,
                runner_invocation_count=0,
                expected_sample_result_count=0,
                workload_basis="DATASET_RECORDS",
                model_invocation_count=0,
                evaluation_item_count=0,
            )

        self._validate_comparable_dataset_versions(candidates)
        dataset = self._dataset_repository.find_by_id(candidates[0].dataset_id)
        if (
            dataset is None
            or dataset.version != candidates[0].dataset_version
            or dataset.organization_id != context.organization_id
            or dataset.project_id != (context.project_id or "")
        ):
            raise InvalidExperimentRequestError(
                "The candidate dataset is not available in the current tenant scope."
            )
        active_run = next(
            (
                run
                for run in self._evaluation_run_repository.find_by_experiment_id(experiment_id)
                if run.status == EvaluationRunStatus.RUNNING
            ),
            None,
        )
        active_progress = None
        if active_run is not None:
            candidate_position = next(
                index
                for index, candidate in enumerate(candidates, start=1)
                if candidate.candidate_id == active_run.candidate_id
            )
            candidate = candidates[candidate_position - 1]
            active_progress = ExperimentRunProgress(
                run_id=active_run.run_id,
                candidate_id=active_run.candidate_id,
                candidate_name=candidate.name,
                candidate_position=candidate_position,
                total_item_count=active_run.total_item_count,
                completed_item_count=active_run.completed_item_count,
                evaluated_item_count=active_run.evaluated_item_count,
            )
        estimates = [
            self._workload_estimate_for_candidate(candidate, context)
            for candidate in candidates
        ]
        provider_estimate_count = sum(estimate is not None for estimate in estimates)
        runner_invocation_count = sum(
            estimate.runner_invocation_count
            if estimate is not None
            else dataset.record_count
            for estimate in estimates
        )
        expected_sample_result_count = (
            sum(
                estimate.expected_sample_result_count
                if estimate is not None
                and estimate.expected_sample_result_count is not None
                else dataset.record_count
                for estimate in estimates
            )
            if all(
                estimate is None
                or estimate.expected_sample_result_count is not None
                for estimate in estimates
            )
            else None
        )
        workload_basis = (
            "PROVIDER_DECLARED"
            if provider_estimate_count == len(candidates)
            else "MIXED"
            if provider_estimate_count
            else "DATASET_RECORDS"
        )
        return ExperimentRunPlan(
            experiment_id=experiment_id,
            candidate_count=len(candidates),
            dataset_item_count=dataset.record_count,
            runner_invocation_count=runner_invocation_count,
            expected_sample_result_count=expected_sample_result_count,
            workload_basis=workload_basis,
            model_invocation_count=len(candidates) * dataset.record_count,
            evaluation_item_count=len(candidates) * dataset.record_count,
            active_run=active_progress,
        )

    def get_evaluation_report(
        self,
        experiment_id: str,
        context: TenantContext,
        *,
        group_dimension: str = "length_band",
    ) -> EvaluationReport:
        """Derive a generic report from durable child evaluation results.

        Providers may supply optional, safe sample dimensions (for example a
        prompt-length band). Providers that do not do so remain reportable in
        the ``all`` group; no provider SDK or schema enters this contract.
        """
        self.get_experiment(experiment_id, context)
        candidates = {
            candidate.candidate_id: candidate
            for candidate in self._candidate_repository.find_by_experiment_id(experiment_id)
        }
        grouped: dict[tuple[str, str], list[EvaluationResult]] = defaultdict(list)
        provenance: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
        for run in self._evaluation_run_repository.find_by_experiment_id(experiment_id):
            candidate = candidates.get(run.candidate_id)
            if candidate is None:
                continue
            if run.runner_provenance:
                fingerprint = str(run.runner_provenance.get("configuration_fingerprint", "unknown"))
                provenance[candidate.candidate_id][fingerprint] = run.runner_provenance
            page = self._evaluation_repository.find_page_by_execution_id_prefix(
                f"{run.run_id}:sample:", context, offset=0, limit=10_000
            )
            for result in page.items:
                group = str(result.metadata.get(group_dimension) or "all")
                grouped[(candidate.candidate_id, group)].append(result)

        rows = tuple(
            self._evaluation_report_row(
                candidates[candidate_id], group, results
            )
            for (candidate_id, group), results in sorted(grouped.items())
        )
        return EvaluationReport(
            experiment_id=experiment_id,
            group_dimension=group_dimension,
            rows=rows,
            runner_provenance={
                candidate_id: tuple(values.values())
                for candidate_id, values in sorted(provenance.items())
            },
        )

    @staticmethod
    def _evaluation_report_row(
        candidate: ExperimentCandidate,
        group: str,
        results: Sequence[EvaluationResult],
    ) -> EvaluationReportRow:
        metric_values: dict[str, list[float]] = defaultdict(list)
        prompt_tokens: list[float] = []
        failure_categories: Counter[str] = Counter()
        failed_scenarios: set[str] = set()
        role_calls: dict[str, list[Mapping[str, object]]] = defaultdict(list)
        tokenizers: set[str] = set()
        token_kinds: set[str] = set()
        for result in results:
            for metric in result.metrics:
                metric_values[metric.metric_name].append(metric.metric_value)
            token_value = _number_value(result.metadata.get("original_prompt_tokens"))
            if token_value is not None:
                prompt_tokens.append(token_value)
            if value := result.metadata.get("tokenizer"):
                tokenizers.add(str(value))
            if value := result.metadata.get("token_count_kind"):
                token_kinds.add(str(value))
            passed = next(
                (metric.metric_value > 0 for metric in result.metrics if metric.metric_name == "pass"),
                None,
            )
            if passed is False:
                failure_categories[str(result.metadata.get("failure_category") or "incorrect")]+=1
                if scenario_id := result.metadata.get("scenario_id"):
                    failed_scenarios.add(str(scenario_id))
            calls = result.metadata.get("model_call_usage")
            if isinstance(calls, Sequence) and not isinstance(calls, str | bytes):
                for call in calls:
                    if isinstance(call, Mapping):
                        role_calls[str(call.get("call_role") or "unattributed")].append(call)

        call_roles = tuple(
            _report_call_role(role, calls)
            for role, calls in sorted(role_calls.items())
        )
        metrics = {
            name: sum(values) / len(values)
            for name, values in sorted(metric_values.items())
            if values
        }
        return EvaluationReportRow(
            candidate_id=candidate.candidate_id,
            candidate_name=candidate.name,
            group=group,
            sample_count=len(results),
            pass_rate=metrics.get("pass"),
            metrics=metrics,
            original_task_tokens=(sum(prompt_tokens) / len(prompt_tokens) if prompt_tokens else None),
            tokenizer=next(iter(tokenizers)) if len(tokenizers) == 1 else None,
            token_count_kind=next(iter(token_kinds)) if len(token_kinds) == 1 else None,
            failure_categories=dict(sorted(failure_categories.items())),
            failed_scenario_ids=tuple(sorted(failed_scenarios)),
            call_roles=call_roles,
            provider_cost=metrics.get("estimated_model_cost"),
        )

    def cancel_experiment(
        self,
        experiment_id: str,
        context: TenantContext | None = None,
    ) -> Experiment:
        """Cancel a running experiment and terminally retain its active runs."""

        experiment = self.get_experiment(experiment_id, context)
        try:
            cancelled = self._experiment_service().cancel_experiment(experiment_id)
        except ExperimentLifecycleError as exc:
            raise InvalidExperimentRequestError(str(exc)) from exc

        now = self._clock()
        cancelled_run_count = 0
        for run in self._evaluation_run_repository.find_by_experiment_id(experiment_id):
            if run.status not in {
                EvaluationRunStatus.PENDING,
                EvaluationRunStatus.RUNNING,
            }:
                continue
            cancelled_run = replace(
                run,
                started_at=run.started_at or now,
                completed_at=now,
                status=EvaluationRunStatus.CANCELLED,
                failure_reason=_CANCELLED_RUN_REASON,
            )
            self._evaluation_run_repository.save(cancelled_run)
            self._publish_evaluation_run_event(cancelled_run, context)
            cancelled_run_count += 1
        LOGGER.warning(
            "experiment_execution_cancelled experiment_id=%s cancelled_run_count=%s organization_id=%s project_id=%s",
            experiment.experiment_id,
            cancelled_run_count,
            context.organization_id if context else None,
            context.project_id if context else None,
        )
        return cancelled

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
        self._validate_comparable_dataset_versions((baseline, comparison))
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
        runtime_parameter_overrides: Sequence[str] | None = None,
        provider_installation_id: str | None = None,
        runtime_connection_id: str | None = None,
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
        explicit_parameters = frozenset(
            str(name)
            for name in (
                runtime_parameter_overrides
                if runtime_parameter_overrides is not None
                else runtime_parameters.keys()
            )
        )
        self._validate_candidate_runtime_parameters(
            model_id=model_id,
            model_version=model_version,
            explicit_parameters=explicit_parameters,
            context=context,
        )
        if not runtime_connection_id and self._model_requires_runtime_connection(
            model_id=model_id, model_version=model_version, context=context
        ):
            raise InvalidExperimentRequestError(
                "Candidate execution requires an active runtime connection."
            )
        if runtime_connection_id:
            self._validate_runtime_connection_for_candidate(
                runtime_connection_id=runtime_connection_id,
                model_id=model_id,
                model_version=model_version,
                context=context,
            )

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
                    **({"runtime_connection_id": runtime_connection_id} if runtime_connection_id else {}),
                    "runtime_parameter_overrides": sorted(explicit_parameters),
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
        repetitions: int = 1,
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

        self.validate_experiment_run(
            experiment_id,
            metric_specs=metric_specs,
            provider_config=provider_config,
            context=context,
        )
        LOGGER.info(
            "experiment_execution_started experiment_id=%s candidate_count=%s organization_id=%s project_id=%s",
            experiment_id,
            len(candidates),
            context.organization_id if context else None,
            context.project_id if context else None,
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

        if repetitions < 1:
            raise InvalidExperimentRequestError("Experiment repetitions must be at least one.")
        for candidate_index, candidate in enumerate(candidates * repetitions):
            if self._is_experiment_cancelled(experiment_id):
                return self._cancelled_run_snapshot(experiment_id)
            repetition_index = (candidate_index // len(candidates)) + 1
            run_idempotency_key = (
                f"{experiment.experiment_id}:{candidate.candidate_id}:repetition:{repetition_index}"
            )
            existing_run = self._run_for_idempotency_key(
                experiment_id=experiment.experiment_id,
                candidate_id=candidate.candidate_id,
                run_idempotency_key=run_idempotency_key,
            )
            if existing_run is not None:
                runs.append(existing_run)
                has_failures = has_failures or (
                    existing_run.status != EvaluationRunStatus.COMPLETED
                )
                continue
            candidate_started_at = perf_counter()
            evaluator_config = self._provider_config_for_candidate(
                candidate, provider_config or {}, context
            )
            runner_provenance = self._runner_provenance_for_candidate(
                candidate, evaluator_config
            )
            if runner_provenance is not None:
                runner_provenance = {
                    **runner_provenance,
                    "repetition": repetition_index,
                    "repetitions": repetitions,
                    "run_idempotency_key": run_idempotency_key,
                }
            else:
                runner_provenance = {
                    "repetition": repetition_index,
                    "repetitions": repetitions,
                    "run_idempotency_key": run_idempotency_key,
                }
            running_run = self._create_running_run(
                experiment=experiment,
                candidate=candidate,
                runner_provenance=runner_provenance,
            )
            LOGGER.info(
                "experiment_candidate_execution_started experiment_id=%s candidate_id=%s run_id=%s dataset_id=%s dataset_version=%s",
                experiment_id,
                candidate.candidate_id,
                running_run.run_id,
                candidate.dataset_id,
                candidate.dataset_version,
            )
            if self._provider_granularity(candidate.evaluation_provider) is EvaluationGranularity.BATCH:
                try:
                    completed_run = self._execute_batch_candidate_run(
                        experiment=experiment,
                        candidate=candidate,
                        running_run=running_run,
                        evaluator_config=evaluator_config,
                        context=context,
                    )
                    self._publish_evaluation_run_event(completed_run, context)
                    runs.append(completed_run)
                except Exception as exc:  # noqa: BLE001 - persist every provider failure as a terminal run.
                    persisted_run = (
                        self._evaluation_run_repository.find_by_id(running_run.run_id)
                        or running_run
                    )
                    failed_run = replace(
                        persisted_run,
                        completed_at=self._clock(),
                        status=EvaluationRunStatus.FAILED,
                        failure_reason=_safe_evaluation_failure_reason(exc),
                        runner_provenance={
                            **(persisted_run.runner_provenance or {}),
                            "batch_persistence_status": "partial"
                            if persisted_run.evaluated_item_count
                            else "not_persisted",
                        },
                    )
                    self._evaluation_run_repository.save(failed_run)
                    self._publish_evaluation_run_event(failed_run, context)
                    runs.append(failed_run)
                    has_failures = True
                continue
            try:
                def record_execution_progress(
                    total_item_count: int,
                    completed_item_count: int,
                    candidate_id: str = candidate.candidate_id,
                ) -> None:
                    nonlocal running_run
                    current_run = self._evaluation_run_repository.find_by_id(
                        running_run.run_id
                    )
                    if current_run is None or current_run.status != EvaluationRunStatus.RUNNING:
                        raise CandidateExecutionError(
                            "Experiment execution was cancelled before the next item could start."
                        )
                    running_run = replace(
                        current_run,
                        total_item_count=total_item_count,
                        completed_item_count=completed_item_count,
                    )
                    self._evaluation_run_repository.save(running_run)
                    LOGGER.info(
                        "experiment_candidate_execution_progress experiment_id=%s candidate_id=%s run_id=%s completed_item_count=%s total_item_count=%s",
                        experiment_id,
                        candidate_id,
                        running_run.run_id,
                        completed_item_count,
                        total_item_count,
                    )

                executions = self._candidate_execution_runtime_or_raise().execute(
                    experiment=experiment,
                    candidate=candidate,
                    run_id=running_run.run_id,
                    context=_required_tenant_context(context),
                    progress_callback=record_execution_progress,
                )
                if self._is_experiment_cancelled(experiment_id):
                    return self._cancelled_run_snapshot(experiment_id)
                LOGGER.info(
                    "experiment_candidate_execution_evidence_captured experiment_id=%s candidate_id=%s run_id=%s execution_count=%s elapsed_ms=%s",
                    experiment_id,
                    candidate.candidate_id,
                    running_run.run_id,
                    len(executions),
                    int((perf_counter() - candidate_started_at) * 1000),
                )
                LOGGER.info(
                    "experiment_candidate_evaluation_started experiment_id=%s candidate_id=%s run_id=%s evaluation_provider=%s execution_count=%s",
                    experiment_id,
                    candidate.candidate_id,
                    running_run.run_id,
                    candidate.evaluation_provider,
                    len(executions),
                )
                item_results = []
                for execution in executions:
                    if self._is_experiment_cancelled(experiment_id):
                        return self._cancelled_run_snapshot(experiment_id)
                    LOGGER.info(
                        "experiment_item_evaluation_started run_id=%s execution_id=%s evaluation_provider=%s",
                        running_run.run_id,
                        execution.execution_id,
                        candidate.evaluation_provider,
                    )
                    item_result = EvaluationApiService(
                        provider_registry=self._provider_registry,
                        evaluation_repository=self._evaluation_repository,
                        ontology_event_publisher=self._ontology_event_publisher,
                    ).submit_evaluation(
                        execution=execution,
                        provider_name=candidate.evaluation_provider,
                        metric_specs=metric_specs,
                        provider_config=evaluator_config,
                        context=context,
                    )
                    item_results.append(item_result)
                    running_run = replace(
                        running_run,
                        evaluated_item_count=len(item_results),
                    )
                    self._evaluation_run_repository.save(running_run)
                    if self._is_experiment_cancelled(experiment_id):
                        return self._cancelled_run_snapshot(experiment_id)
                    LOGGER.info(
                        "experiment_item_evaluation_completed run_id=%s execution_id=%s evaluation_id=%s",
                        running_run.run_id,
                        execution.execution_id,
                        item_result.evaluation_id,
                    )
                result = self._aggregate_item_evaluations(
                    run_id=running_run.run_id,
                    execution_ids=[execution.execution_id for execution in executions],
                    item_results=item_results,
                    context=context,
                )
                if self._is_experiment_cancelled(experiment_id):
                    return self._cancelled_run_snapshot(experiment_id)
                self._evaluation_repository.save(result)
                LOGGER.info(
                    "experiment_candidate_evaluation_aggregated experiment_id=%s candidate_id=%s run_id=%s item_count=%s evaluation_id=%s",
                    experiment_id,
                    candidate.candidate_id,
                    running_run.run_id,
                    len(executions),
                    result.evaluation_id,
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
                LOGGER.info(
                    "experiment_candidate_evaluation_completed experiment_id=%s candidate_id=%s run_id=%s elapsed_ms=%s",
                    experiment_id,
                    candidate.candidate_id,
                    running_run.run_id,
                    int((perf_counter() - candidate_started_at) * 1000),
                )
            except CandidateExecutionError as exc:
                if self._is_experiment_cancelled(experiment_id):
                    return self._cancelled_run_snapshot(experiment_id)
                LOGGER.warning(
                    "experiment_candidate_execution_failed experiment_id=%s candidate_id=%s run_id=%s elapsed_ms=%s failure_reason=%s",
                    experiment_id,
                    candidate.candidate_id,
                    running_run.run_id,
                    int((perf_counter() - candidate_started_at) * 1000),
                    _safe_evaluation_failure_reason(exc),
                )
                failed_run = replace(
                    running_run,
                    completed_at=self._clock(),
                    status=EvaluationRunStatus.EXECUTION_FAILED,
                    failure_reason=_safe_evaluation_failure_reason(exc),
                )
                self._evaluation_run_repository.save(failed_run)
                self._publish_evaluation_run_event(failed_run, context)
                runs.append(failed_run)
                has_failures = True
            except Exception as exc:  # noqa: BLE001 - candidate failures must be persisted as failed runs.
                if self._is_experiment_cancelled(experiment_id):
                    return self._cancelled_run_snapshot(experiment_id)
                LOGGER.warning(
                    "experiment_candidate_evaluation_failed experiment_id=%s candidate_id=%s run_id=%s elapsed_ms=%s error_type=%s",
                    experiment_id,
                    candidate.candidate_id,
                    running_run.run_id,
                    int((perf_counter() - candidate_started_at) * 1000),
                    type(exc).__name__,
                )
                failed_run = replace(
                    running_run,
                    completed_at=self._clock(),
                    status=EvaluationRunStatus.FAILED,
                    failure_reason=_safe_evaluation_failure_reason(exc),
                )
                self._evaluation_run_repository.save(failed_run)
                self._publish_evaluation_run_event(failed_run, context)
                runs.append(failed_run)
                has_failures = True

        if self._is_experiment_cancelled(experiment_id):
            return self._cancelled_run_snapshot(experiment_id)

        if has_failures:
            experiment_service.fail_experiment(experiment_id)
            LOGGER.warning(
                "experiment_execution_failed experiment_id=%s failed_run_count=%s",
                experiment_id,
                sum(run.status != EvaluationRunStatus.COMPLETED for run in runs),
            )
            return runs, None

        experiment_service.complete_experiment(experiment_id)
        leaderboard = self._ranking_service().generate_leaderboard(experiment_id)
        self._publish_leaderboard_event(leaderboard, context)
        LOGGER.info(
            "experiment_execution_completed experiment_id=%s completed_run_count=%s leaderboard_id=%s",
            experiment_id,
            len(runs),
            leaderboard.leaderboard_id,
        )
        return runs, leaderboard

    def validate_experiment_run(
        self,
        experiment_id: str,
        *,
        metric_specs: Sequence[EvaluationMetricSpec] | None = None,
        provider_config: Mapping[str, Any] | None = None,
        context: TenantContext | None = None,
    ) -> None:
        """Fail unsupported resolved provider combinations before job dispatch."""
        self.get_experiment(experiment_id, context)
        candidates = self._candidate_repository.find_by_experiment_id(experiment_id)
        if not candidates:
            raise InvalidExperimentRequestError(
                f"Experiment '{experiment_id}' has no candidates."
            )
        self._validate_candidate_providers_and_metrics(candidates, metric_specs or ())
        self._validate_comparable_dataset_versions(candidates)
        for candidate in candidates:
            resolved_config = self._provider_config_for_candidate(
                candidate, provider_config or {}, context
            )
            self._validate_provider_run_configuration(candidate, resolved_config)

    def get_leaderboard(
        self,
        experiment_id: str,
        context: TenantContext | None = None,
    ) -> Leaderboard:
        """
        Return the latest leaderboard only after an experiment completes.

        A leaderboard is a terminal comparison artifact. Generating one from
        partially completed runs would turn an interim snapshot into a false
        recommendation and persist that misleading outcome.
        """
        experiment = self.get_experiment(experiment_id, context)
        if experiment.status is not ExperimentStatus.COMPLETED:
            raise InvalidExperimentRequestError(
                "A leaderboard is available only after all evaluation runs complete."
            )
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
        runner_provenance: Mapping[str, Any] | None = None,
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
            runner_provenance=dict(runner_provenance)
            if runner_provenance is not None
            else None,
        )
        self._evaluation_run_repository.save(pending_run)
        running_run = replace(
            pending_run,
            started_at=self._clock(),
            status=EvaluationRunStatus.RUNNING,
        )
        self._evaluation_run_repository.save(running_run)
        return running_run

    def _run_for_idempotency_key(
        self,
        *,
        experiment_id: str,
        candidate_id: str,
        run_idempotency_key: str,
    ) -> EvaluationRun | None:
        """Return the durable candidate/repetition boundary, if already claimed."""
        for run in self._evaluation_run_repository.find_by_candidate_id(candidate_id):
            if run.experiment_id != experiment_id:
                continue
            provenance = run.runner_provenance or {}
            if provenance.get("run_idempotency_key") == run_idempotency_key:
                return run
        return None

    def _candidate_execution_runtime_or_raise(self) -> CandidateExecutionRuntime:
        if self._candidate_execution_runtime is None:
            raise CandidateExecutionError(
                "Candidate execution runtime is not configured for this deployment."
            )
        return self._candidate_execution_runtime

    def _provider_granularity(self, provider_name: str) -> EvaluationGranularity:
        return self._resolve_provider(
            provider_name
        ).descriptor.capabilities.evaluation_granularity

    def _execute_batch_candidate_run(
        self,
        *,
        experiment: Experiment,
        candidate: ExperimentCandidate,
        running_run: EvaluationRun,
        evaluator_config: Mapping[str, Any],
        context: TenantContext | None,
    ) -> EvaluationRun:
        """Persist one provider invocation's child samples under one run.

        Individual provider SDK records are converted by the adapter to the
        generic batch boundary before this service assigns durable identities.
        A persistence failure leaves the run non-complete with its persisted
        item counts, making a partial batch visible rather than silently
        aggregating incomplete evidence.
        """
        provider = self._resolve_provider(candidate.evaluation_provider)
        evaluate_batch = getattr(provider, "evaluate_batch", None)
        if not callable(evaluate_batch):
            raise InvalidExperimentRequestError(
                f"Provider '{candidate.evaluation_provider}' declares BATCH granularity "
                "but does not implement evaluate_batch."
            )
        request_execution = WorkflowExecution(
            workflow_id=experiment.experiment_id,
            execution_id=running_run.run_id,
            workflow_name=experiment.name,
            workflow_version=candidate.dataset_version,
            execution_status="COMPLETED",
            input={},
            final_state={},
            events=[],
            metadata={"dataset_version": candidate.dataset_version},
        )
        batch = self._provider_execution_deadline.call(
            self._provider_execution_timeout_seconds(provider, evaluator_config),
            lambda: evaluate_batch(
                EvaluationRequest(
                    execution=request_execution,
                    dataset=EvaluationDatasetBuilder().build(request_execution),
                    provider_config=dict(evaluator_config),
                )
            ),
        )
        if not isinstance(batch, BatchEvaluationResult):
            raise InvalidExperimentRequestError(
                "Batch evaluation providers must return BatchEvaluationResult."
            )
        current_run = replace(
            running_run,
            total_item_count=len(batch.sample_results),
        )
        self._evaluation_run_repository.save(current_run)
        item_results: list[EvaluationResult] = []
        try:
            for sample in batch.sample_results:
                execution_id = f"{current_run.run_id}:sample:{sample.sample_id}"
                item_result = EvaluationResult(
                    evaluation_id=f"{execution_id}:evaluation",
                    execution_id=execution_id,
                    evaluator_type=provider.descriptor.name,
                    evaluator_version=provider.descriptor.version,
                    metrics=list(sample.metrics),
                    metadata={
                        **dict(sample.metadata),
                        "evaluation_run_id": current_run.run_id,
                        "sample_id": sample.sample_id,
                    },
                    artifacts=list(sample.artifacts),
                    provider_metadata=dict(sample.provider_metadata),
                    provider_descriptor_snapshot=provider.descriptor.to_dict(),
                    organization_id=context.organization_id if context else "org_default",
                    project_id=(context.project_id or "") if context else "project_default",
                )
                self._evaluation_repository.save(item_result)
                self._record_batch_sample_execution(
                    item_result=item_result,
                    provider_name=provider.descriptor.name,
                    provider_version=provider.descriptor.version,
                    context=context,
                )
                item_results.append(item_result)
                current_run = replace(
                    current_run,
                    completed_item_count=len(item_results),
                    evaluated_item_count=len(item_results),
                )
                self._evaluation_run_repository.save(current_run)
        except Exception:
            self._evaluation_run_repository.save(
                replace(
                    current_run,
                    runner_provenance={
                        **(current_run.runner_provenance or {}),
                        "batch_persistence_status": "partial",
                    },
                )
            )
            raise
        aggregate = self._aggregate_item_evaluations(
            run_id=current_run.run_id,
            execution_ids=[result.execution_id for result in item_results],
            item_results=item_results,
            context=context,
            batch_artifacts=batch.artifacts,
        )
        self._evaluation_repository.save(aggregate)
        completed_run = replace(
            current_run,
            evaluation_result_id=aggregate.evaluation_id,
            completed_at=self._clock(),
            status=EvaluationRunStatus.COMPLETED,
        )
        self._evaluation_run_repository.save(completed_run)
        return completed_run

    def _record_batch_sample_execution(
        self,
        *,
        item_result: EvaluationResult,
        provider_name: str,
        provider_version: str,
        context: TenantContext | None,
    ) -> None:
        """Link batch samples to the authoritative Agent Runtime event source.

        This is deliberately optional for non-runtime deployments.  It records
        only safe provider-normalized facts and references the evaluation
        artifact that is already durably persisted with the sample result.
        """
        if self._agent_execution_service is None or context is None:
            return
        runtime = self._agent_execution_service
        runner_provenance = dict(item_result.provider_metadata.get("runner_provenance", {}))
        execution = runtime.ingest_start(
            agent_id=provider_name,
            agent_name=f"{provider_name} evaluation sample",
            agent_version=provider_version,
            external_execution_id=item_result.execution_id,
            runtime_provider=provider_name,
            correlation_id=item_result.metadata.get("evaluation_run_id"),
            metadata={
                "evaluation_result_id": item_result.evaluation_id,
                "evaluation_run_id": item_result.metadata.get("evaluation_run_id"),
                "sample_id": item_result.metadata.get("sample_id"),
                "runner_provenance": runner_provenance,
            },
            context=context,
        )
        artifact = next(
            (
                value
                for value in item_result.artifacts
                if value.artifact_type == "observable_execution_events"
            ),
            None,
        )
        artifact_reference = (
            f"evaluation-artifact:{item_result.evaluation_id}:observable-events"
            if artifact is not None
            else None
        )
        if artifact is not None and isinstance(artifact.payload, Mapping):
            source_events = artifact.payload.get("events", [])
            if isinstance(source_events, Sequence):
                for source_event in source_events:
                    if not isinstance(source_event, Mapping):
                        continue
                    kind = str(source_event.get("kind", "")).lower()
                    event_type = {
                        "tool": EventType.TOOL_CALL,
                        "tool_call": EventType.TOOL_CALL,
                        "tool_result": EventType.TOOL_CALL,
                        "model": EventType.MODEL_CALL,
                        "model_call": EventType.MODEL_CALL,
                        "generate": EventType.MODEL_CALL,
                        "error": EventType.ERROR,
                        "timeout": EventType.ERROR,
                        "failure": EventType.ERROR,
                    }.get(kind)
                    if event_type is None:
                        continue
                    attributes = {
                        key: value
                        for key, value in source_event.items()
                        if key not in {"sequence", "kind"}
                    }
                    runtime.ingest_event(
                        execution_id=execution.execution_id,
                        event_type=event_type,
                        attributes=attributes,
                        context=context,
                        idempotency_key=f"{item_result.evaluation_id}:source:{source_event.get('sequence')}",
                        actor_id=provider_name,
                        actor_type=ActorType.TOOL if event_type is EventType.TOOL_CALL else ActorType.MODEL if event_type is EventType.MODEL_CALL else ActorType.SYSTEM,
                        evidence_references=[artifact_reference] if artifact_reference else [],
                    )
        metrics = {metric.metric_name: metric.metric_value for metric in item_result.metrics}
        runtime.ingest_event(
            execution_id=execution.execution_id,
            event_type=EventType.EVALUATION,
            attributes={
                "evaluation_result_id": item_result.evaluation_id,
                "sample_status": item_result.metadata.get("sample_status"),
                **metrics,
            },
            context=context,
            idempotency_key=f"{item_result.evaluation_id}:evaluation",
            actor_id=provider_name,
            actor_type=ActorType.EVALUATOR,
            evidence_references=[artifact_reference] if artifact_reference else [],
        )
        runtime.mark_completed(
            execution.execution_id,
            status=AgentExecutionStatus.SUCCEEDED,
            context=context,
        )

    def _aggregate_item_evaluations(
        self,
        *,
        run_id: str,
        execution_ids: Sequence[str],
        item_results: Sequence[EvaluationResult],
        context: TenantContext | None,
        batch_artifacts: Sequence[EvaluationArtifact] = (),
    ) -> EvaluationResult:
        if not execution_ids or len(execution_ids) != len(item_results):
            raise ValueError(
                "Candidate evaluation requires one result for every execution item."
            )
        metric_values: dict[str, list[float]] = {}
        for result in item_results:
            for metric in result.metrics:
                metric_values.setdefault(metric.metric_name, []).append(metric.metric_value)
        first = item_results[0]
        return EvaluationResult(
            evaluation_id=f"{run_id}:aggregate",
            execution_id=run_id,
            evaluator_type=first.evaluator_type,
            evaluator_version=first.evaluator_version,
            metrics=[
                EvaluationMetric(metric_name=name, metric_value=sum(values) / len(values))
                for name, values in sorted(metric_values.items())
            ],
            metadata={
                "aggregation": "mean",
                "item_execution_ids": list(execution_ids),
                "item_evaluation_ids": [result.evaluation_id for result in item_results],
                **(
                    {"runner_provenance": first.provider_metadata["runner_provenance"]}
                    if first.provider_metadata.get("runner_provenance") is not None
                    else {}
                ),
            },
            artifacts=[
                EvaluationArtifact(
                    artifact_type="candidate_execution_set",
                    metadata={"item_count": len(execution_ids)},
                )
            ] + list(batch_artifacts),
            provider_descriptor_snapshot=first.provider_descriptor_snapshot,
            provider_metadata=dict(first.provider_metadata),
            organization_id=context.organization_id if context else "org_default",
            project_id=(context.project_id or "") if context else "project_default",
        )

    @staticmethod
    def _validate_comparable_dataset_versions(
        candidates: Sequence[ExperimentCandidate],
    ) -> None:
        if len({(candidate.dataset_id, candidate.dataset_version) for candidate in candidates}) != 1:
            raise InvalidExperimentRequestError(
                "Experiment comparison requires every candidate to use the same immutable dataset version."
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
        runner_config = candidate.metadata.get("evaluation_runner_config")
        if runner_config is not None and not isinstance(runner_config, Mapping):
            raise InvalidExperimentRequestError(
                "evaluation_runner_config must be an object."
            )
        candidate_config = dict(runner_config or {})
        if not installation_id:
            return {**candidate_config, **dict(request_config)}
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
        return {**installation_config, **candidate_config, **dict(request_config)}

    def _workload_estimate_for_candidate(
        self,
        candidate: ExperimentCandidate,
        context: TenantContext,
    ) -> EvaluationWorkloadEstimate | None:
        """Use a provider's optional generic planner without leaking its config."""
        provider = self._resolve_provider(candidate.evaluation_provider)
        estimate_workload = getattr(provider, "estimate_workload", None)
        if not callable(estimate_workload):
            return None
        estimate = estimate_workload(
            self._provider_config_for_candidate(candidate, {}, context)
        )
        if not isinstance(estimate, EvaluationWorkloadEstimate):
            raise InvalidExperimentRequestError(
                "Evaluation provider returned an invalid workload estimate."
            )
        return estimate

    def _validate_provider_run_configuration(
        self,
        candidate: ExperimentCandidate,
        provider_config: Mapping[str, Any],
    ) -> None:
        """Invoke a provider's optional pre-dispatch capability check."""
        provider = self._resolve_provider(candidate.evaluation_provider)
        validate = getattr(provider, "validate_run_configuration", None)
        if callable(validate):
            try:
                validate(provider_config)
            except ValueError as exc:
                raise InvalidExperimentRequestError(str(exc)) from exc

    @staticmethod
    def _provider_execution_timeout_seconds(
        provider: Any,
        provider_config: Mapping[str, Any],
    ) -> int | None:
        """Read a provider-declared bound without interpreting provider config."""
        timeout = getattr(provider, "execution_timeout_seconds", None)
        if not callable(timeout):
            return None
        value = timeout(provider_config)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
        ):
            raise InvalidExperimentRequestError(
                "Evaluation provider returned an invalid execution timeout."
            )
        return value

    def _runner_provenance_for_candidate(
        self,
        candidate: ExperimentCandidate,
        provider_config: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        provider = self._resolve_provider(candidate.evaluation_provider)
        capture = getattr(provider, "capture_runner_provenance", None)
        if not callable(capture):
            return None
        provenance = capture(provider_config, candidate.dataset_version)
        if not isinstance(provenance, Mapping):
            raise InvalidExperimentRequestError(
                "Evaluation runner returned invalid provenance."
            )
        return dict(provenance)

    def _validate_runtime_connection_for_candidate(
        self,
        *,
        runtime_connection_id: str,
        model_id: str,
        model_version: str,
        context: TenantContext | None,
    ) -> None:
        if self._runtime_connection_service is None or context is None:
            raise InvalidExperimentRequestError(
                "Runtime connections require a tenant-scoped runtime."
            )
        model = self._model_repository.find_by_id(
            model_id,
            context.organization_id,
            context.project_id or "",
        )
        if model is None or model.version != model_version:
            raise InvalidExperimentRequestError(
                "Candidate references an unknown model version."
            )
        try:
            self._runtime_connection_service.validate_model_compatibility(
                runtime_connection_id,
                model.provider,
                context,
            )
        except (
            RuntimeConnectionDisabledError,
            RuntimeConnectionNotFoundError,
            RuntimeConnectionProviderMismatchError,
            ValueError,
        ) as exc:
            raise InvalidExperimentRequestError(str(exc)) from exc

    def _reconcile_interrupted_runs(self, experiment: Experiment) -> bool:
        """Terminally record synchronous runs orphaned by a process restart."""

        if experiment.status == ExperimentStatus.CANCELLED:
            return False

        interrupted = [
            run
            for run in self._evaluation_run_repository.find_by_experiment_id(
                experiment.experiment_id
            )
            if run.status == EvaluationRunStatus.RUNNING
            and run.started_at is not None
            and run.started_at < _PROCESS_STARTED_AT
        ]
        if not interrupted:
            return False

        now = self._clock()
        for run in interrupted:
            self._evaluation_run_repository.save(
                replace(
                    run,
                    completed_at=now,
                    status=EvaluationRunStatus.EXECUTION_FAILED,
                    failure_reason=_INTERRUPTED_RUN_REASON,
                )
            )
        if experiment.status.value == "RUNNING":
            self._experiment_service().fail_experiment(experiment.experiment_id)
        LOGGER.warning(
            "experiment_interrupted_runs_reconciled experiment_id=%s interrupted_run_count=%s process_started_at=%s",
            experiment.experiment_id,
            len(interrupted),
            _PROCESS_STARTED_AT.isoformat(),
        )
        return True

    def _is_experiment_cancelled(self, experiment_id: str) -> bool:
        experiment = self._experiment_repository.find_by_id(experiment_id)
        return experiment is not None and experiment.status == ExperimentStatus.CANCELLED

    def _cancelled_run_snapshot(
        self, experiment_id: str
    ) -> tuple[list[EvaluationRun], None]:
        """Return terminal run records after a cancellation is observed.

        A cancellation can arrive while a provider call is in flight. The
        caller that began that call holds an older ``RUNNING`` instance and
        may save its progress immediately before observing the experiment's
        terminal state. Reconcile that stale write here so cancellation cannot
        leave a child run appearing active.
        """
        now = self._clock()
        reconciled_run_count = 0
        runs: list[EvaluationRun] = []
        for run in self._evaluation_run_repository.find_by_experiment_id(experiment_id):
            if run.status not in {
                EvaluationRunStatus.PENDING,
                EvaluationRunStatus.RUNNING,
            }:
                runs.append(run)
                continue
            cancelled_run = replace(
                run,
                started_at=run.started_at or now,
                completed_at=now,
                status=EvaluationRunStatus.CANCELLED,
                failure_reason=_CANCELLED_RUN_REASON,
            )
            self._evaluation_run_repository.save(cancelled_run)
            runs.append(cancelled_run)
            reconciled_run_count += 1
        LOGGER.warning(
            "experiment_execution_cancellation_observed experiment_id=%s reconciled_run_count=%s",
            experiment_id,
            reconciled_run_count,
        )
        return runs, None

    def _model_requires_runtime_connection(
        self,
        *,
        model_id: str,
        model_version: str,
        context: TenantContext | None,
    ) -> bool:
        if context is None:
            raise InvalidExperimentRequestError(
                "Candidate runtime parameters require a tenant-scoped runtime."
            )
        model = self._model_repository.find_by_id(
            model_id, context.organization_id, context.project_id or ""
        )
        if model is None or model.version != model_version:
            raise InvalidExperimentRequestError("Candidate references an unknown model version.")
        return runtime_model_provider_key(model.provider) in {
            "openai",
            "anthropic",
            "custom",
        }

    def _validate_candidate_runtime_parameters(
        self,
        *,
        model_id: str,
        model_version: str,
        explicit_parameters: frozenset[str],
        context: TenantContext | None,
    ) -> None:
        if context is None:
            raise InvalidExperimentRequestError(
                "Candidate runtime parameters require a tenant-scoped runtime."
            )
        model = self._model_repository.find_by_id(
            model_id, context.organization_id, context.project_id or ""
        )
        if model is None or model.version != model_version:
            raise InvalidExperimentRequestError("Candidate references an unknown model version.")
        if model.runtime_capabilities.verification.value == "UNVERIFIED":
            return
        unsupported = sorted(
            name
            for name in explicit_parameters
            if not model.runtime_capabilities.supports(
                "max_output_tokens" if name == "max_tokens" else name
            )
        )
        if unsupported:
            raise InvalidExperimentRequestError(
                "The selected model version does not support: " + ", ".join(unsupported) + "."
            )

    def _resolve_runtime_connection_for_candidate(
        self,
        candidate: ExperimentCandidate,
        context: TenantContext | None,
    ) -> None:
        """Resolve the selected connection immediately before candidate use.

        The current experiment evaluator scores recorded execution evidence;
        it does not invoke the candidate model yet.  Resolving here exercises
        the governed connection contract (scope, enabled state, provider
        compatibility and current secret reference) without adding the
        resolved credential to the candidate, run, API response or job.
        """

        runtime_connection_id = candidate.metadata.get("runtime_connection_id")
        if not runtime_connection_id:
            return
        if self._runtime_connection_service is None or context is None:
            raise InvalidExperimentRequestError(
                "Runtime connections require a tenant-scoped runtime."
            )
        model = self._model_repository.find_by_id(
            candidate.model_id,
            context.organization_id,
            context.project_id or "",
        )
        if model is None or model.version != candidate.model_version:
            raise InvalidExperimentRequestError(
                "Candidate references an unknown model version."
            )
        self._runtime_connection_service.resolve_runtime_config(
            str(runtime_connection_id), model.provider, context
        )

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


def _safe_evaluation_failure_reason(error: Exception) -> str:
    """Return an operator-useful error that cannot disclose provider secrets."""

    safe_errors = (
        CandidateExecutionError,
        InvalidExperimentRequestError,
        EvaluationProviderNotFoundError,
        ProviderInstallationDisabledError,
        ProviderInstallationNotFoundError,
        ProviderInstallationTypeUnavailableError,
        RuntimeConnectionDisabledError,
        RuntimeConnectionNotFoundError,
        RuntimeConnectionProviderMismatchError,
        ExecutionDeadlineExceeded,
        ExecutionDeadlineUnavailable,
        ValueError,
    )
    if isinstance(error, safe_errors):
        return " ".join(str(error).split())[:500]
    return (
        "Evaluation provider execution failed "
        f"({type(error).__name__}). Inspect the API or worker logs for operational detail."
    )


def _model_latency_ms(metadata: Mapping[str, Any]) -> int | None:
    """Read safe model latency from immutable candidate execution evidence."""
    runtime_evidence = metadata.get("runtime_evidence")
    if isinstance(runtime_evidence, Mapping):
        value = runtime_evidence.get("latency_ms")
    else:
        value = metadata.get("model_latency_ms")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _number_value(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _report_call_role(
    role: str,
    calls: Sequence[Mapping[str, object]],
) -> EvaluationReportCallRole:
    def average(name: str) -> float | None:
        values = [_number_value(call.get(name)) for call in calls]
        observed = [value for value in values if value is not None]
        return sum(observed) / len(observed) if observed else None

    def shared_boolean(name: str) -> bool | None:
        values = [call.get(name) for call in calls if isinstance(call.get(name), bool)]
        return values[0] if values and len(set(values)) == 1 else None

    return EvaluationReportCallRole(
        call_role=role,
        call_count=len(calls),
        input_tokens=average("input_tokens"),
        output_tokens=average("output_tokens"),
        total_tokens=average("total_tokens"),
        duration_ms=average("duration_ms"),
        original_task_included=shared_boolean("original_task_included"),
        prior_conversation_retained=shared_boolean("prior_conversation_retained"),
    )


def _required_tenant_context(context: TenantContext | None) -> TenantContext:
    if context is None:
        raise CandidateExecutionError("Candidate execution requires a tenant-scoped runtime.")
    return context
