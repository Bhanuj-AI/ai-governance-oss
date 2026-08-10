"""S3-compatible object storage for dataset content.

The dataset registry owns immutable metadata. This adapter owns only the
bytes referenced by a registry record, using the standard S3 API so local
SeaweedFS and managed AWS S3 share the same application contract.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
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

    def delete_object(self, *, bucket: str, key: str) -> None:
        self._client.delete_object(Bucket=bucket, Key=key)


def dataset_object_store_from_environment() -> DatasetObjectStore | None:
    """Resolve the optional dataset-content store from runtime configuration."""

    backend = os.getenv("AI_GOVERNANCE_DATASET_OBJECT_STORE_BACKEND", "none").strip().lower()
    if backend in {"", "none"}:
        return None
    if backend == "s3":
        return S3DatasetObjectStore.from_environment()
    raise ValueError(
        "AI_GOVERNANCE_DATASET_OBJECT_STORE_BACKEND must be 'none' or 's3'."
    )


def _optional_environment(name: str) -> str | None:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else None


def _boolean_environment(name: str, *, default: bool) -> bool:
    value = _optional_environment(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}
