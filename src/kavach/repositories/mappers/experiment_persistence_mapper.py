from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from kavach.domain.experiments import (
    Experiment,
    ExperimentStatus,
)


class ExperimentPersistenceMapper:
    """
    Maps Experiment domain objects to and from persistence records.
    """

    @staticmethod
    def to_persistence_record(
        experiment: Experiment,
    ) -> dict[str, Any]:
        return {
            "experiment_id": experiment.experiment_id,
            "name": experiment.name,
            "description": experiment.description,
            "owner": experiment.owner,
            "created_at": experiment.created_at.isoformat(),
            "updated_at": experiment.updated_at.isoformat(),
            "status": experiment.status.value,
            "organization_id": experiment.organization_id,
            "project_id": experiment.project_id,
        }

    @staticmethod
    def from_persistence_record(
        record: Mapping[str, Any],
    ) -> Experiment:
        return Experiment(
            experiment_id=record["experiment_id"],
            name=record["name"],
            description=record["description"],
            owner=record["owner"],
            created_at=datetime.fromisoformat(record["created_at"]),
            status=ExperimentStatus(record["status"]),
            organization_id=_value(record, "organization_id", "org_default"),
            project_id=_value(record, "project_id", "project_default"),
            updated_at=_datetime_value(record, "updated_at", record["created_at"]),
        )

    @classmethod
    def from_persistence_records(
        cls,
        records: list[Mapping[str, Any]],
    ) -> list[Experiment]:
        return [cls.from_persistence_record(record) for record in records]


def _value(record: Mapping[str, Any], key: str, default: str) -> str:
    try:
        return str(record[key])
    except (KeyError, IndexError):
        return default


def _datetime_value(
    record: Mapping[str, Any],
    key: str,
    default: str,
) -> datetime:
    try:
        return datetime.fromisoformat(str(record[key]))
    except (KeyError, TypeError, ValueError):
        return datetime.fromisoformat(default)
