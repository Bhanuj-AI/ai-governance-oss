from __future__ import annotations

import pytest

from ai_governance.datasets import DatasetUploadValidationError, inspect_uploaded_dataset


def test_inspect_jsonl_dataset_returns_record_count_checksum_and_content_type() -> None:
    content = inspect_uploaded_dataset(
        filename="evaluation.jsonl",
        body=b'{"question":"one"}\n{"question":"two"}\n',
        max_bytes=1024,
    )

    assert content.record_count == 2
    assert content.content_type == "application/x-ndjson"
    assert content.extension == "jsonl"
    assert content.checksum.startswith("sha256:")
    assert content.content_length == 38


def test_inspect_csv_dataset_requires_header_and_records() -> None:
    content = inspect_uploaded_dataset(
        filename="evaluation.csv",
        body=b"question,expected_answer\nWhat?,This\n",
        max_bytes=1024,
    )

    assert content.record_count == 1
    assert content.content_type == "text/csv"


@pytest.mark.parametrize(
    ("filename", "body", "message"),
    [
        ("evaluation.txt", b"not supported", "Only .csv"),
        ("evaluation.jsonl", b"{not-json}\n", "Invalid JSON"),
        ("evaluation.csv", b"question\n", "contains no records"),
    ],
)
def test_inspect_dataset_rejects_invalid_uploads(
    filename: str,
    body: bytes,
    message: str,
) -> None:
    with pytest.raises(DatasetUploadValidationError, match=message):
        inspect_uploaded_dataset(filename=filename, body=body, max_bytes=1024)
