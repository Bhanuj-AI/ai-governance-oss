from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from kavach.domain.prompts import (
    AssetProvenance,
    Prompt,
    PromptStatus,
)


class PromptPersistenceMapper:
    """
    Maps Prompt domain objects to and from persistence records.
    """

    @staticmethod
    def to_persistence_record(
        prompt: Prompt,
    ) -> dict[str, Any]:
        return {
            "prompt_id": prompt.prompt_id,
            "name": prompt.name,
            "version": prompt.version,
            "template": prompt.template,
            "variables_json": json.dumps(list(prompt.variables)),
            "created_at": prompt.created_at.isoformat(),
            "created_by": prompt.created_by,
            "status": prompt.status.value,
            "provenance": prompt.provenance.value,
            "source_system": prompt.source_system,
            "source_reference": prompt.source_reference,
            "content_hash": prompt.content_hash,
            # PostgreSQL has a native boolean column. SQLite accepts bool and
            # persists it as its compatible integer representation.
            "content_available": prompt.content_available,
            "tenant_id": prompt.tenant_id,
            "organization_id": prompt.organization_id,
            "project_id": prompt.project_id,
        }

    @staticmethod
    def from_persistence_record(
        record: Mapping[str, Any],
    ) -> Prompt:
        return Prompt(
            prompt_id=record["prompt_id"],
            name=record["name"],
            version=record["version"],
            template=record["template"],
            variables=tuple(json.loads(record["variables_json"] or "[]")),
            created_at=datetime.fromisoformat(record["created_at"]),
            created_by=record["created_by"],
            status=PromptStatus(record["status"]),
            provenance=AssetProvenance(_value(record, "provenance", "MANAGED")),
            source_system=_optional_value(record, "source_system"),
            source_reference=_optional_value(record, "source_reference"),
            content_hash=_optional_value(record, "content_hash"),
            content_available=bool(_value(record, "content_available", 1)),
            tenant_id=str(_value(record, "tenant_id", "org_default")),
            organization_id=str(_value(record, "organization_id", "org_default")),
            project_id=str(_value(record, "project_id", "project_default")),
        )

    @classmethod
    def from_persistence_records(
        cls,
        records: list[Mapping[str, Any]],
    ) -> list[Prompt]:
        return [
            cls.from_persistence_record(record)
            for record in records
        ]


def _value(record: Mapping[str, Any], key: str, default: Any) -> Any:
    try:
        return record[key]
    except (KeyError, IndexError):
        return default


def _optional_value(record: Mapping[str, Any], key: str) -> str | None:
    value = _value(record, key, None)
    return str(value) if value is not None else None
