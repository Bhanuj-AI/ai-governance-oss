from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from ai_governance.domain.evaluation_result import EvaluationResult
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.evaluation import EvaluationService
from ai_governance.evaluation.evaluation_metrics import (
    EvaluationMetricSpec,
    normalize_metric_name,
)
from ai_governance.ontology.synchronization import (
    OntologySyncEventPublisherProtocol,
)
from ai_governance.providers.errors import ProviderNotFoundError
from ai_governance.providers.provider_registry import EvaluationProviderRegistry
from ai_governance.repositories.evaluation_repository import EvaluationRepository
from ai_governance.services.provider_installation_service import ProviderInstallationService
from ai_governance.services.dataset_builder import EvaluationDatasetBuilder
from ai_governance.tenancy.domain import TenantContext
from ai_governance.settings_control.operational import (
    duration_seconds,
    evaluate_thresholds,
    setting_context,
)


class EvaluationProviderNotFoundError(Exception):
    """
    Raised when the requested REST evaluation provider is not registered.
    """

    def __init__(
        self,
        provider_name: str,
    ) -> None:
        self.provider_name = provider_name
        super().__init__(f"Provider '{provider_name}' was not found.")


class UnsupportedMetricError(Exception):
    """
    Raised when a requested metric is not supported by the provider.
    """

    def __init__(
        self,
        metric: str,
        provider_name: str,
    ) -> None:
        self.metric = metric
        self.provider_name = provider_name
        super().__init__(
            f"Metric '{metric}' is not supported by provider '{provider_name}'."
        )


class EvaluationNotFoundError(Exception):
    """
    Raised when a persisted evaluation cannot be found.
    """

    def __init__(
        self,
        evaluation_id: str | None = None,
        execution_id: str | None = None,
    ) -> None:
        self.evaluation_id = evaluation_id
        self.execution_id = execution_id
        if evaluation_id is not None:
            message = f"Evaluation '{evaluation_id}' was not found."
        else:
            message = f"No evaluation was found for execution '{execution_id}'."
        super().__init__(message)


