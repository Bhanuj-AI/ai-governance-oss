from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def lowercase_record(
    record: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        key.lower(): value
        for key, value in record.items()
    }


def lowercase_records(
    records: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        lowercase_record(record)
        for record in records
    ]
