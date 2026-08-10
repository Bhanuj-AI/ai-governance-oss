from datetime import UTC, datetime

import pytest

from ai_governance.domain.experiments import ExperimentStatus
from ai_governance.repositories.in_memory_experiment_repository import (
    InMemoryExperimentRepository,
)
from ai_governance.services.experiments import (
    ExperimentConflictError,
    ExperimentLifecycleError,
    ExperimentService,
)


def test_experiment_service_creates_experiment() -> None:
    service = _create_service()

    experiment = service.create_experiment(
        name="support-prompt-benchmark",
        description="Compare support prompt revisions.",
        owner="governance-team",
    )

    assert experiment.experiment_id == "experiment-1"
    assert experiment.name == "support-prompt-benchmark"
    assert experiment.description == "Compare support prompt revisions."
    assert experiment.owner == "governance-team"
    assert experiment.created_at == datetime(2026, 6, 26, tzinfo=UTC)
    assert experiment.status == ExperimentStatus.DRAFT


def test_experiment_service_rejects_duplicate_name() -> None:
    service = _create_service()
    service.create_experiment(
        name="support-prompt-benchmark",
        description="Compare support prompt revisions.",
        owner="governance-team",
    )

    with pytest.raises(ExperimentConflictError):
        service.create_experiment(
            name="support-prompt-benchmark",
            description="Duplicate name.",
            owner="another-team",
        )


def test_experiment_service_updates_draft_metadata() -> None:
    service = _create_service()
    experiment = service.create_experiment(
        name="support-prompt-benchmark",
        description="Compare support prompt revisions.",
        owner="governance-team",
    )

    updated = service.update_experiment_metadata(
        experiment.experiment_id,
        name="support-prompt-benchmark-v2",
        description="Compare prompt and model revisions.",
        owner="ml-governance",
    )

    assert updated.name == "support-prompt-benchmark-v2"
    assert updated.description == "Compare prompt and model revisions."
    assert updated.owner == "ml-governance"
    assert updated.status == ExperimentStatus.DRAFT


def test_experiment_service_updates_last_modified_on_lifecycle_changes() -> None:
    times = iter(
        [
            datetime(2026, 6, 26, tzinfo=UTC),
            datetime(2026, 6, 27, tzinfo=UTC),
            datetime(2026, 6, 28, tzinfo=UTC),
            datetime(2026, 6, 29, tzinfo=UTC),
        ]
    )
    service = ExperimentService(
        experiment_repository=InMemoryExperimentRepository(),
        id_generator=lambda: "experiment-1",
        clock=lambda: next(times),
    )

    experiment = service.create_experiment(
        name="support-prompt-benchmark",
        description="Compare support prompt revisions.",
        owner="governance-team",
    )
    started = service.start_experiment(experiment.experiment_id)
    completed = service.complete_experiment(experiment.experiment_id)

    assert experiment.updated_at == datetime(2026, 6, 26, tzinfo=UTC)
    assert started.updated_at == datetime(2026, 6, 27, tzinfo=UTC)
    assert completed.updated_at == datetime(2026, 6, 28, tzinfo=UTC)


def test_experiment_service_rejects_updates_after_start() -> None:
    service = _create_service()
    experiment = service.create_experiment(
        name="support-prompt-benchmark",
        description="Compare support prompt revisions.",
        owner="governance-team",
    )
    service.start_experiment(experiment.experiment_id)

    with pytest.raises(ExperimentLifecycleError):
        service.update_experiment_metadata(
            experiment.experiment_id,
            description="Should not update.",
        )


def test_experiment_service_starts_draft_experiment() -> None:
    service = _create_service()
    experiment = service.create_experiment(
        name="support-prompt-benchmark",
        description="Compare support prompt revisions.",
        owner="governance-team",
    )

    started = service.start_experiment(experiment.experiment_id)

    assert started.status == ExperimentStatus.RUNNING


def test_experiment_service_completes_running_experiment() -> None:
    service = _create_service()
    experiment = service.create_experiment(
        name="support-prompt-benchmark",
        description="Compare support prompt revisions.",
        owner="governance-team",
    )
    service.start_experiment(experiment.experiment_id)

    completed = service.complete_experiment(experiment.experiment_id)

    assert completed.status == ExperimentStatus.COMPLETED


def test_experiment_service_fails_running_experiment() -> None:
    service = _create_service()
    experiment = service.create_experiment(
        name="support-prompt-benchmark",
        description="Compare support prompt revisions.",
        owner="governance-team",
    )
    service.start_experiment(experiment.experiment_id)

    failed = service.fail_experiment(experiment.experiment_id)

    assert failed.status == ExperimentStatus.FAILED


def test_experiment_service_rejects_start_after_completion() -> None:
    service = _create_service()
    experiment = service.create_experiment(
        name="support-prompt-benchmark",
        description="Compare support prompt revisions.",
        owner="governance-team",
    )
    service.start_experiment(experiment.experiment_id)
    service.complete_experiment(experiment.experiment_id)

    with pytest.raises(ExperimentLifecycleError):
        service.start_experiment(experiment.experiment_id)


def test_experiment_service_archives_experiment() -> None:
    service = _create_service()
    experiment = service.create_experiment(
        name="support-prompt-benchmark",
        description="Compare support prompt revisions.",
        owner="governance-team",
    )

    archived = service.archive_experiment(experiment.experiment_id)

    assert archived.status == ExperimentStatus.ARCHIVED
    assert (
        service.get_experiment(experiment.experiment_id).status
        == ExperimentStatus.ARCHIVED
    )


def test_experiment_service_lists_experiments() -> None:
    service = _create_service()
    first = service.create_experiment(
        name="support-prompt-benchmark",
        description="Compare support prompt revisions.",
        owner="governance-team",
    )
    second = service.create_experiment(
        name="retrieval-benchmark",
        description="Compare retrieval strategies.",
        owner="search-team",
    )

    assert service.list_experiments() == [first, second]


def _create_service() -> ExperimentService:
    ids = iter(["experiment-1", "experiment-2", "experiment-3"])

    return ExperimentService(
        experiment_repository=InMemoryExperimentRepository(),
        id_generator=lambda: next(ids),
        clock=lambda: datetime(2026, 6, 26, tzinfo=UTC),
    )
