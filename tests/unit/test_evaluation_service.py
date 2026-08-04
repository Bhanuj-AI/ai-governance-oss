from kavach.domain.evaluation_result import EvaluationMetric, EvaluationResult
from kavach.domain.workflow_execution import WorkflowExecution
from kavach.evaluation import EvaluationService
from kavach.evaluation.evaluation_metrics import (
    ANSWER_RELEVANCE,
    GROUNDEDNESS,
    EvaluationMetricSpec,
)
from kavach.evaluation.evaluation_request import EvaluationRequest
from kavach.providers import EvaluationProviderRegistry
from kavach.providers.evaluation_provider import EvaluationProvider
from kavach.providers.provider_capabilities import ProviderCapabilities
from kavach.providers.provider_descriptor import ProviderDescriptor
from kavach.services.dataset_builder import EvaluationDatasetBuilder
from tests.providers.FakeProvider import FakeEvaluationProvider


def test_evaluation_service():

    execution = WorkflowExecution(
        workflow_id="wf-1",
        execution_id="exec-1",
        workflow_name="claim-validation",
        workflow_version="1.0.0",
        execution_status="COMPLETED",
        input={},
        final_state={},
        events=[],
    )

    service = EvaluationService(
        provider=FakeEvaluationProvider(), dataset_builder=EvaluationDatasetBuilder()
    )

    result = service.evaluate(execution)

    assert result.evaluator_type == "fake"
    assert result.provider_descriptor_snapshot is not None
    assert result.provider_descriptor_snapshot["provider_name"] == "fake"


def test_evaluation_service_resolves_provider_from_registry() -> None:
    execution = WorkflowExecution(
        workflow_id="wf-1",
        execution_id="exec-1",
        workflow_name="claim-validation",
        workflow_version="1.0.0",
        execution_status="COMPLETED",
        input={},
        final_state={},
        events=[],
    )
    registry = EvaluationProviderRegistry()
    registry.register(FakeEvaluationProvider())
    service = EvaluationService(
        provider_registry=registry,
        provider_name="fake",
        dataset_builder=EvaluationDatasetBuilder(),
    )

    result = service.evaluate(execution)

    assert result.evaluator_type == "fake"
    assert result.provider_descriptor_snapshot is not None
    assert result.provider_descriptor_snapshot["descriptor_hash"]


def test_evaluation_service_forwards_metric_specs_to_direct_provider() -> None:
    provider = RecordingEvaluationProvider()
    service = EvaluationService(
        provider=provider,
        dataset_builder=EvaluationDatasetBuilder(),
    )
    metric_specs = [
        EvaluationMetricSpec(ANSWER_RELEVANCE, threshold=0.8),
        EvaluationMetricSpec(GROUNDEDNESS, weight=2.0),
    ]

    service.evaluate(
        _workflow_execution(),
        metric_specs=metric_specs,
    )

    assert provider.last_request is not None
    assert provider.last_request.metric_specs == tuple(metric_specs)


def test_evaluation_service_forwards_metric_specs_to_registry_provider() -> None:
    provider = RecordingEvaluationProvider()
    registry = EvaluationProviderRegistry()
    registry.register(provider)
    service = EvaluationService(
        provider_registry=registry,
        provider_name="recording",
        dataset_builder=EvaluationDatasetBuilder(),
    )
    metric_specs = [
        EvaluationMetricSpec(GROUNDEDNESS, threshold=0.7),
    ]

    service.evaluate(
        _workflow_execution(),
        metric_specs=metric_specs,
    )

    assert provider.last_request is not None
    assert provider.last_request.metric_specs == tuple(metric_specs)


def _workflow_execution() -> WorkflowExecution:
    return WorkflowExecution(
        workflow_id="wf-1",
        execution_id="exec-1",
        workflow_name="claim-validation",
        workflow_version="1.0.0",
        execution_status="COMPLETED",
        input={},
        final_state={},
        events=[],
    )


class RecordingEvaluationProvider(EvaluationProvider):
    def __init__(self) -> None:
        self.last_request: EvaluationRequest | None = None

    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            name="recording",
            display_name="Recording",
            version="1.0",
            adapter_version="1.0.0",
            capabilities=ProviderCapabilities(
                supported_metrics=(
                    ANSWER_RELEVANCE,
                    GROUNDEDNESS,
                ),
                supports_artifacts=False,
            ),
        )

    def evaluate(self, request: EvaluationRequest) -> EvaluationResult:
        self.last_request = request
        return EvaluationResult(
            evaluation_id="recording-eval-1",
            execution_id=request.execution_id,
            evaluator_type=self.descriptor.name,
            evaluator_version=self.descriptor.version,
            metrics=[
                EvaluationMetric(
                    metric_name=ANSWER_RELEVANCE,
                    metric_value=1.0,
                ),
            ],
            metadata={},
        )
