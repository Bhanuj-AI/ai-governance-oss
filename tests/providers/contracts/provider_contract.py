from __future__ import annotations

from abc import ABC, abstractmethod

import pytest

from ai_governance.domain.evaluation_dataset import EvaluationDataset
from ai_governance.domain.evaluation_result import EvaluationResult
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.evaluation import EvaluationService
from ai_governance.evaluation.evaluation_metrics import EvaluationMetricSpec
from ai_governance.evaluation.evaluation_request import EvaluationRequest
from ai_governance.providers.evaluation_provider import EvaluationProvider
from ai_governance.providers.provider_descriptor import ProviderDescriptor
from ai_governance.services.dataset_builder import EvaluationDatasetBuilder

_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "token",
)


class ProviderContract(ABC):
    @abstractmethod
    def provider(self) -> EvaluationProvider:
        """
        Return a provider instance under test.
        """

    def evaluation_request(self) -> EvaluationRequest:
        execution = self.workflow_execution()
        return EvaluationRequest(
            execution=execution,
            dataset=EvaluationDataset(
                execution_id=execution.execution_id,
                input_text="What is the capital of France?",
                context_text="Paris is the capital of France.",
                output_text="The capital of France is Paris.",
                metadata={},
            ),
            metric_specs=[
                EvaluationMetricSpec("Answer Relevance"),
            ],
        )

    def workflow_execution(self) -> WorkflowExecution:
        return WorkflowExecution(
            workflow_id="workflow-1",
            execution_id="execution-1",
            workflow_name="support",
            workflow_version="1.0.0",
            execution_status="COMPLETED",
            input={},
            final_state={},
            events=[],
        )

    def test_provider_exposes_descriptor(self) -> None:
        descriptor = self.provider().descriptor

        assert isinstance(descriptor, ProviderDescriptor)
        assert descriptor.name
        assert descriptor.display_name
        assert descriptor.version
        assert descriptor.adapter_version
        assert descriptor.capabilities.supported_metrics

    def test_descriptor_metrics_are_normalized(self) -> None:
        descriptor = self.provider().descriptor

        for metric_name in descriptor.capabilities.supported_metrics:
            assert metric_name == metric_name.lower()
            assert " " not in metric_name

    def test_descriptor_serialization_has_no_secret_keys(self) -> None:
        descriptor = self.provider().descriptor

        assert not _contains_sensitive_key(descriptor.to_dict())

    def test_evaluate_returns_evaluation_result(self) -> None:
        result = self.provider().evaluate(self.evaluation_request())

        assert isinstance(result, EvaluationResult)
        assert result.evaluator_type == self.provider().descriptor.name
        assert result.evaluator_version == self.provider().descriptor.version
        assert result.metrics
        assert result.provider_metadata is not None
        assert not _contains_sensitive_key(dict(result.provider_metadata))
        assert result.artifacts is not None

    def test_evaluation_service_attaches_provider_descriptor_snapshot(
        self,
    ) -> None:
        service = EvaluationService(
            provider=self.provider(),
            dataset_builder=EvaluationDatasetBuilder(),
        )

        result = service.evaluate(self.workflow_execution())

        assert result.provider_descriptor_snapshot is not None
        assert (
            result.provider_descriptor_snapshot["provider_name"]
            == self.provider().descriptor.name
        )
        assert result.provider_descriptor_snapshot["descriptor_hash"]

    def test_unsupported_metrics_fail_clearly(self) -> None:
        request = self.evaluation_request()
        unsupported = EvaluationRequest(
            execution=request.execution,
            dataset=request.dataset,
            metric_specs=[EvaluationMetricSpec("unsupported metric")],
            provider_config=request.provider_config,
        )

        with pytest.raises(Exception):  # noqa: B017 - provider implementations expose distinct error types.
            self.provider().evaluate(unsupported)


def _contains_sensitive_key(
    value: object,
) -> bool:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            if any(part in str(key).lower() for part in _SENSITIVE_KEY_PARTS):
                return True
            if _contains_sensitive_key(nested_value):
                return True
    elif isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)

    return False
