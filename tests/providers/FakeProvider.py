from ai_governance.domain.evaluation_dataset import EvaluationDataset
from ai_governance.domain.evaluation_result import (
    EvaluationMetric,
    EvaluationResult,
)
from ai_governance.evaluation.evaluation_metrics import ANSWER_RELEVANCE
from ai_governance.providers.evaluation_provider import EvaluationProvider
from ai_governance.providers.provider_capabilities import ProviderCapabilities
from ai_governance.providers.provider_descriptor import ProviderDescriptor


class FakeEvaluationProvider(EvaluationProvider):
    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            name="fake",
            display_name="Fake",
            version="1.0",
            adapter_version="1.0.0",
            capabilities=ProviderCapabilities(
                supported_metrics=(ANSWER_RELEVANCE,),
                supports_artifacts=False,
            ),
        )

    def evaluate(self, dataset: EvaluationDataset) -> EvaluationResult:

        return EvaluationResult(
            evaluation_id="1",
            execution_id=dataset.execution_id,
            evaluator_type=self.descriptor.name,
            evaluator_version=self.descriptor.version,
            metrics=[
                EvaluationMetric(
                    metric_name=ANSWER_RELEVANCE,
                    metric_value=1.0,
                    explanation="faked",
                ),
            ],
            metadata={},
        )

    @property
    def provider_metadata(self) -> dict[str, str]:
        return {
            "provider": self.descriptor.name,
            "provider_version": self.descriptor.version,
            "judge_model": "FAKE_JUDGE",
        }