class EvaluationApiService:
    """
    Application facade for REST evaluation use cases.

    The REST layer uses this service to submit synchronous evaluations and
    read persisted evaluation results without reaching into repositories or
    provider adapters directly.
    """

    def __init__(
        self,
        provider_registry: EvaluationProviderRegistry,
        evaluation_repository: EvaluationRepository,
        dataset_builder: EvaluationDatasetBuilder | None = None,
        ontology_event_publisher: OntologySyncEventPublisherProtocol | None = None,
        configuration_service=None,
        provider_installation_service: ProviderInstallationService | None = None,
    ) -> None:
        self._provider_registry = provider_registry
        self._evaluation_repository = evaluation_repository
        self._dataset_builder = dataset_builder
        self._ontology_event_publisher = ontology_event_publisher
        self._configuration_service = configuration_service
        self._provider_installations = provider_installation_service

    def submit_evaluation(
        self,
        execution: WorkflowExecution,
        provider_name: str | None,
        metric_specs: Sequence[EvaluationMetricSpec] | None = None,
        provider_config: dict[str, object] | None = None,
        provider_installation_id: str | None = None,
        context: TenantContext | None = None,
    ) -> EvaluationResult:
        """
        Evaluate an execution synchronously and persist the result.
        """
        provider_name, effective_provider_config = self._resolve_installation(
            provider_name=provider_name,
            provider_config=provider_config or {},
            provider_installation_id=provider_installation_id,
            context=context,
        )
        provider = self._resolve_provider(provider_name)
        self._validate_metric_specs(
            metric_specs=metric_specs or (),
            provider_name=provider.descriptor.name,
            supported_metrics=provider.descriptor.capabilities.supported_metrics,
        )

        service = EvaluationService(
            provider_registry=self._provider_registry,
            provider_name=provider_name,
            dataset_builder=self._dataset_builder,
        )
        result = service.evaluate(
            execution,
            provider_config=effective_provider_config,
            metric_specs=metric_specs,
        )
        model_latency_ms = _model_latency_ms(execution)
        if model_latency_ms is not None:
            result.metadata["model_latency_ms"] = model_latency_ms
        if context is not None:
            result.organization_id = context.organization_id
            result.project_id = context.project_id or ""
        if self._configuration_service is not None:
            setting_scope = setting_context(context)
            default_threshold = float(
                self._configuration_service.get(
                    "evaluation.pass_threshold", setting_scope
                )
            )
            configured_thresholds = dict(
                self._configuration_service.get("evaluation.thresholds", setting_scope)
            )
            outcome = evaluate_thresholds(
                result.metrics, default_threshold, configured_thresholds
            )
            result.metadata["ai_governance_evaluation_outcome"] = {
                "passed": outcome.passed,
                "score": outcome.score,
                "default_threshold": outcome.threshold,
                "metric_thresholds": outcome.metric_thresholds,
                "failures": list(outcome.failures),
            }
        self._evaluation_repository.save(result)
        self._publish_evaluation_event(result)
        return result

    def _resolve_installation(
        self,
        *,
        provider_name: str | None,
        provider_config: dict[str, object],
        provider_installation_id: str | None,
        context: TenantContext | None,
    ) -> tuple[str, dict[str, object]]:
        """Resolve a tenant configuration immediately before adapter invocation."""
        if not provider_installation_id:
            if not provider_name:
                raise EvaluationProviderNotFoundError("")
            return provider_name, dict(provider_config)
        if self._provider_installations is None or context is None:
            raise ValueError(
                "Provider installations require a tenant-scoped evaluation runtime."
            )
        installation, installation_config = (
            self._provider_installations.resolve_runtime_config(
                provider_installation_id, context
            )
        )
        if provider_name and provider_name != installation.provider_type:
            raise ValueError(
                "Provider installation type does not match the requested provider."
            )
        return installation.provider_type, {
            **dict(provider_config),
            **installation_config,
        }

    def get_evaluation(
        self,
        evaluation_id: str,
        context: TenantContext | None = None,
    ) -> EvaluationResult:
        """
        Return a persisted evaluation result by ID.
        """
        result = self._evaluation_repository.find_by_evaluation_id(evaluation_id)
        if result is None or not _evaluation_in_context(result, context):
            raise EvaluationNotFoundError(evaluation_id=evaluation_id)
        return result

    def get_history(
        self,
        execution_id: str,
        context: TenantContext | None = None,
    ) -> list[EvaluationResult]:
        """
        Return persisted evaluations for an execution.
        """
        results = [
            result
            for result in self._evaluation_repository.find_by_execution_id(execution_id)
            if _evaluation_in_context(result, context)
        ]
        if self._configuration_service is None:
            return results
        retention = duration_seconds(
            self._configuration_service.get(
                "evaluation.retention", setting_context(context)
            )
        )
        cutoff = datetime.now(UTC).timestamp() - retention
        return [result for result in results if result.created_at.timestamp() >= cutoff]

    def get_latest(
        self,
        execution_id: str,
        context: TenantContext | None = None,
    ) -> EvaluationResult:
        """
        Return the most recently created evaluation for an execution.
        """
        results = self.get_history(execution_id, context)
        if not results:
            raise EvaluationNotFoundError(execution_id=execution_id)

        return max(results, key=lambda result: result.created_at)

    def _resolve_provider(
        self,
        provider_name: str,
    ):
        try:
            return self._provider_registry.get(provider_name)
        except ProviderNotFoundError as exc:
            raise EvaluationProviderNotFoundError(provider_name) from exc

    def _validate_metric_specs(
        self,
        metric_specs: Sequence[EvaluationMetricSpec],
        provider_name: str,
        supported_metrics: Sequence[str],
    ) -> None:
        supported = {normalize_metric_name(metric) for metric in supported_metrics}
        for metric_spec in metric_specs:
            if metric_spec.name not in supported:
                raise UnsupportedMetricError(
                    metric=metric_spec.name,
                    provider_name=provider_name,
                )

    def _publish_evaluation_event(
        self,
        result: EvaluationResult,
    ) -> None:
        if self._ontology_event_publisher is None:
            return
        self._ontology_event_publisher.publish_entity_event(
            "EvaluationCompleted",
            entity_type="EvaluationResult",
            entity_id=result.evaluation_id,
            scope_identifier="evaluation_repository",
            payload={
                "evaluation_id": result.evaluation_id,
                "execution_id": result.execution_id,
                "provider": result.evaluator_type,
            },
        )


def _evaluation_in_context(
    result: EvaluationResult, context: TenantContext | None
) -> bool:
    return context is None or (
        result.organization_id == context.organization_id
        and result.project_id == context.project_id
    )


def _model_latency_ms(execution: WorkflowExecution) -> int | None:
    """Extract the safe model invocation latency from candidate evidence."""
    runtime_evidence = execution.metadata.get("runtime_evidence")
    if not isinstance(runtime_evidence, Mapping):
        return None
    value = runtime_evidence.get("latency_ms")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value
