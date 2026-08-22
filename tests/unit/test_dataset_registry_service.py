from datetime import UTC, datetime

import pytest

from ai_governance.domain.datasets import DatasetStatus
from ai_governance.repositories.in_memory_dataset_repository import (
    InMemoryDatasetRepository,
)
from ai_governance.services.datasets import (
    DatasetLifecycleError,
    DatasetNotFoundError,
    DatasetRegistryService,
    DatasetVersionConflictError,
)
from ai_governance.tenancy.domain import TenantContext

_TENANT = TenantContext("org_default", "project_default", "dataset-owner", "request-1")


def test_dataset_registry_registers_dataset() -> None:
    service = _create_service()

    dataset = service.register_dataset(
        name="support-faq",
        version="2026-06-26",
        description="Baseline evaluation dataset",
        storage_uri="s3://datasets/support-faq/2026-06-26.parquet",
        storage_type="S3",
        schema_version="v1",
        record_count=1500,
        checksum="sha256:abc123",
        creator="dataset-owner",
    )

    assert dataset.dataset_id == "dataset-1"
    assert dataset.name == "support-faq"
    assert dataset.version == "2026-06-26"
    assert dataset.description == "Baseline evaluation dataset"
    assert dataset.storage_uri == "s3://datasets/support-faq/2026-06-26.parquet"
    assert dataset.storage_type == "S3"
    assert dataset.schema_version == "v1"
    assert dataset.record_count == 1500
    assert dataset.checksum == "sha256:abc123"
    assert dataset.creator == "dataset-owner"
    assert dataset.created_at == datetime(2026, 6, 26, tzinfo=UTC)
    assert dataset.status == DatasetStatus.DRAFT


def test_dataset_registry_preserves_registered_tenant_scope() -> None:
    dataset = _create_service().register_dataset(
        name="tenant-evaluation-set",
        version="v1.0",
        description="Tenant-scoped evaluation dataset",
        storage_uri="s3://datasets/tenant-evaluation-set/v1.0.jsonl",
        storage_type="S3",
        schema_version="1.0",
        record_count=1,
        checksum="sha256:abc123",
        creator="dataset-owner",
        organization_id="org-acme",
        project_id="project-risk",
    )

    assert dataset.organization_id == "org-acme"
    assert dataset.project_id == "project-risk"


def test_dataset_registry_rejects_duplicate_dataset_version() -> None:
    service = _create_service()
    service.register_dataset(
        name="support-faq",
        version="2026-06-26",
        description="Baseline evaluation dataset",
        storage_uri="s3://datasets/support-faq/2026-06-26.parquet",
        storage_type="S3",
        schema_version="v1",
        record_count=1500,
        checksum="sha256:abc123",
        creator="dataset-owner",
    )

    with pytest.raises(DatasetVersionConflictError):
        service.register_dataset(
            name="support-faq",
            version="2026-06-26",
            description="Baseline evaluation dataset",
            storage_uri="s3://datasets/support-faq/2026-06-26.parquet",
            storage_type="S3",
            schema_version="v1",
            record_count=1500,
            checksum="sha256:abc123",
            creator="dataset-owner",
        )


def test_dataset_registry_creates_new_version() -> None:
    service = _create_service()
    original = service.register_dataset(
        name="support-faq",
        version="2026-06-26",
        description="Baseline evaluation dataset",
        storage_uri="s3://datasets/support-faq/2026-06-26.parquet",
        storage_type="S3",
        schema_version="v1",
        record_count=1500,
        checksum="sha256:abc123",
        creator="dataset-owner",
    )

    versioned = service.create_dataset_version(
        dataset_id=original.dataset_id,
        version="2026-07-01",
        description="Expanded evaluation dataset",
        storage_uri="s3://datasets/support-faq/2026-07-01.parquet",
        schema_version="v2",
        record_count=2200,
        checksum="sha256:def456",
        creator="data-steward",
    )

    assert versioned.dataset_id == "dataset-2"
    assert versioned.name == original.name
    assert versioned.version == "2026-07-01"
    assert versioned.description == "Expanded evaluation dataset"
    assert versioned.storage_uri == "s3://datasets/support-faq/2026-07-01.parquet"
    assert versioned.storage_type == "S3"
    assert versioned.schema_version == "v2"
    assert versioned.record_count == 2200
    assert versioned.checksum == "sha256:def456"
    assert versioned.status == DatasetStatus.DRAFT


def test_dataset_registry_promotes_dataset_and_deprecates_previous_active() -> None:
    service = _create_service()
    original = service.register_dataset(
        name="support-faq",
        version="2026-06-26",
        description="Baseline evaluation dataset",
        storage_uri="s3://datasets/support-faq/2026-06-26.parquet",
        storage_type="S3",
        schema_version="v1",
        record_count=1500,
        checksum="sha256:abc123",
        creator="dataset-owner",
    )
    candidate = service.create_dataset_version(
        dataset_id=original.dataset_id,
        version="2026-07-01",
        checksum="sha256:def456",
        creator="data-steward",
    )

    activated_original = service.promote_dataset(original.dataset_id)
    activated_candidate = service.promote_dataset(candidate.dataset_id)

    assert activated_original.status == DatasetStatus.ACTIVE
    assert activated_candidate.status == DatasetStatus.ACTIVE
    assert service.get_dataset(original.dataset_id).status == DatasetStatus.DEPRECATED
    assert service.get_dataset(candidate.dataset_id).status == DatasetStatus.ACTIVE


