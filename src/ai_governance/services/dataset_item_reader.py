"""Tenant-scoped readers for immutable evaluation dataset records."""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from io import StringIO
from typing import Any, Protocol
from urllib.parse import urlparse

from ai_governance.datasets.object_store import (
    DatasetObjectStore,
    FilesystemDatasetObjectStore,
)
from ai_governance.domain.datasets import Dataset
from ai_governance.tenancy.domain import TenantContext


class DatasetItemReadError(ValueError):
    """Raised when immutable dataset content cannot be used for execution."""


@dataclass(frozen=True)
class DatasetItem:
    """One immutable input record selected from a governed dataset version."""

    item_id: str
    input_text: str
    context_text: str
    variables: Mapping[str, str]
    metadata: Mapping[str, Any]


class DatasetItemReader(Protocol):
    """Resolve the exact records represented by a registered dataset version."""

    def read_items(
        self, dataset: Dataset, context: TenantContext
    ) -> tuple[DatasetItem, ...]: ...


class DatasetObjectStoreItemReader:
    """Read JSONL/CSV content from a configured immutable object store."""

    def __init__(self, object_store: DatasetObjectStore | None) -> None:
        self._object_store = object_store

    def read_items(
        self, dataset: Dataset, context: TenantContext
    ) -> tuple[DatasetItem, ...]:
        if dataset.organization_id != context.organization_id or (
            dataset.project_id != (context.project_id or "")
        ):
            raise DatasetItemReadError("Dataset is not available in the current tenant scope.")
        if self._object_store is None:
            raise DatasetItemReadError(
                "Dataset content storage is not configured for candidate execution."
            )
        try:
            body, extension = self._read_bytes(dataset.storage_uri)
        except DatasetItemReadError:
            raise
        except Exception as exc:
            raise DatasetItemReadError(
                "Dataset content could not be read for candidate execution."
            ) from exc

        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DatasetItemReadError("Dataset content must be UTF-8 encoded.") from exc

        if extension in {"jsonl", "ndjson"}:
            records = _jsonl_records(text)
        elif extension == "csv":
            records = _csv_records(text)
        else:
            raise DatasetItemReadError(
                "Candidate execution supports JSONL and CSV dataset records only."
            )

        if not records:
            raise DatasetItemReadError("Dataset contains no executable records.")
        if dataset.record_count != len(records):
            raise DatasetItemReadError(
                "Dataset record count does not match its immutable registered content."
            )
        return tuple(
            _dataset_item(dataset.dataset_id, index, record)
            for index, record in enumerate(records, start=1)
        )

    def _read_bytes(self, storage_uri: str) -> tuple[bytes, str]:
        parsed = urlparse(storage_uri)
        if parsed.scheme == "s3":
            bucket, key = _parse_s3_uri(storage_uri)
            return (
                self._object_store.get_bytes(bucket=bucket, key=key),
                key.rsplit(".", maxsplit=1)[-1].lower() if "." in key else "",
            )
        if parsed.scheme == "file" and isinstance(
            self._object_store, FilesystemDatasetObjectStore
        ):
            return (
                self._object_store.get_bytes_for_uri(storage_uri),
                parsed.path.rsplit(".", maxsplit=1)[-1].lower()
                if "." in parsed.path
                else "",
            )
        raise DatasetItemReadError(
            "Candidate execution requires dataset content in the configured object store."
        )


def _parse_s3_uri(value: str) -> tuple[str, str]:
    parsed = urlparse(value)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.lstrip("/"):
        raise DatasetItemReadError(
            "Candidate execution requires an S3-backed immutable dataset."
        )
    return parsed.netloc, parsed.path.lstrip("/")


def _jsonl_records(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DatasetItemReadError(f"Dataset JSONL record {number} is invalid.") from exc
        if not isinstance(record, dict):
            raise DatasetItemReadError(f"Dataset JSONL record {number} must be an object.")
        records.append(record)
    return records


def _csv_records(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames or any(not field or not field.strip() for field in reader.fieldnames):
        raise DatasetItemReadError("Dataset CSV requires named header fields.")
    return [dict(record) for record in reader]


def _dataset_item(dataset_id: str, index: int, record: Mapping[str, Any]) -> DatasetItem:
    variables = {key: _stringify(value) for key, value in record.items()}
    input_text = _first_non_empty(variables, "input", "question", "prompt", "query")
    if not input_text:
        raise DatasetItemReadError(
            f"Dataset record {index} requires one of: input, question, prompt, query."
        )
    context_text = _first_non_empty(variables, "context", "contexts", "source", "sources")
    digest = hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()[:16]
    return DatasetItem(
        item_id=f"{dataset_id}:{index}:{digest}",
        input_text=input_text,
        context_text=context_text,
        variables=variables,
        metadata={"dataset_record_index": index},
    )


def _first_non_empty(values: Mapping[str, str], *keys: str) -> str:
    for key in keys:
        value = values.get(key, "").strip()
        if value:
            return value
    return ""


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)


# Preserve the initial public name while supporting local filesystem storage.
S3DatasetItemReader = DatasetObjectStoreItemReader
