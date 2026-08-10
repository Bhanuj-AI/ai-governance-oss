from datetime import UTC, datetime

from ai_governance.domain.experiments import ExperimentCandidate
from ai_governance.repositories.mappers.experiment_candidate_persistence_mapper import (
    ExperimentCandidatePersistenceMapper,
)


def test_experiment_candidate_persistence_mapper_round_trips_candidate() -> None:
    candidate = ExperimentCandidate(
        candidate_id="candidate-1",
        experiment_id="experiment-1",
        name="Baseline",
        prompt_id="prompt-1",
        prompt_version="v1",
        model_id="model-1",
        model_version="2026-06-25",
        dataset_id="dataset-1",
        dataset_version="2026-06-26",
        evaluation_provider="TruLens",
        temperature=0.0,
        top_p=1.0,
        max_tokens=4096,
        metadata={"tier": "baseline"},
        created_at=datetime(2026, 6, 26, tzinfo=UTC),
    )

    record = ExperimentCandidatePersistenceMapper.to_persistence_record(
        candidate
    )
    reloaded = ExperimentCandidatePersistenceMapper.from_persistence_record(
        record
    )

    assert reloaded == candidate
