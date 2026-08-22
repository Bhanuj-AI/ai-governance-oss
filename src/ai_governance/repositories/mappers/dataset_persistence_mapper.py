from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from ai_governance.domain.assets import AssetProvenance
from ai_governance.domain.datasets import (
    Dataset,
    DatasetStatus,
)


class DatasetPersistenceMapper:
    """
    Maps Dataset domain objects to and from persistence records.
    """

    @staticmethod
    def to_persistence_record(
        dataset: Dataset,
    ) -> dict[str, Any]:
        return {
            "dataset_id": dataset.dataset_id,
            "name": dataset.name,
            "version": dataset.version,
            "description": dataset.description,
            "storage_uri": dataset.storage_uri,
            "storage_type": dataset.storage_type,
            "schema_version": dataset.schema_version,
            "record_count": dataset.record_count,
            "checksum": dataset.checksum,
            "creator": dataset.creator,
            "created_at": dataset.created_at.isoformat(),
            "status": dataset.status.value,
            "organization_id": dataset.organization_id,
            "project_id": dataset.project_id,
            "provenance": dataset.provenance.value,
            "source_system": dataset.source_system,
            "source_reference": dataset.source_reference,
        }

    @staticmethod
    def from_persistence_record(
        record: Mapping[str, Any],
    ) -> Dataset:
        return Dataset(
            dataset_id=record["dataset_id"],
            name=record["name"],
            version=record["version"],
            description=record["description"],
            storage_uri=record["storage_uri"],
            storage_type=record["storage_type"],
            schema_version=record["schema_version"],
            record_count=record["record_count"],
            checksum=record["checksum"],
            creator=record["creator"],
            created_at=datetime.fromisoformat(record["created_at"]),
            status=DatasetStatus(record["status"]),
            organization_id=_value(record, "organization_id", "org_default"),
            project_id=_value(record, "project_id", "project_default"),
            provenance=AssetProvenance(_value(record, "provenance", "MANAGED")),
            source_system=_optional_value(record, "source_system"),
            source_reference=_optional_value(record, "source_reference"),
        )

    @classmethod
    def from_persistence_records(
        cls,
        records: list[Mapping[str, Any]],
    ) -> list[Dataset]:
        return [cls.from_persistence_record(record) for record in records]


def _value(record: Mapping[str, Any], key: str, default: Any) -> Any:
    try:
        return record[key]
    except (KeyError, IndexError):
        return default


def _optional_value(record: Mapping[str, Any], key: str) -> str | None:
    value = _value(record, key, None)
    return str(value) if value is not None else None
