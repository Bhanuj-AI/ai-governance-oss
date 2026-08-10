from ai_governance.domain.evaluation_result import (
    EvaluationArtifact,
    EvaluationMetric,
    EvaluationResult,
)
from ai_governance.repositories.mappers.evaluation_persistence_mapper import (
    EvaluationPersistenceMapper,
)


class TestEvaluationPersistenceMapper:
    def test_should_convert_evaluation_result_to_persistence_records(self) -> None:
        result = EvaluationResult(
            evaluation_id="evaluation-1",
            execution_id="execution-1",
            evaluator_type="trulens",
            evaluator_version="1.0.0",
            metrics=[
                EvaluationMetric(
                    metric_name="ANSWER_RELEVANCE",
                    metric_value=0.95,
                    explanation="Highly relevant",
                ),
                EvaluationMetric(
                    metric_name="GROUNDEDNESS",
                    metric_value=0.89,
                    explanation="Well grounded",
                ),
            ],
            metadata={
                "model": "gpt-4o",
                "temperature": 0.0,
            },
            artifacts=[
                EvaluationArtifact(
                    artifact_type="provider_trace",
                    uri="s3://trace.json",
                    metadata={"kind": "trace"},
                )
            ],
            provider_metadata={
                "provider_run_id": "run-1",
            },
            provider_descriptor_snapshot={
                "provider_name": "trulens",
                "descriptor_hash": "abc123",
            },
        )

        records = EvaluationPersistenceMapper.to_persistence_records(result)

        assert len(records) == 2

        assert records[0]["evaluation_id"] == "evaluation-1"
        assert records[0]["execution_id"] == "execution-1"
        assert records[0]["evaluator_type"] == "trulens"
        assert records[0]["evaluator_version"] == "1.0.0"
        assert records[0]["metric_name"] == "ANSWER_RELEVANCE"
        assert records[0]["metric_score"] == 0.95
        assert records[0]["explanation"] == "Highly relevant"
        assert records[0]["provider_metadata_json"] == (
            '{"provider_run_id": "run-1"}'
        )
        assert "provider_descriptor_snapshot_json" in records[0]
        assert "artifacts_json" in records[0]
        assert "created_at" in records[0]

        assert records[1]["metric_name"] == "GROUNDEDNESS"
        assert records[1]["metric_score"] == 0.89
        assert records[1]["explanation"] == "Well grounded"

    def test_should_convert_persistence_records_to_evaluation_result(self) -> None:

        original = EvaluationResult(
            evaluation_id="evaluation-1",
            execution_id="execution-1",
            evaluator_type="trulens",
            evaluator_version="1.0.0",
            metrics=[
                EvaluationMetric(
                    metric_name="ANSWER_RELEVANCE",
                    metric_value=0.95,
                    explanation="Highly relevant",
                ),
                EvaluationMetric(
                    metric_name="GROUNDEDNESS",
                    metric_value=0.89,
                    explanation="Well grounded",
                ),
            ],
            metadata={
                "model": "gpt-4o",
                "temperature": 0.0,
            },
        )

        records = EvaluationPersistenceMapper.to_persistence_records(original)

        reconstructed = EvaluationPersistenceMapper.from_persistence_records(records)

        assert len(reconstructed) == 1

        assert reconstructed[0] == original
        assert reconstructed[0].provider_descriptor_snapshot == (
            original.provider_descriptor_snapshot
        )

    def test_should_return_empty_list_when_no_records_exist(self) -> None:

        reconstructed = EvaluationPersistenceMapper.from_persistence_records([])

        assert reconstructed == []

    def test_should_group_multiple_metrics_into_single_evaluation_result(self) -> None:
        records = [
            {
                "evaluation_id": "evaluation-1",
                "execution_id": "execution-1",
                "evaluator_type": "trulens",
                "evaluator_version": "1.0.0",
                "metric_name": "ANSWER_RELEVANCE",
                "metric_score": 0.95,
                "explanation": "Relevant",
                "metadata_json": '{"model":"gpt-4o"}',
            },
            {
                "evaluation_id": "evaluation-1",
                "execution_id": "execution-1",
                "evaluator_type": "trulens",
                "evaluator_version": "1.0.0",
                "metric_name": "GROUNDEDNESS",
                "metric_score": 0.87,
                "explanation": "Grounded",
                "metadata_json": '{"model":"gpt-4o"}',
            },
        ]

        results = EvaluationPersistenceMapper.from_persistence_records(records)

        assert len(results) == 1
        assert len(results[0].metrics) == 2
