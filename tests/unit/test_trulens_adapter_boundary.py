from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ai_governance.providers.trulens import adapter as trulens_adapter_module

from ai_governance.domain.evaluation_dataset import EvaluationDataset
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.evaluation.evaluation_metrics import (
    ANSWER_RELEVANCE,
    CONTEXT_RELEVANCE,
    GROUNDEDNESS,
    EvaluationMetricSpec,
)
from ai_governance.evaluation.evaluation_request import EvaluationRequest
from ai_governance.providers.trulens import (
    TruLensAdapter,
    TruLensConfig,
    TruLensMetricMapper,
    TruLensResultMapper,
    UnsupportedTruLensMetricError,
)
from ai_governance.providers.trulens.errors import TruLensProviderError


def test_trulens_descriptor_links_to_official_setup_documentation() -> None:
    descriptor = TruLensAdapter(
        config=TruLensConfig(model="judge-model")
    ).descriptor

    assert descriptor.configuration_schema["documentation_url"] == (
        "https://trulens.org/getting_started/"
    )


def test_trulens_metric_mapper_normalizes_display_aliases() -> None:
    mapper = TruLensMetricMapper()

    assert mapper.map_specs(
        [
            EvaluationMetricSpec("Answer Relevance"),
            EvaluationMetricSpec("Groundedness"),
        ],
        enabled_metrics=[
            ANSWER_RELEVANCE,
            GROUNDEDNESS,
        ],
    ) == [
        ANSWER_RELEVANCE,
        GROUNDEDNESS,
    ]


def test_trulens_metric_mapper_uses_explicit_metric_specs() -> None:
    mapper = TruLensMetricMapper()

    assert mapper.map_specs(
        [
            EvaluationMetricSpec(GROUNDEDNESS),
        ],
        enabled_metrics=[
            ANSWER_RELEVANCE,
            CONTEXT_RELEVANCE,
            GROUNDEDNESS,
        ],
    ) == [
        GROUNDEDNESS,
    ]


def test_trulens_metric_mapper_falls_back_to_enabled_metrics() -> None:
    mapper = TruLensMetricMapper()

    assert mapper.map_specs(
        [],
        enabled_metrics=[
            ANSWER_RELEVANCE,
        ],
    ) == [
        ANSWER_RELEVANCE,
    ]
    assert mapper.map_specs(
        None,
        enabled_metrics=[
            CONTEXT_RELEVANCE,
        ],
    ) == [
        CONTEXT_RELEVANCE,
    ]


def test_trulens_metric_mapper_rejects_unsupported_metrics() -> None:
    mapper = TruLensMetricMapper()

    with pytest.raises(UnsupportedTruLensMetricError):
        mapper.map_specs(
            [EvaluationMetricSpec("provider_native_metric")],
            enabled_metrics=[ANSWER_RELEVANCE],
        )


def test_trulens_metric_mapper_rejects_requested_disabled_metric() -> None:
    mapper = TruLensMetricMapper()

    with pytest.raises(UnsupportedTruLensMetricError):
        mapper.map_specs(
            [EvaluationMetricSpec(GROUNDEDNESS)],
            enabled_metrics=[ANSWER_RELEVANCE],
        )


def test_trulens_adapter_evaluates_explicit_metric_selection() -> None:
    provider = _RecordingTruLensProvider()
    adapter = TruLensAdapter(
        llm_provider=provider,  # type: ignore[arg-type]
        config=TruLensConfig(
            model="judge-model",
            enabled_metrics=[
                ANSWER_RELEVANCE,
                CONTEXT_RELEVANCE,
                GROUNDEDNESS,
            ],
        ),
    )

    result = adapter.evaluate(
        _evaluation_request(
            metric_specs=[
                EvaluationMetricSpec(GROUNDEDNESS),
            ],
        )
    )

    assert provider.calls == [GROUNDEDNESS]
    assert [
        metric.metric_name
        for metric in result.metrics
    ] == [GROUNDEDNESS]


