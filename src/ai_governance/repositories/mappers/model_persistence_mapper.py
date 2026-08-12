from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from ai_governance.domain.models import (
    AssetProvenance,
    Model,
    ModelStatus,
)
from ai_governance.domain.models.runtime_capabilities import (
    ModelRuntimeCapabilitySnapshot,
)


class ModelPersistenceMapper:
    """
    Maps Model domain objects to and from persistence records.
    """

    @staticmethod
    def to_persistence_record(
        model: Model,
    ) -> dict[str, Any]:
        return {
            "model_id": model.model_id,
            "provider": model.provider,
            "model_name": model.model_name,
            "version": model.version,
            "parameters_json": json.dumps(
                {
                    "_ai_governance_model_record_version": 1,
                    "model_parameters": model.parameters,
                    "runtime_capabilities": model.runtime_capabilities.to_record(),
                    "provider_model_id": model.provider_model_id,
                }
            ),
            "cost_json": json.dumps(model.cost),
            "latency": model.latency,
            "context_window": model.context_window,
            "creator": model.creator,
            "created_at": model.created_at.isoformat(),
            "status": model.status.value,
            "provenance": model.provenance.value,
            "source_system": model.source_system,
            "source_reference": model.source_reference,
            "tenant_id": model.tenant_id,
            "organization_id": model.organization_id,
            "project_id": model.project_id,
        }

    @staticmethod
    def from_persistence_record(
        record: Mapping[str, Any],
    ) -> Model:
        parameter_record = json.loads(record["parameters_json"] or "{}")
        is_envelope = parameter_record.get("_ai_governance_model_record_version") == 1
        return Model(
            model_id=record["model_id"],
            provider=record["provider"],
            model_name=record["model_name"],
            version=record["version"],
            parameters=(
                dict(parameter_record.get("model_parameters", {}))
                if is_envelope
                else parameter_record
            ),
            cost=json.loads(record["cost_json"])
            if record["cost_json"] is not None
            else None,
            latency=record["latency"],
            context_window=record["context_window"],
            creator=record["creator"],
            created_at=datetime.fromisoformat(record["created_at"]),
            status=ModelStatus(record["status"]),
            provenance=AssetProvenance(_value(record, "provenance", "MANAGED")),
            source_system=_optional_value(record, "source_system"),
            source_reference=_optional_value(record, "source_reference"),
            tenant_id=str(_value(record, "tenant_id", "org_default")),
            organization_id=str(_value(record, "organization_id", "org_default")),
            project_id=str(_value(record, "project_id", "project_default")),
            runtime_capabilities=(
                ModelRuntimeCapabilitySnapshot.from_record(
                    dict(parameter_record["runtime_capabilities"])
                )
                if is_envelope and isinstance(parameter_record.get("runtime_capabilities"), dict)
                else None
            ),
            provider_model_id=(
                str(parameter_record["provider_model_id"])
                if is_envelope and parameter_record.get("provider_model_id") is not None
                else None
            ),
        )

    @classmethod
    def from_persistence_records(
        cls,
        records: list[Mapping[str, Any]],
    ) -> list[Model]:
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
