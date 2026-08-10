from datetime import UTC, datetime
from pathlib import Path

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.domain.experiments import ExperimentStatus
from ai_governance.repositories.sqlite.sqlite_experiment_repository import (
    SQLiteExperimentRepository,
)
from ai_governance.services.experiments import ExperimentService


def test_sqlite_experiment_service_persists_experiment_lifecycle(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(tmp_path / "ai_governance.db")
    database.initialize()
    repository = SQLiteExperimentRepository(database)
    service = ExperimentService(
        experiment_repository=repository,
        id_generator=lambda: "experiment-1",
        clock=lambda: datetime(2026, 6, 26, tzinfo=UTC),
    )

    experiment = service.create_experiment(
        name="support-prompt-benchmark",
        description="Compare support prompt revisions.",
        owner="governance-team",
    )
    started = service.start_experiment(experiment.experiment_id)

    reloaded_service = ExperimentService(repository)
    reloaded = reloaded_service.get_experiment(experiment.experiment_id)

    assert started.status == ExperimentStatus.RUNNING
    assert reloaded.status == ExperimentStatus.RUNNING
    assert reloaded.name == "support-prompt-benchmark"
