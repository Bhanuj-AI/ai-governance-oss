from uuid import uuid4

from ai_governance.domain.evaluation_result import (
    EvaluationMetric,
    EvaluationResult,
)
from ai_governance.evaluation.evaluation_metrics import (
    ANSWER_RELEVANCE,
    CONTEXT_RELEVANCE,
    GROUNDEDNESS,
    SUPPORTED_EVALUATION_METRICS,
)
from ai_governance.evaluation.evaluation_request import EvaluationRequest
from ai_governance.providers.evaluation_provider import EvaluationProvider
from ai_governance.providers.provider_capabilities import ProviderCapabilities
from ai_governance.providers.provider_descriptor import ProviderDescriptor
from ai_governance.providers.schema_loader import load_provider_configuration_schema


class MockEvaluationProvider(EvaluationProvider):
    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            name="mock",
            display_name="Mock",
            version="1.0.0",
            adapter_version="1.0.0",
            capabilities=ProviderCapabilities(
                supported_metrics=(
                    ANSWER_RELEVANCE,
                    CONTEXT_RELEVANCE,
                    GROUNDEDNESS,
                ),
                supports_artifacts=False,
                supports_explanations=True,
            ),
            configuration_schema=load_provider_configuration_schema("mock"),
        )

    def validate_configuration(self, _provider_config: dict[str, object]) -> None:
        """Mock is entirely local and needs no external connection."""

    def evaluate(self, request: EvaluationRequest) -> EvaluationResult:
        unsupported_metrics = [
            metric_spec.name
            for metric_spec in request.metric_specs
            if metric_spec.name not in SUPPORTED_EVALUATION_METRICS
        ]
        if unsupported_metrics:
            raise ValueError(
                "Unsupported mock metrics: "
                + ", ".join(unsupported_metrics)
            )

        return EvaluationResult(
            evaluation_id=str(uuid4()),
            execution_id=request.execution_id,
            evaluator_type=self.descriptor.name,
            evaluator_version="1.0.0",
            metrics=[
                EvaluationMetric(
                    metric_name=ANSWER_RELEVANCE,
                    metric_value=1.0,
                )
            ],
            metadata=self.provider_metadata,
            provider_metadata=self.provider_metadata,
        )

    @property
    def provider_metadata(self) -> dict[str, str]:
        return {
            "provider": self.descriptor.name,
            "provider_version": "1.0.0",
        }
