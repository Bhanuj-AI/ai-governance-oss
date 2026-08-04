from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from kavach.domain.assets import AssetProvenance


class DatasetStatus(str, Enum):
    """
    Governance lifecycle state for a registered dataset version.
    """

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"
    DEPRECATED = "DEPRECATED"
    ARCHIVED = "ARCHIVED"


@dataclass(frozen=True)
class Dataset:
    """
    Immutable dataset metadata governed by the dataset registry.

    Dataset registry records capture where an evaluation dataset lives and the
    exact metadata required to reproduce historical experiments without taking
    ownership of the underlying storage system.
    """

    dataset_id: str
    name: str
    version: str
    description: str
    storage_uri: str
    storage_type: str
    schema_version: str
    record_count: int
    checksum: str
    creator: str
    created_at: datetime
    status: DatasetStatus
    organization_id: str = "org_default"
    project_id: str = "project_default"
    provenance: AssetProvenance = AssetProvenance.MANAGED
    source_system: str | None = None
    source_reference: str | None = None

    def __post_init__(self) -> None:
        self._require_non_empty("dataset_id", self.dataset_id)
        self._require_non_empty("name", self.name)
        self._require_non_empty("version", self.version)
        self._require_non_empty("description", self.description)
        self._require_non_empty("storage_uri", self.storage_uri)
        self._require_non_empty("storage_type", self.storage_type)
        self._require_non_empty("schema_version", self.schema_version)
        self._require_non_empty("checksum", self.checksum)
        self._require_non_empty("creator", self.creator)

        if self.record_count < 0:
            raise ValueError("Dataset record_count must not be negative.")

    @staticmethod
    def _require_non_empty(
        field_name: str,
        value: str,
    ) -> None:
        if not value.strip():
            raise ValueError(f"Dataset {field_name} must not be empty.")


@dataclass(frozen=True)
class DatasetDiff:
    """
    Governance diff between two dataset versions.

    This captures the metadata changes that matter when teams investigate why
    experiment outcomes changed between dataset versions.
    """

    baseline_dataset_id: str
    candidate_dataset_id: str
    name_changed: bool
    version_changed: bool
    description_changed: bool
    storage_location_changed: bool
    storage_type_changed: bool
    schema_version_changed: bool
    record_count_changed: bool
    checksum_changed: bool

    @property
    def metadata_changed(self) -> bool:
        """
        Return whether descriptive dataset metadata changed.
        """

        return any(
            [
                self.name_changed,
                self.description_changed,
                self.storage_type_changed,
            ]
        )

    @property
    def has_changes(self) -> bool:
        """
        Return whether any governed dataset metadata changed.
        """

        return any(
            [
                self.name_changed,
                self.version_changed,
                self.description_changed,
                self.storage_location_changed,
                self.storage_type_changed,
                self.schema_version_changed,
                self.record_count_changed,
                self.checksum_changed,
            ]
        )
