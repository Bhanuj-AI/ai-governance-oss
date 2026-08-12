"""Immutable object storage for dataset content.

The dataset registry owns immutable metadata. This adapter owns only the
bytes referenced by a registry record, using the standard S3 API so local
SeaweedFS and managed AWS S3 share the same application contract.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import BinaryIO
from typing import Any, Protocol

from botocore.config import Config
from botocore.exceptions import ClientError


@dataclass(frozen=True)
class ObjectWriteResult:
    """Whether an immutable object was newly written by this request."""

    created: bool


class DatasetObjectStore(Protocol):
    """Minimal object-store contract required by dataset ingestion."""

    def put_bytes(
        self,
        *,
        bucket: str,
        key: str,
        body: bytes,
        content_type: str,
        metadata: Mapping[str, str] | None = None,
    ) -> ObjectWriteResult:
        """Write one immutable dataset object."""

    def put_stream(
        self,
        *,
        bucket: str,
        key: str,
        body: BinaryIO,
        content_length: int,
        content_type: str,
        metadata: Mapping[str, str],
        if_absent: bool,
    ) -> ObjectWriteResult:
        """Write a seekable upload stream without loading it into application memory."""

    def get_bytes(self, *, bucket: str, key: str) -> bytes:
        """Read one immutable dataset object for governed execution."""

    def delete_object(self, *, bucket: str, key: str) -> None:
        """Delete an object created by a failed cross-system write."""


class S3DatasetObjectStore:
    """Dataset object store implemented with the standard S3 API."""

    def __init__(self, client: Any) -> None:
        self._client = client

    @classmethod
    def from_environment(cls) -> S3DatasetObjectStore:
        """Create an S3 client for SeaweedFS locally or AWS S3 in production."""

        import boto3

        endpoint_url = _optional_environment("AI_GOVERNANCE_DATASET_S3_ENDPOINT_URL")
        region_name = os.getenv("AI_GOVERNANCE_DATASET_S3_REGION", "us-east-1")
        access_key = _optional_environment("AI_GOVERNANCE_DATASET_S3_ACCESS_KEY_ID")
        secret_key = _optional_environment("AI_GOVERNANCE_DATASET_S3_SECRET_ACCESS_KEY")
        force_path_style = _boolean_environment(
            "AI_GOVERNANCE_DATASET_S3_FORCE_PATH_STYLE",
            default=endpoint_url is not None,
        )
        return cls(
            boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                region_name=region_name,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                config=Config(
                    s3={"addressing_style": "path" if force_path_style else "auto"}
                ),
            )
        )

    def put_bytes(
        self,
        *,
        bucket: str,
        key: str,
        body: bytes,
        content_type: str,
        metadata: Mapping[str, str] | None = None,
    ) -> ObjectWriteResult:
        self._client.put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
            Metadata=dict(metadata or {}),
        )
        return ObjectWriteResult(created=True)

    def put_stream(
        self,
        *,
        bucket: str,
        key: str,
        body: BinaryIO,
        content_length: int,
        content_type: str,
        metadata: Mapping[str, str],
        if_absent: bool,
    ) -> ObjectWriteResult:
        try:
            self._client.put_object(
                Bucket=bucket,
                Key=key,
                Body=body,
                ContentLength=content_length,
                ContentType=content_type,
                Metadata=dict(metadata),
                **({"IfNoneMatch": "*"} if if_absent else {}),
            )
            return ObjectWriteResult(created=True)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if not if_absent or code not in {"412", "PreconditionFailed"}:
                raise
            existing = self._client.head_object(Bucket=bucket, Key=key)
            existing_metadata = existing.get("Metadata", {})
            if existing_metadata.get("checksum") != metadata.get("checksum"):
                raise ValueError("An existing dataset object failed checksum verification.") from exc
            return ObjectWriteResult(created=False)

    def get_bytes(self, *, bucket: str, key: str) -> bytes:
        """Read immutable dataset bytes through the configured S3 API."""
        response = self._client.get_object(Bucket=bucket, Key=key)
        body = response["Body"]
        try:
            return body.read()
        finally:
            body.close()

    def delete_object(self, *, bucket: str, key: str) -> None:
        self._client.delete_object(Bucket=bucket, Key=key)


class FilesystemDatasetObjectStore:
    """Local-development object store rooted at one configured directory.

    It preserves the same immutable object-key contract as S3 without making
    the non-Docker workflow depend on a local object-storage service.
    """

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    @property
    def root(self) -> Path:
        return self._root

    @classmethod
    def from_environment(cls) -> "FilesystemDatasetObjectStore":
        configured_root = _optional_environment("AI_GOVERNANCE_DATASET_FILESYSTEM_ROOT")
        return cls(Path(configured_root or ".ai-governance/datasets"))

    def put_bytes(
        self,
        *,
        bucket: str,
        key: str,
        body: bytes,
        content_type: str,
        metadata: Mapping[str, str] | None = None,
    ) -> ObjectWriteResult:
        del content_type, metadata
        return self._write_if_absent(bucket=bucket, key=key, chunks=(body,))

    def put_stream(
        self,
        *,
        bucket: str,
        key: str,
        body: BinaryIO,
        content_length: int,
        content_type: str,
        metadata: Mapping[str, str],
        if_absent: bool,
    ) -> ObjectWriteResult:
        del content_length, content_type, metadata
        path = self._path(bucket, key)
        if path.exists() and if_absent:
            return ObjectWriteResult(created=False)
        if path.exists():
            raise ValueError("Filesystem dataset objects are immutable.")
        return self._write_if_absent(
            bucket=bucket,
            key=key,
            chunks=iter(lambda: body.read(1024 * 1024), b""),
        )

    def get_bytes(self, *, bucket: str, key: str) -> bytes:
        return self._path(bucket, key).read_bytes()

    def delete_object(self, *, bucket: str, key: str) -> None:
        path = self._path(bucket, key)
        if path.exists():
            path.unlink()

    def uri_for(self, *, bucket: str, key: str) -> str:
        return self._path(bucket, key).as_uri()

    def get_bytes_for_uri(self, storage_uri: str) -> bytes:
        from urllib.parse import unquote, urlparse

        parsed = urlparse(storage_uri)
        if parsed.scheme != "file":
            raise ValueError("Filesystem dataset storage requires a file URI.")
        path = Path(unquote(parsed.path)).resolve()
        try:
            path.relative_to(self._root)
        except ValueError as exc:
            raise ValueError("Dataset file URI is outside the configured object-store root.") from exc
        return path.read_bytes()

    def _write_if_absent(
        self, *, bucket: str, key: str, chunks: Iterable[bytes]
    ) -> ObjectWriteResult:
        path = self._path(bucket, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb") as target:
                for chunk in chunks:
                    target.write(chunk)
        except FileExistsError:
            return ObjectWriteResult(created=False)
        return ObjectWriteResult(created=True)

    def _path(self, bucket: str, key: str) -> Path:
        path = self._root.joinpath(*_filesystem_object_path_parts(bucket, key)).resolve()
        try:
            path.relative_to(self._root)
        except ValueError as exc:
            raise ValueError("Dataset object key escapes the configured filesystem root.") from exc
        return path


def dataset_object_uri(
    object_store: DatasetObjectStore, *, bucket: str, key: str
) -> str:
    """Return the immutable registry URI for an object-store key."""
    if isinstance(object_store, FilesystemDatasetObjectStore):
        return object_store.uri_for(bucket=bucket, key=key)
    return f"s3://{bucket}/{key}"


def dataset_object_store_from_environment() -> DatasetObjectStore | None:
    """Resolve the optional dataset-content store from runtime configuration."""

    backend = os.getenv("AI_GOVERNANCE_DATASET_OBJECT_STORE_BACKEND", "none").strip().lower()
    if backend in {"", "none"}:
        return None
    if backend == "s3":
        return S3DatasetObjectStore.from_environment()
    if backend == "filesystem":
        return FilesystemDatasetObjectStore.from_environment()
    raise ValueError(
        "AI_GOVERNANCE_DATASET_OBJECT_STORE_BACKEND must be 'none', 'filesystem', or 's3'."
    )


def _optional_environment(name: str) -> str | None:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else None


def _boolean_environment(name: str, *, default: bool) -> bool:
    value = _optional_environment(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _filesystem_object_path_parts(bucket: str, key: str) -> tuple[str, ...]:
    """Return validated relative path components for the local object-store adapter."""

    return _safe_filesystem_path_parts(bucket, "bucket", allow_nested=False) + _safe_filesystem_path_parts(
        key,
        "key",
        allow_nested=True,
    )


def _safe_filesystem_path_parts(
    value: str,
    label: str,
    *,
    allow_nested: bool,
) -> tuple[str, ...]:
    """Reject absolute or traversal path syntax before joining filesystem paths."""

    if not value or "\x00" in value or "\\" in value or PureWindowsPath(value).is_absolute():
        raise ValueError(f"Dataset object {label} must be a non-empty relative path.")
    parts = tuple(value.split("/"))
    if (
        value.startswith("/")
        or value.endswith("/")
        or (not allow_nested and len(parts) != 1)
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise ValueError(f"Dataset object {label} contains unsafe path syntax.")
    return parts
