from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from kavach.domain.datasets import Dataset


class DatasetResponse(BaseModel):
    """
    REST metadata for a registered dataset version.
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
    status: str
    provenance: str
    source_system: str | None
    source_reference: str | None

    @classmethod
    def from_domain(
        cls,
        dataset: Dataset,
    ) -> DatasetResponse:
        return cls(
            dataset_id=dataset.dataset_id,
            name=dataset.name,
            version=dataset.version,
            description=dataset.description,
            storage_uri=dataset.storage_uri,
            storage_type=dataset.storage_type,
            schema_version=dataset.schema_version,
            record_count=dataset.record_count,
            checksum=dataset.checksum,
            creator=dataset.creator,
            created_at=dataset.created_at,
            status=dataset.status.value,
            provenance=dataset.provenance.value,
            source_system=dataset.source_system,
            source_reference=dataset.source_reference,
        )
