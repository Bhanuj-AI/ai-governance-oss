from datetime import UTC, datetime

from ai_governance.datasets import FilesystemDatasetObjectStore, dataset_object_uri
from ai_governance.domain.datasets import Dataset, DatasetStatus
from ai_governance.services.dataset_item_reader import DatasetObjectStoreItemReader
from ai_governance.tenancy.domain import TenantContext


def test_filesystem_reader_resolves_registered_dataset_content(tmp_path) -> None:
    store = FilesystemDatasetObjectStore(tmp_path)
    bucket = "ai-governance-datasets"
    key = "datasets/org/project/support/v1/data.jsonl"
    store.put_bytes(
        bucket=bucket,
        key=key,
        body=b'{"question":"What is covered?","context":"The policy covers support."}\n',
        content_type="application/x-ndjson",
    )
    dataset = Dataset(
        dataset_id="support-v1",
        name="Support",
        version="v1",
        description="Support evaluation data",
        storage_uri=dataset_object_uri(store, bucket=bucket, key=key),
        storage_type="filesystem",
        schema_version="v1",
        record_count=1,
        checksum="sha256:test",
        creator="test",
        created_at=datetime(2026, 8, 11, tzinfo=UTC),
        status=DatasetStatus.FROZEN,
        organization_id="org",
        project_id="project",
    )

    items = DatasetObjectStoreItemReader(store).read_items(
        dataset,
        TenantContext(
            organization_id="org",
            project_id="project",
            actor_id="test",
            request_id="request-1",
        ),
    )

    assert len(items) == 1
    assert items[0].input_text == "What is covered?"
    assert items[0].context_text == "The policy covers support."
