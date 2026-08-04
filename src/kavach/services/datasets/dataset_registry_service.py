from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from kavach.domain.datasets import (
    Dataset,
    DatasetDiff,
    DatasetStatus,
)
from kavach.ontology.synchronization import (
    OntologySyncEventPublisherProtocol,
)
from kavach.repositories.dataset_repository import DatasetRepository
from kavach.tenancy.domain import TenantContext


class DatasetNotFoundError(Exception):
    """
    Raised when a dataset registry operation references an unknown dataset.
    """


class DatasetVersionConflictError(Exception):
    """Raised when a dataset name and version already exist."""


class DatasetDuplicateContentError(Exception):
    """Raised when a logical dataset already has the uploaded checksum."""


class DatasetLifecycleError(Exception):
    """
    Raised when a dataset lifecycle transition is not allowed.
    """


class DatasetRegistryService:
    """
    Application service for governed dataset lifecycle management.

    The service owns dataset governance rules while repositories remain
    persistence-only.
    """

    def __init__(
        self,
        dataset_repository: DatasetRepository,
        id_generator: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
        ontology_event_publisher: OntologySyncEventPublisherProtocol | None = None,
    ) -> None:
        self._dataset_repository = dataset_repository
        self._id_generator = id_generator or (lambda: str(uuid4()))
        self._clock = clock or (lambda: datetime.now(UTC))
        self._ontology_event_publisher = ontology_event_publisher

    def register_dataset(
        self,
        name: str,
        version: str,
        description: str,
        storage_uri: str,
        storage_type: str,
        schema_version: str,
        record_count: int,
        checksum: str,
        creator: str,
        organization_id: str = "org_default",
        project_id: str = "project_default",
        dataset_id: str | None = None,
    ) -> Dataset:
        """
        Register a new dataset version in DRAFT status.
        """

        self._ensure_version_available(
            name=name,
            version=version,
        )

        dataset = Dataset(
            dataset_id=dataset_id or self._id_generator(),
            name=name,
            version=version,
            description=description,
            storage_uri=storage_uri,
            storage_type=storage_type,
            schema_version=schema_version,
            record_count=record_count,
            checksum=checksum,
            creator=creator,
            created_at=self._clock(),
            status=DatasetStatus.DRAFT,
            organization_id=organization_id,
            project_id=project_id,
        )

        self._dataset_repository.save(dataset)
        self._publish_dataset_event("DatasetVersionRegistered", dataset)

        return dataset

    def create_dataset_version(
        self,
        dataset_id: str,
        version: str,
        creator: str,
        description: str | None = None,
        storage_uri: str | None = None,
        storage_type: str | None = None,
        schema_version: str | None = None,
        record_count: int | None = None,
        checksum: str | None = None,
    ) -> Dataset:
        """
        Create a new DRAFT version from an existing dataset.
        """

        source = self._get_dataset(dataset_id)
        self._ensure_version_available(
            name=source.name,
            version=version,
        )

        dataset = Dataset(
            dataset_id=self._id_generator(),
            name=source.name,
            version=version,
            description=description if description is not None else source.description,
            storage_uri=storage_uri if storage_uri is not None else source.storage_uri,
            storage_type=storage_type
            if storage_type is not None
            else source.storage_type,
            schema_version=(
                schema_version if schema_version is not None else source.schema_version
            ),
            record_count=record_count
            if record_count is not None
            else source.record_count,
            checksum=checksum if checksum is not None else source.checksum,
            creator=creator,
            created_at=self._clock(),
            status=DatasetStatus.DRAFT,
        )

        self._dataset_repository.save(dataset)
        self._publish_dataset_event("DatasetVersionRegistered", dataset)

        return dataset

    def freeze_dataset(
        self,
        dataset_id: str,
    ) -> Dataset:
        """
        Mark a dataset version as frozen for benchmark evaluations.
        """

        dataset = self._get_dataset(dataset_id)

        if dataset.status == DatasetStatus.ARCHIVED:
            raise DatasetLifecycleError("Archived datasets cannot be frozen.")

        frozen = replace(dataset, status=DatasetStatus.FROZEN)
        self._dataset_repository.save(frozen)
        self._publish_dataset_event("DatasetFrozen", frozen)

        return frozen

    def promote_dataset(
        self,
        dataset_id: str,
    ) -> Dataset:
        """
        Activate one dataset version and deprecate the previous active version.
        """

        dataset = self._get_dataset(dataset_id)

        if dataset.status == DatasetStatus.ARCHIVED:
            raise DatasetLifecycleError("Archived datasets cannot be promoted.")

        for existing in self.list_versions(name=dataset.name):
            if (
                existing.dataset_id != dataset.dataset_id
                and existing.status == DatasetStatus.ACTIVE
            ):
                deprecated = replace(
                    existing,
                    status=DatasetStatus.DEPRECATED,
                )
                self._dataset_repository.save(deprecated)
                self._publish_dataset_event(
                    "DatasetVersionDeprecated",
                    deprecated,
                )

        promoted = replace(dataset, status=DatasetStatus.ACTIVE)
        self._dataset_repository.save(promoted)
        self._publish_dataset_event("DatasetVersionActivated", promoted)

        return promoted

    def deprecate_dataset(
        self,
        dataset_id: str,
    ) -> Dataset:
        """
        Mark a dataset version as deprecated while preserving history.
        """

        dataset = self._get_dataset(dataset_id)

        if dataset.status == DatasetStatus.ARCHIVED:
            raise DatasetLifecycleError("Archived datasets cannot be deprecated.")

        deprecated = replace(dataset, status=DatasetStatus.DEPRECATED)
        self._dataset_repository.save(deprecated)
        self._publish_dataset_event("DatasetVersionDeprecated", deprecated)

        return deprecated

    def archive_dataset(
        self,
        dataset_id: str,
    ) -> Dataset:
        """
        Archive a dataset version so it is no longer available for active use.
        """

        dataset = self._get_dataset(dataset_id)

        if dataset.status == DatasetStatus.ARCHIVED:
            return dataset

        archived = replace(dataset, status=DatasetStatus.ARCHIVED)
        self._dataset_repository.save(archived)
        self._publish_dataset_event("DatasetVersionArchived", archived)

        return archived

    def get_dataset(
        self,
        dataset_id: str,
        context: TenantContext | None = None,
    ) -> Dataset:
        """
        Retrieve a dataset by registry ID.
        """

        dataset = self._get_dataset(dataset_id)
        if context is not None and (
            dataset.organization_id != context.organization_id
            or dataset.project_id != context.project_id
        ):
            raise DatasetNotFoundError(f"Dataset '{dataset_id}' does not exist.")
        return dataset

    def get_dataset_version(
        self,
        name: str,
        version: str,
    ) -> Dataset:
        """
        Retrieve a specific logical dataset version.
        """

        dataset = self._dataset_repository.find_by_name_and_version(
            name=name,
            version=version,
        )

        if dataset is None:
            raise DatasetNotFoundError(
                f"Dataset '{name}' version '{version}' does not exist."
            )

        return dataset

    def list_datasets(self, context: TenantContext | None = None) -> list[Dataset]:
        """
        Return every dataset version in the registry.
        """

        return [
            dataset
            for dataset in self._dataset_repository.find_all()
            if context is None
            or (
                dataset.organization_id == context.organization_id
                and dataset.project_id == context.project_id
            )
        ]

    def list_versions(
        self,
        name: str,
    ) -> list[Dataset]:
        """
        Return every version for one logical dataset.
        """

        return self._dataset_repository.find_by_name(name)

    def compare_dataset_versions(
        self,
        baseline_dataset_id: str,
        candidate_dataset_id: str,
    ) -> DatasetDiff:
        """
        Compare two dataset versions by governed metadata.
        """

        baseline = self._get_dataset(baseline_dataset_id)
        candidate = self._get_dataset(candidate_dataset_id)

        return DatasetDiff(
            baseline_dataset_id=baseline.dataset_id,
            candidate_dataset_id=candidate.dataset_id,
            name_changed=baseline.name != candidate.name,
            version_changed=baseline.version != candidate.version,
            description_changed=baseline.description != candidate.description,
            storage_location_changed=baseline.storage_uri != candidate.storage_uri,
            storage_type_changed=baseline.storage_type != candidate.storage_type,
            schema_version_changed=(
                baseline.schema_version != candidate.schema_version
            ),
            record_count_changed=baseline.record_count != candidate.record_count,
            checksum_changed=baseline.checksum != candidate.checksum,
        )

    def _get_dataset(
        self,
        dataset_id: str,
    ) -> Dataset:
        dataset = self._dataset_repository.find_by_id(dataset_id)

        if dataset is None:
            raise DatasetNotFoundError(f"Dataset '{dataset_id}' does not exist.")

        return dataset

    def _ensure_version_available(
        self,
        name: str,
        version: str,
    ) -> None:
        existing = self._dataset_repository.find_by_name_and_version(
            name=name,
            version=version,
        )

        if existing is not None:
            raise DatasetVersionConflictError(
                f"Dataset '{name}' version '{version}' already exists."
            )

    def _publish_dataset_event(
        self,
        event_type: str,
        dataset: Dataset,
    ) -> None:
        if self._ontology_event_publisher is None:
            return
        self._ontology_event_publisher.publish_entity_event(
            event_type,
            entity_type="DatasetVersion",
            entity_id=dataset.dataset_id,
            scope_identifier="dataset_registry",
            payload={
                "dataset_id": dataset.dataset_id,
                "name": dataset.name,
                "version": dataset.version,
                "status": dataset.status.value,
            },
        )
