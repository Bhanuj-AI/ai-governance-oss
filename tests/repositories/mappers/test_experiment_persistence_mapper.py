from datetime import UTC, datetime

from kavach.domain.experiments import (
    Experiment,
    ExperimentStatus,
)
from kavach.repositories.mappers.experiment_persistence_mapper import (
    ExperimentPersistenceMapper,
)


def test_experiment_persistence_mapper_round_trips_experiment() -> None:
    experiment = Experiment(
        experiment_id="experiment-1",
        name="support-prompt-benchmark",
        description="Compare support prompt revisions.",
        owner="governance-team",
        created_at=datetime(2026, 6, 26, tzinfo=UTC),
        status=ExperimentStatus.RUNNING,
    )

    record = ExperimentPersistenceMapper.to_persistence_record(experiment)
    reloaded = ExperimentPersistenceMapper.from_persistence_record(record)

    assert reloaded == experiment
