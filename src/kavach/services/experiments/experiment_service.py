from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from kavach.domain.experiments import (
    Experiment,
    ExperimentStatus,
)
from kavach.ontology.synchronization import (
    OntologySyncEventPublisherProtocol,
)
from kavach.repositories.experiment_repository import ExperimentRepository


class ExperimentNotFoundError(Exception):
    """
    Raised when an experiment operation references an unknown experiment.
    """


class ExperimentConflictError(Exception):
    """
    Raised when an experiment name already exists.
    """


class ExperimentLifecycleError(Exception):
    """
    Raised when an experiment lifecycle transition is not allowed.
    """


class ExperimentService:
    """
    Application service for experiment lifecycle orchestration.

    The service owns experiment governance rules while repositories remain
    persistence-only.
    """

    def __init__(
        self,
        experiment_repository: ExperimentRepository,
        id_generator: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
        ontology_event_publisher: OntologySyncEventPublisherProtocol
        | None = None,
    ) -> None:
        self._experiment_repository = experiment_repository
        self._id_generator = id_generator or (lambda: str(uuid4()))
        self._clock = clock or (lambda: datetime.now(UTC))
        self._ontology_event_publisher = ontology_event_publisher

    def create_experiment(
        self,
        name: str,
        description: str,
        owner: str,
    ) -> Experiment:
        """
        Create a new experiment in DRAFT status.
        """

        self._ensure_name_available(name)
        experiment = Experiment(
            experiment_id=self._id_generator(),
            name=name,
            description=description,
            owner=owner,
            created_at=self._clock(),
            status=ExperimentStatus.DRAFT,
        )
        self._experiment_repository.save(experiment)
        self._publish_experiment_event("ExperimentCreated", experiment)

        return experiment

    def update_experiment_metadata(
        self,
        experiment_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        owner: str | None = None,
    ) -> Experiment:
        """
        Update metadata for a draft experiment.
        """

        experiment = self._get_experiment(experiment_id)

        if experiment.status != ExperimentStatus.DRAFT:
            raise ExperimentLifecycleError(
                "Only draft experiments may be modified."
            )

        updated_name = name if name is not None else experiment.name
        if updated_name != experiment.name:
            self._ensure_name_available(updated_name)

        updated = replace(
            experiment,
            name=updated_name,
            description=(
                description
                if description is not None
                else experiment.description
            ),
            owner=owner if owner is not None else experiment.owner,
            updated_at=self._clock(),
        )
        self._experiment_repository.save(updated)
        self._publish_experiment_event("ExperimentUpdated", updated)

        return updated

    def start_experiment(
        self,
        experiment_id: str,
    ) -> Experiment:
        """
        Mark a draft experiment as running.
        """

        experiment = self._get_experiment(experiment_id)

        if experiment.status != ExperimentStatus.DRAFT:
            raise ExperimentLifecycleError(
                "Only draft experiments may be started."
            )

        started = replace(
            experiment,
            status=ExperimentStatus.RUNNING,
            updated_at=self._clock(),
        )
        self._experiment_repository.save(started)
        self._publish_experiment_event("ExperimentStarted", started)

        return started

    def complete_experiment(
        self,
        experiment_id: str,
    ) -> Experiment:
        """
        Mark a running experiment as completed.
        """

        experiment = self._get_experiment(experiment_id)

        if experiment.status != ExperimentStatus.RUNNING:
            raise ExperimentLifecycleError(
                "Only running experiments may be completed."
            )

        completed = replace(
            experiment,
            status=ExperimentStatus.COMPLETED,
            updated_at=self._clock(),
        )
        self._experiment_repository.save(completed)
        self._publish_experiment_event("ExperimentCompleted", completed)

        return completed

    def fail_experiment(
        self,
        experiment_id: str,
    ) -> Experiment:
        """
        Mark a running experiment as failed.
        """

        experiment = self._get_experiment(experiment_id)

        if experiment.status != ExperimentStatus.RUNNING:
            raise ExperimentLifecycleError(
                "Only running experiments may be failed."
            )

        failed = replace(
            experiment,
            status=ExperimentStatus.FAILED,
            updated_at=self._clock(),
        )
        self._experiment_repository.save(failed)
        self._publish_experiment_event("ExperimentFailed", failed)

        return failed

    def archive_experiment(
        self,
        experiment_id: str,
    ) -> Experiment:
        """
        Archive an experiment while preserving it for governance history.
        """

        experiment = self._get_experiment(experiment_id)

        if experiment.status == ExperimentStatus.ARCHIVED:
            return experiment

        archived = replace(
            experiment,
            status=ExperimentStatus.ARCHIVED,
            updated_at=self._clock(),
        )
        self._experiment_repository.save(archived)
        self._publish_experiment_event("ExperimentArchived", archived)

        return archived

    def get_experiment(
        self,
        experiment_id: str,
    ) -> Experiment:
        """
        Retrieve one experiment by ID.
        """

        return self._get_experiment(experiment_id)

    def list_experiments(self) -> list[Experiment]:
        """
        Return every experiment.
        """

        return self._experiment_repository.find_all()

    def _get_experiment(
        self,
        experiment_id: str,
    ) -> Experiment:
        experiment = self._experiment_repository.find_by_id(experiment_id)

        if experiment is None:
            raise ExperimentNotFoundError(
                f"Experiment '{experiment_id}' does not exist."
            )

        return experiment

    def _ensure_name_available(
        self,
        name: str,
    ) -> None:
        existing = self._experiment_repository.find_by_name(name)

        if existing is not None:
            raise ExperimentConflictError(
                f"Experiment '{name}' already exists."
            )

    def _publish_experiment_event(
        self,
        event_type: str,
        experiment: Experiment,
    ) -> None:
        if self._ontology_event_publisher is None:
            return
        self._ontology_event_publisher.publish_entity_event(
            event_type,
            entity_type="Experiment",
            entity_id=experiment.experiment_id,
            scope_identifier="experiment_service",
            payload={
                "experiment_id": experiment.experiment_id,
                "name": experiment.name,
                "status": experiment.status.value,
            },
        )
