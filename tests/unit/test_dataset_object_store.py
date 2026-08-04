from __future__ import annotations

from io import BytesIO
import boto3
import pytest

from kavach.datasets import (
    S3DatasetObjectStore,
    dataset_object_store_from_environment,
)


def test_s3_dataset_object_store_writes_standard_s3_object() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def put_object(self, **kwargs: object) -> None:
            self.calls.append(kwargs)

    client = FakeClient()
    store = S3DatasetObjectStore(client)

    store.put_bytes(
        bucket="kavach-datasets",
        key="demo/evaluation/v1.0/dataset.jsonl",
        body=b'{"question":"Example"}\n',
        content_type="application/x-ndjson",
        metadata={"dataset_id": "dataset-1"},
    )

    assert client.calls == [
        {
            "Bucket": "kavach-datasets",
            "Key": "demo/evaluation/v1.0/dataset.jsonl",
            "Body": b'{"question":"Example"}\n',
            "ContentType": "application/x-ndjson",
            "Metadata": {"dataset_id": "dataset-1"},
        }
    ]


def test_s3_dataset_object_store_reads_seaweedfs_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeClient:
        pass

    def fake_client(service_name: str, **kwargs: object) -> FakeClient:
        captured["service_name"] = service_name
        captured.update(kwargs)
        return FakeClient()

    monkeypatch.setattr(boto3, "client", fake_client)
    monkeypatch.setenv("KAVACH_DATASET_OBJECT_STORE_BACKEND", "s3")
    monkeypatch.setenv("KAVACH_DATASET_S3_ENDPOINT_URL", "http://seaweedfs:8333")
    monkeypatch.setenv("KAVACH_DATASET_S3_REGION", "us-east-1")
    monkeypatch.setenv("KAVACH_DATASET_S3_ACCESS_KEY_ID", "kavach-local")
    monkeypatch.setenv("KAVACH_DATASET_S3_SECRET_ACCESS_KEY", "kavach-local-secret")
    monkeypatch.setenv("KAVACH_DATASET_S3_FORCE_PATH_STYLE", "true")

    store = dataset_object_store_from_environment()

    assert isinstance(store, S3DatasetObjectStore)
    assert captured["service_name"] == "s3"
    assert captured["endpoint_url"] == "http://seaweedfs:8333"
    assert captured["region_name"] == "us-east-1"
    assert captured["aws_access_key_id"] == "kavach-local"
    assert captured["aws_secret_access_key"] == "kavach-local-secret"
    assert captured["config"].s3 == {"addressing_style": "path"}


def test_dataset_object_store_is_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("KAVACH_DATASET_OBJECT_STORE_BACKEND", raising=False)

    assert dataset_object_store_from_environment() is None


def test_dataset_object_store_rejects_unknown_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KAVACH_DATASET_OBJECT_STORE_BACKEND", "filesystem")

    with pytest.raises(ValueError, match="must be 'none' or 's3'"):
        dataset_object_store_from_environment()


def test_s3_dataset_object_store_uses_conditional_stream_write_and_delete() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.put_calls: list[dict[str, object]] = []
            self.deleted: list[dict[str, str]] = []

        def put_object(self, **kwargs: object) -> None:
            self.put_calls.append(kwargs)

        def delete_object(self, **kwargs: str) -> None:
            self.deleted.append(kwargs)

    client = FakeClient()
    stream = BytesIO(b'{"question":"Example"}\n')
    result = S3DatasetObjectStore(client).put_stream(
        bucket="kavach-datasets",
        key="datasets/org/project/id/v1/checksum.jsonl",
        body=stream,
        content_length=23,
        content_type="application/x-ndjson",
        metadata={"checksum": "sha256:checksum"},
        if_absent=True,
    )
    S3DatasetObjectStore(client).delete_object(
        bucket="kavach-datasets",
        key="datasets/org/project/id/v1/checksum.jsonl",
    )

    assert result.created is True
    assert client.put_calls[0]["IfNoneMatch"] == "*"
    assert client.deleted == [{"Bucket": "kavach-datasets", "Key": "datasets/org/project/id/v1/checksum.jsonl"}]
