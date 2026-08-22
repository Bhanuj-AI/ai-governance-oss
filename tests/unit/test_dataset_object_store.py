from __future__ import annotations

from io import BytesIO

import boto3
import pytest

from ai_governance.datasets import (
    FilesystemDatasetObjectStore,
    S3DatasetObjectStore,
    dataset_object_store_from_environment,
    dataset_object_uri,
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
        bucket="ai-governance-datasets",
        key="demo/evaluation/v1.0/dataset.jsonl",
        body=b'{"question":"Example"}\n',
        content_type="application/x-ndjson",
        metadata={"dataset_id": "dataset-1"},
    )

    assert client.calls == [
        {
            "Bucket": "ai-governance-datasets",
            "Key": "demo/evaluation/v1.0/dataset.jsonl",
            "Body": b'{"question":"Example"}\n',
            "ContentType": "application/x-ndjson",
            "Metadata": {"dataset_id": "dataset-1"},
        }
    ]


def test_s3_dataset_object_store_reads_dataset_bytes() -> None:
    class FakeBody:
        def __init__(self) -> None:
            self.closed = False

        def read(self) -> bytes:
            return b'{"question":"Example"}\n'

        def close(self) -> None:
            self.closed = True

    class FakeClient:
        def __init__(self) -> None:
            self.body = FakeBody()
            self.calls: list[dict[str, str]] = []

        def get_object(self, **kwargs: str) -> dict[str, FakeBody]:
            self.calls.append(kwargs)
            return {"Body": self.body}

    client = FakeClient()
    assert S3DatasetObjectStore(client).get_bytes(
        bucket="ai-governance-datasets", key="example.jsonl"
    ) == b'{"question":"Example"}\n'
    assert client.calls == [{"Bucket": "ai-governance-datasets", "Key": "example.jsonl"}]
    assert client.body.closed is True


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
    monkeypatch.setenv("AI_GOVERNANCE_DATASET_OBJECT_STORE_BACKEND", "s3")
    monkeypatch.setenv("AI_GOVERNANCE_DATASET_S3_ENDPOINT_URL", "http://seaweedfs:8333")
    monkeypatch.setenv("AI_GOVERNANCE_DATASET_S3_REGION", "us-east-1")
    monkeypatch.setenv("AI_GOVERNANCE_DATASET_S3_ACCESS_KEY_ID", "ai-governance-local")
    monkeypatch.setenv("AI_GOVERNANCE_DATASET_S3_SECRET_ACCESS_KEY", "ai-governance-local-secret")
    monkeypatch.setenv("AI_GOVERNANCE_DATASET_S3_FORCE_PATH_STYLE", "true")

    store = dataset_object_store_from_environment()

    assert isinstance(store, S3DatasetObjectStore)
    assert captured["service_name"] == "s3"
    assert captured["endpoint_url"] == "http://seaweedfs:8333"
    assert captured["region_name"] == "us-east-1"
    assert captured["aws_access_key_id"] == "ai-governance-local"
    assert captured["aws_secret_access_key"] == "ai-governance-local-secret"
    assert captured["config"].s3 == {"addressing_style": "path"}


def test_dataset_object_store_is_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AI_GOVERNANCE_DATASET_OBJECT_STORE_BACKEND", raising=False)

    assert dataset_object_store_from_environment() is None


def test_filesystem_dataset_object_store_preserves_immutable_content(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("AI_GOVERNANCE_DATASET_OBJECT_STORE_BACKEND", "filesystem")
    monkeypatch.setenv("AI_GOVERNANCE_DATASET_FILESYSTEM_ROOT", str(tmp_path))

    store = dataset_object_store_from_environment()

    assert isinstance(store, FilesystemDatasetObjectStore)
    assert store.put_bytes(
        bucket="datasets", key="support/v1.jsonl", body=b'{"question":"Example"}\n',
        content_type="application/x-ndjson",
    ).created is True
    assert store.get_bytes(bucket="datasets", key="support/v1.jsonl") == b'{"question":"Example"}\n'
    assert dataset_object_uri(store, bucket="datasets", key="support/v1.jsonl").startswith("file://")
    assert store.put_bytes(
        bucket="datasets", key="support/v1.jsonl", body=b"different", content_type="text/plain"
    ).created is False


@pytest.mark.parametrize(
    ("bucket", "key"),
    [
        ("../datasets", "support/v1.jsonl"),
        ("datasets", "../outside.jsonl"),
        ("datasets", "support/../../outside.jsonl"),
        ("datasets", "/outside.jsonl"),
        ("datasets/other", "support/v1.jsonl"),
        ("datasets", "C:/outside.jsonl"),
        ("datasets", "support\\outside.jsonl"),
    ],
)
def test_filesystem_dataset_object_store_rejects_unsafe_object_paths(
    tmp_path,
    bucket: str,
    key: str,
) -> None:
    store = FilesystemDatasetObjectStore(tmp_path)

    with pytest.raises(ValueError, match="unsafe path|relative path"):
        store.put_bytes(
            bucket=bucket,
            key=key,
            body=b'{"question":"Example"}\n',
            content_type="application/x-ndjson",
        )


def test_filesystem_dataset_object_store_rejects_symlink_escape(tmp_path) -> None:
    store = FilesystemDatasetObjectStore(tmp_path)
    (tmp_path / "datasets").symlink_to(tmp_path.parent, target_is_directory=True)

    with pytest.raises(ValueError, match="escapes the configured filesystem root"):
        store.put_bytes(
            bucket="datasets",
            key="outside.jsonl",
            body=b'{"question":"Example"}\n',
            content_type="application/x-ndjson",
        )


def test_dataset_object_store_rejects_unknown_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_GOVERNANCE_DATASET_OBJECT_STORE_BACKEND", "unknown")

    with pytest.raises(ValueError, match="must be 'none', 'filesystem', or 's3'"):
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
        bucket="ai-governance-datasets",
        key="datasets/org/project/id/v1/checksum.jsonl",
        body=stream,
        content_length=23,
        content_type="application/x-ndjson",
        metadata={"checksum": "sha256:checksum"},
        if_absent=True,
    )
    S3DatasetObjectStore(client).delete_object(
        bucket="ai-governance-datasets",
        key="datasets/org/project/id/v1/checksum.jsonl",
    )

    assert result.created is True
    assert client.put_calls[0]["IfNoneMatch"] == "*"
    assert client.deleted == [{"Bucket": "ai-governance-datasets", "Key": "datasets/org/project/id/v1/checksum.jsonl"}]
