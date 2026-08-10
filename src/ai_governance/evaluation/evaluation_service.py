from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.domain.evaluation_result import EvaluationResult
from ai_governance.evaluation.evaluation_metrics import EvaluationMetricSpec
from ai_governance.evaluation.evaluation_request import EvaluationRequest
from ai_governance.providers.evaluation_provider import EvaluationProvider
from ai_governance.providers.errors import ProviderContractError
from ai_governance.providers.provider_metadata import ProviderDescriptorSnapshot
from ai_governance.providers.provider_registry import EvaluationProviderRegistry
from ai_governance.services.dataset_builder import EvaluationDatasetBuilder


class EvaluationService:
    """
    Application service responsible for evaluation orchestration.

    EvaluationService coordinates the transformation of a workflow
    execution into an evaluation result.

    Responsibilities:

    - Build evaluation datasets
    - Invoke evaluation providers
    - Return evaluation results

    Non-Responsibilities:

    - Workflow retrieval
    - Evaluation persistence
    - Worker lifecycle management
    - Provider-specific evaluation logic

    Architectural Flow:

        WorkflowExecution
                ↓
        EvaluationDatasetBuilder
                ↓
        EvaluationDataset
                ↓
        EvaluationProvider
                ↓
        EvaluationResult

    Design Goals:

    - Separation of orchestration and evaluation logic
    - Provider independence
    - Testability
    - Extensibility

    Example:
        service = EvaluationService(
            provider_registry=registry,
            provider_name="example_provider",
        )

        result = service.evaluate(
            execution,
            provider_config={"temperature": 0},
        )
    """

    def __init__(
        self,
        provider: EvaluationProvider | None = None,
        dataset_builder: EvaluationDatasetBuilder | None = None,
        provider_registry: EvaluationProviderRegistry | None = None,
        provider_name: str | None = None,
    ):
        if provider is not None and (
            provider_registry is not None or provider_name is not None
        ):
            raise ProviderContractError(
                "Provide either a direct provider or provider registry/name, not both."
            )

        if provider is None and (provider_registry is None) != (
            provider_name is None
        ):
            raise ProviderContractError(
                "Provider registry resolution requires both provider_registry and provider_name."
            )

        if provider is None and provider_registry is None:
            raise ProviderContractError(
                "EvaluationService requires a provider or provider registry/name."
            )

        self._provider = provider
        self._provider_registry = provider_registry
        self._provider_name = provider_name
        self._dataset_builder = dataset_builder or EvaluationDatasetBuilder()

    def evaluate(
        self,
        execution: WorkflowExecution,
        provider_config: dict[str, object] | None = None,
        metric_specs: Sequence[EvaluationMetricSpec] | None = None,
    ) -> EvaluationResult:
        """
        Evaluate a workflow execution using the configured provider.

        The service builds a canonical dataset, resolves the provider,
        snapshots the provider descriptor, and passes both the dataset and
        snapshot through the provider boundary. If the provider returns a
        result without a descriptor snapshot, the service attaches the snapshot
        before returning.

        Args:
            execution: Workflow execution to evaluate.
            provider_config: Optional provider-specific runtime settings.
            metric_specs: Optional metric specs to request from the provider.
                When omitted, providers may fall back to their configured
                default metrics.

        Returns:
            EvaluationResult with metrics, provider metadata, and descriptor
            snapshot information.
        """
        dataset = self._dataset_builder.build(execution)
        provider = self._resolve_provider()
        descriptor = provider.descriptor
        snapshot = ProviderDescriptorSnapshot.from_descriptor(descriptor)
        request_kwargs = {}
        if metric_specs is not None:
            request_kwargs["metric_specs"] = metric_specs

        request = EvaluationRequest(
            execution=execution,
            dataset=dataset,
            provider_config=provider_config or {},
            provider_descriptor_snapshot=snapshot.to_dict(),
            **request_kwargs,
        )

        result = provider.evaluate(request)

        if result.provider_descriptor_snapshot is None:
            result = replace(
                result,
                provider_descriptor_snapshot=snapshot.to_dict(),
            )

        return result

    def _resolve_provider(self) -> EvaluationProvider:
        """
        Resolve the provider from direct injection or registry configuration.
        """
        if self._provider is not None:
            return self._provider

        if self._provider_registry is None or self._provider_name is None:
            raise ProviderContractError("No evaluation provider is configured.")

        return self._provider_registry.get(self._provider_name)