def test_dataset_registry_freezes_dataset() -> None:
    service = _create_service()
    dataset = service.register_dataset(
        name="support-faq",
        version="2026-06-26",
        description="Baseline evaluation dataset",
        storage_uri="s3://datasets/support-faq/2026-06-26.parquet",
        storage_type="S3",
        schema_version="v1",
        record_count=1500,
        checksum="sha256:abc123",
        creator="dataset-owner",
    )

    frozen = service.freeze_dataset(dataset.dataset_id, _TENANT)

    assert frozen.status == DatasetStatus.FROZEN


def test_dataset_registry_lifecycle_transition_does_not_cross_tenant_scope() -> None:
    service = _create_service()
    dataset = service.register_dataset(
        name="tenant-evaluation-set",
        version="v1.0",
        description="Tenant-scoped evaluation dataset",
        storage_uri="s3://datasets/tenant-evaluation-set/v1.0.jsonl",
        storage_type="S3",
        schema_version="1.0",
        record_count=1,
        checksum="sha256:abc123",
        creator="dataset-owner",
        organization_id="org-acme",
        project_id="project-risk",
    )

    with pytest.raises(DatasetNotFoundError, match="does not exist"):
        service.freeze_dataset(dataset.dataset_id, _TENANT)


def test_dataset_registry_deprecates_dataset() -> None:
    service = _create_service()
    dataset = service.register_dataset(
        name="support-faq",
        version="2026-06-26",
        description="Baseline evaluation dataset",
        storage_uri="s3://datasets/support-faq/2026-06-26.parquet",
        storage_type="S3",
        schema_version="v1",
        record_count=1500,
        checksum="sha256:abc123",
        creator="dataset-owner",
    )

    deprecated = service.deprecate_dataset(dataset.dataset_id)

    assert deprecated.status == DatasetStatus.DEPRECATED


def test_dataset_registry_archives_dataset() -> None:
    service = _create_service()
    dataset = service.register_dataset(
        name="support-faq",
        version="2026-06-26",
        description="Baseline evaluation dataset",
        storage_uri="s3://datasets/support-faq/2026-06-26.parquet",
        storage_type="S3",
        schema_version="v1",
        record_count=1500,
        checksum="sha256:abc123",
        creator="dataset-owner",
    )

    archived = service.archive_dataset(dataset.dataset_id)

    assert archived.status == DatasetStatus.ARCHIVED
    assert service.get_dataset(dataset.dataset_id).status == DatasetStatus.ARCHIVED


def test_dataset_registry_rejects_promotion_of_archived_dataset() -> None:
    service = _create_service()
    dataset = service.register_dataset(
        name="support-faq",
        version="2026-06-26",
        description="Baseline evaluation dataset",
        storage_uri="s3://datasets/support-faq/2026-06-26.parquet",
        storage_type="S3",
        schema_version="v1",
        record_count=1500,
        checksum="sha256:abc123",
        creator="dataset-owner",
    )
    service.archive_dataset(dataset.dataset_id)

    with pytest.raises(DatasetLifecycleError):
        service.promote_dataset(dataset.dataset_id)


def test_dataset_registry_retrieves_specific_version_and_lists_versions() -> None:
    service = _create_service()
    original = service.register_dataset(
        name="support-faq",
        version="2026-06-26",
        description="Baseline evaluation dataset",
        storage_uri="s3://datasets/support-faq/2026-06-26.parquet",
        storage_type="S3",
        schema_version="v1",
        record_count=1500,
        checksum="sha256:abc123",
        creator="dataset-owner",
    )
    versioned = service.create_dataset_version(
        dataset_id=original.dataset_id,
        version="2026-07-01",
        checksum="sha256:def456",
        creator="data-steward",
    )

    found = service.get_dataset_version(
        name="support-faq",
        version="2026-07-01",
    )
    versions = service.list_versions(name="support-faq")

    assert found == versioned
    assert versions == [original, versioned]
    assert service.list_datasets() == [original, versioned]


def test_dataset_registry_compares_dataset_versions() -> None:
    service = _create_service()
    original = service.register_dataset(
        name="support-faq",
        version="2026-06-26",
        description="Baseline evaluation dataset",
        storage_uri="s3://datasets/support-faq/2026-06-26.parquet",
        storage_type="S3",
        schema_version="v1",
        record_count=1500,
        checksum="sha256:abc123",
        creator="dataset-owner",
    )
    candidate = service.create_dataset_version(
        dataset_id=original.dataset_id,
        version="2026-07-01",
        description="Expanded evaluation dataset",
        storage_uri="snowflake://datasets/support_faq/2026_07_01",
        storage_type="Snowflake",
        schema_version="v2",
        record_count=2200,
        checksum="sha256:def456",
        creator="data-steward",
    )

    diff = service.compare_dataset_versions(
        baseline_dataset_id=original.dataset_id,
        candidate_dataset_id=candidate.dataset_id,
    )

    assert diff.baseline_dataset_id == original.dataset_id
    assert diff.candidate_dataset_id == candidate.dataset_id
    assert diff.name_changed is False
    assert diff.version_changed is True
    assert diff.description_changed is True
    assert diff.storage_location_changed is True
    assert diff.storage_type_changed is True
    assert diff.schema_version_changed is True
    assert diff.record_count_changed is True
    assert diff.checksum_changed is True
    assert diff.metadata_changed is True
    assert diff.has_changes is True


def _create_service() -> DatasetRegistryService:
    ids = iter(["dataset-1", "dataset-2", "dataset-3"])

    return DatasetRegistryService(
        dataset_repository=InMemoryDatasetRepository(),
        id_generator=lambda: next(ids),
        clock=lambda: datetime(2026, 6, 26, tzinfo=UTC),
    )