def test_trulens_adapter_falls_back_to_enabled_metrics_when_specs_empty() -> None:
    provider = _RecordingTruLensProvider()
    adapter = TruLensAdapter(
        llm_provider=provider,  # type: ignore[arg-type]
        config=TruLensConfig(
            model="judge-model",
            enabled_metrics=[
                ANSWER_RELEVANCE,
            ],
        ),
    )

    result = adapter.evaluate(_evaluation_request(metric_specs=[]))

    assert provider.calls == [ANSWER_RELEVANCE]
    assert [
        metric.metric_name
        for metric in result.metrics
    ] == [ANSWER_RELEVANCE]


def test_trulens_adapter_supports_score_and_reason_results() -> None:
    adapter = TruLensAdapter(
        llm_provider=_TupleResultTruLensProvider(),  # type: ignore[arg-type]
        config=TruLensConfig(
            model="judge-model",
            enabled_metrics=[ANSWER_RELEVANCE],
        ),
    )

    result = adapter.evaluate(
        _evaluation_request(metric_specs=[EvaluationMetricSpec(ANSWER_RELEVANCE)])
    )

    assert result.metrics[0].metric_value == 0.91
    assert result.metrics[0].explanation == "structured reason"


def test_trulens_adapter_rejects_pre_fix_openai_score_parser_versions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        trulens_adapter_module,
        "version",
        lambda package_name: (
            "2.9.0" if package_name == "trulens-providers-openai" else "2.10.0"
        ),
    )
    adapter = TruLensAdapter(config=TruLensConfig(model="judge-model"))

    with pytest.raises(
        TruLensProviderError,
        match="unsupported for OpenAI Responses API scoring",
    ):
        adapter.validate_configuration({})


def test_trulens_result_mapper_scrubs_sensitive_metadata() -> None:
    request = _evaluation_request(
        metric_specs=[EvaluationMetricSpec(ANSWER_RELEVANCE)],
    )

    result = TruLensResultMapper().to_evaluation_result(
        request=request,
        raw_result={
            "metrics": [
                {
                    "name": ANSWER_RELEVANCE,
                    "value": 0.91,
                    "explanation": None,
                }
            ],
            "timings": {
                ANSWER_RELEVANCE: 0.2,
            },
        },
        provider_metadata={
            "provider": "trulens",
            "provider_version": "2.8.1",
            "openai_api_key": "secret",
        },
    )

    assert result.execution_id == "execution-1"
    assert result.evaluator_type == "trulens"
    assert result.evaluator_version == "2.8.1"
    assert result.metrics[0].metric_name == ANSWER_RELEVANCE
    assert result.provider_metadata["provider"] == "trulens"
    assert "openai_api_key" not in result.provider_metadata
    assert result.artifacts[0].artifact_type == "trulens_timings"
    assert result.created_at <= datetime.now(UTC)


def _evaluation_request(
    metric_specs: list[EvaluationMetricSpec] | None = None,
) -> EvaluationRequest:
    request_kwargs = {}
    if metric_specs is not None:
        request_kwargs["metric_specs"] = metric_specs

    return EvaluationRequest(
        execution=WorkflowExecution(
            workflow_id="workflow-1",
            execution_id="execution-1",
            workflow_name="claim-validation",
            workflow_version="1.0.0",
            execution_status="COMPLETED",
            input={},
            final_state={},
            events=[],
        ),
        dataset=EvaluationDataset(
            execution_id="execution-1",
            input_text="question",
            context_text="context",
            output_text="answer",
            metadata={},
        ),
        **request_kwargs,
    )


class _RecordingTruLensProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def relevance(
        self,
        prompt: str,
        response: str,
    ) -> float:
        self.calls.append(ANSWER_RELEVANCE)
        return 0.91

    def context_relevance(
        self,
        question: str,
        context: str,
    ) -> float:
        self.calls.append(CONTEXT_RELEVANCE)
        return 0.88

    def groundedness_measure_with_cot_reasons(
        self,
        source: str,
        statement: str,
    ) -> tuple[float, dict[str, str]]:
        self.calls.append(GROUNDEDNESS)
        return 0.86, {"reason": "grounded"}


class _TupleResultTruLensProvider:
    def relevance(self, prompt: str, response: str) -> tuple[float, str]:
        return 0.91, "structured reason"
