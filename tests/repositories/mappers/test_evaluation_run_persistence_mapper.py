from datetime import UTC, datetime

from ai_governance.domain.experiments import (
    EvaluationRun,
    EvaluationRunStatus,
)
from ai_governance.repositories.mappers.evaluation_run_persistence_mapper import (
    EvaluationRunPersistenceMapper,
)


def test_evaluation_run_persistence_mapper_round_trips_run() -> None:
    run = EvaluationRun(
        run_id="run-1",
        experiment_id="experiment-1",
        candidate_id="candidate-1",
        dataset_version="2026-06-26",
        evaluation_provider="TruLens",
        evaluation_result_id="evaluation-1",
        started_at=datetime(2026, 6, 26, tzinfo=UTC),
        completed_at=datetime(2026, 6, 26, 0, 1, tzinfo=UTC),
        status=EvaluationRunStatus.COMPLETED,
        total_item_count=10,
        completed_item_count=10,
        evaluated_item_count=10,
    )

    record = EvaluationRunPersistenceMapper.to_persistence_record(run)
    reloaded = EvaluationRunPersistenceMapper.from_persistence_record(record)

    assert reloaded == run
