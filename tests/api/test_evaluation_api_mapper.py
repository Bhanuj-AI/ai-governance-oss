from __future__ import annotations

from datetime import UTC, datetime

from kavach.api.mappers import EvaluationApiMapper
from kavach.api.models import (
    EvaluationMetricSpecRequest,
    EvaluationSubmitRequest,
)
from kavach.domain.evaluation_result import (
    EvaluationArtifact,
    EvaluationMetric,
    EvaluationResult,
)


def test_submit_request_maps_to_workflow_execution_defaults() -> None:
    request = EvaluationSubmitRequest(
        provider_name="fake",
        workflow_id="wf-1",
        execution_id="exec-1",
        execution_status="COMPLETED",
        input={"question": "What happened?"},
        final_state={"answer": "It worked."},
    )

    execution = EvaluationApiMapper.to_workflow_execution(request)

    assert execution.workflow_id == "wf-1"
    assert execution.execution_id == "exec-1"
    assert execution.workflow_name == "wf-1"
    assert execution.workflow_version == "unknown"
    assert execution.events == []


def test_metric_spec_request_maps_to_domain_spec() -> None:
    specs = EvaluationApiMapper.to_metric_specs(
        [
            EvaluationMetricSpecRequest(
                name="Answer Relevance",
                description="Judge answer fit.",
                threshold=0.8,
                weight=2.0,
                metadata={"rubric": "strict"},
            )
        ]
    )

    assert specs[0].name == "answer_relevance"
    assert specs[0].description == "Judge answer fit."
    assert specs[0].threshold == 0.8
    assert specs[0].weight == 2.0
    assert dict(specs[0].metadata) == {"rubric": "strict"}


def test_result_response_scrubs_sensitive_metadata() -> None:
    result = EvaluationResult(
        evaluation_id="eval-1",
        execution_id="exec-1",
        evaluator_type="fake",
        evaluator_version="1.0.0",
        metrics=[
            EvaluationMetric(
                metric_name="answer_relevance",
                metric_value=0.95,
                explanation="Relevant.",
            )
        ],
        artifacts=[
            EvaluationArtifact(
                artifact_type="trace",
                payload={"span": "root"},
                metadata={"trace_id": "trace-1"},
            )
        ],
        provider_metadata={
            "visible": "ok",
            "api_key": "secret",
            "nested": {"token": "secret", "safe": "value"},
        },
        provider_descriptor_snapshot={
            "name": "fake",
            "metadata": {
                "authorization": "secret",
                "region": "local",
            },
        },
        created_at=datetime(2026, 6, 27, tzinfo=UTC),
    )

    response = EvaluationApiMapper.to_response(result)

    assert response.provider_metadata == {
        "visible": "ok",
        "nested": {"safe": "value"},
    }
    assert response.provider_descriptor_snapshot == {
        "name": "fake",
        "metadata": {"region": "local"},
    }
    assert response.metrics[0].name == "answer_relevance"
    assert response.artifacts[0].payload == {"span": "root"}


def test_history_response_preserves_execution_id() -> None:
    result = EvaluationResult(
        evaluation_id="eval-1",
        execution_id="exec-1",
        evaluator_type="fake",
        evaluator_version="1.0.0",
        metrics=[],
    )

    response = EvaluationApiMapper.to_history_response("exec-1", [result])

    assert response.execution_id == "exec-1"
    assert response.evaluations[0].evaluation_id == "eval-1"
