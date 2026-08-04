from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from kavach.domain.experiments import (
    EvaluationRun,
    EvaluationRunStatus,
)


class EvaluationRunPersistenceMapper:
    """
    Maps EvaluationRun domain objects to and from persistence records.
    """

    @staticmethod
    def to_persistence_record(
        run: EvaluationRun,
    ) -> dict[str, Any]:
        return {
            "run_id": run.run_id,
            "experiment_id": run.experiment_id,
            "candidate_id": run.candidate_id,
            "dataset_version": run.dataset_version,
            "evaluation_provider": run.evaluation_provider,
            "evaluation_result_id": run.evaluation_result_id,
            "started_at": run.started_at.isoformat()
            if run.started_at is not None
            else None,
            "completed_at": run.completed_at.isoformat()
            if run.completed_at is not None
            else None,
            "status": run.status.value,
        }

    @staticmethod
    def from_persistence_record(
        record: Mapping[str, Any],
    ) -> EvaluationRun:
        return EvaluationRun(
            run_id=record["run_id"],
            experiment_id=record["experiment_id"],
            candidate_id=record["candidate_id"],
            dataset_version=record["dataset_version"],
            evaluation_provider=record["evaluation_provider"],
            evaluation_result_id=record["evaluation_result_id"],
            started_at=datetime.fromisoformat(record["started_at"])
            if record["started_at"] is not None
            else None,
            completed_at=datetime.fromisoformat(record["completed_at"])
            if record["completed_at"] is not None
            else None,
            status=EvaluationRunStatus(record["status"]),
        )

    @classmethod
    def from_persistence_records(
        cls,
        records: list[Mapping[str, Any]],
    ) -> list[EvaluationRun]:
        return [
            cls.from_persistence_record(record)
            for record in records
        ]
