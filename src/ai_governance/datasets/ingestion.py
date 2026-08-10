"""Bounded streaming validation and identity helpers for uploaded datasets."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from io import TextIOWrapper
from pathlib import PurePath
from typing import BinaryIO
from uuid import NAMESPACE_URL, uuid5


class DatasetUploadValidationError(ValueError):
    """Raised when an uploaded dataset cannot be registered safely."""


@dataclass(frozen=True)
class UploadedDatasetContent:
    content_type: str
    extension: str
    record_count: int
    checksum: str
    content_length: int


def inspect_uploaded_dataset(
    *, filename: str | None, body: bytes, max_bytes: int
) -> UploadedDatasetContent:
    """Compatibility helper for bytes-based callers and focused tests."""

    from io import BytesIO

    return inspect_uploaded_dataset_stream(
        filename=filename,
        stream=BytesIO(body),
        max_bytes=max_bytes,
        max_record_bytes=max_bytes,
        max_fields=256,
    )


def inspect_uploaded_dataset_stream(
    *,
    filename: str | None,
    stream: BinaryIO,
    max_bytes: int,
    max_record_bytes: int,
    max_fields: int,
) -> UploadedDatasetContent:
    """Validate CSV/JSONL using a seekable spooled stream and bounded records."""

    if not filename:
        raise DatasetUploadValidationError("A dataset filename is required.")
    suffix = PurePath(filename).suffix.lower()
    if suffix in {".jsonl", ".ndjson"}:
        content_type, extension = "application/x-ndjson", "jsonl"
    elif suffix == ".csv":
        content_type, extension = "text/csv", "csv"
    else:
        raise DatasetUploadValidationError("Only .csv, .jsonl, and .ndjson datasets are supported.")

    content_length, checksum = _measure(stream, max_bytes)
    stream.seek(0)
    if suffix in {".jsonl", ".ndjson"}:
        record_count = _jsonl_record_count(stream, max_record_bytes, max_fields)
    else:
        record_count = _csv_record_count(stream, max_record_bytes, max_fields)
    stream.seek(0)
    return UploadedDatasetContent(content_type, extension, record_count, checksum, content_length)


def dataset_id_for_upload(*, organization_id: str, project_id: str, name: str, version: str, checksum: str) -> str:
    return uuid5(NAMESPACE_URL, f"ai-governance:dataset:{organization_id}:{project_id}:{name}:{version}:{checksum}").hex


def object_key_for_upload(*, organization_id: str, project_id: str, dataset_id: str, version: str, checksum: str, extension: str) -> str:
    return "/".join(["datasets", _slug(organization_id), _slug(project_id), dataset_id, _slug(version), f"{checksum.removeprefix('sha256:')}.{extension}"])


def _measure(stream: BinaryIO, max_bytes: int) -> tuple[int, str]:
    digest, total = hashlib.sha256(), 0
    stream.seek(0)
    while chunk := stream.read(1024 * 1024):
        total += len(chunk)
        if total > max_bytes:
            raise DatasetUploadValidationError(f"Dataset upload exceeds the {max_bytes:,}-byte limit.")
        digest.update(chunk)
    if not total:
        raise DatasetUploadValidationError("The uploaded dataset is empty.")
    return total, f"sha256:{digest.hexdigest()}"


def _jsonl_record_count(stream: BinaryIO, max_record_bytes: int, max_fields: int) -> int:
    count = 0
    text = TextIOWrapper(stream, encoding="utf-8", errors="strict", newline="")
    try:
        for number, line in enumerate(text, start=1):
            if len(line.encode("utf-8")) > max_record_bytes:
                raise DatasetUploadValidationError(f"Record {number} exceeds the record-size limit.")
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DatasetUploadValidationError(f"Invalid JSON on line {number}.") from exc
            if not isinstance(value, dict) or len(value) > max_fields:
                raise DatasetUploadValidationError(f"JSONL line {number} must be an object with at most {max_fields} fields.")
            count += 1
    finally:
        text.detach()
    if not count:
        raise DatasetUploadValidationError("The JSONL dataset contains no records.")
    return count


def _csv_record_count(stream: BinaryIO, max_record_bytes: int, max_fields: int) -> int:
    text = TextIOWrapper(stream, encoding="utf-8", errors="strict", newline="")
    try:
        reader = csv.reader(text)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise DatasetUploadValidationError("CSV datasets require a header row.") from exc
        if not header or len(header) > max_fields or not all(field.strip() for field in header):
            raise DatasetUploadValidationError(f"CSV datasets require up to {max_fields} named header fields.")
        count = 0
        for number, row in enumerate(reader, start=2):
            if len(row) > max_fields or sum(len(field.encode("utf-8")) for field in row) > max_record_bytes:
                raise DatasetUploadValidationError(f"Record {number} exceeds dataset field or size limits.")
            count += 1
    finally:
        text.detach()
    if not count:
        raise DatasetUploadValidationError("The CSV dataset contains no records.")
    return count


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "dataset"
