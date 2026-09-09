from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from ai_governance.domain.experiments import (
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
            "failure_reason": run.failure_reason,
            "total_item_count": run.total_item_count,
            "completed_item_count": run.completed_item_count,
            "evaluated_item_count": run.evaluated_item_count,
            "runner_provenance_json": json.dumps(run.runner_provenance)
            if run.runner_provenance is not None
            else None,
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
            failure_reason=record["failure_reason"],
            total_item_count=record["total_item_count"],
            completed_item_count=record["completed_item_count"] or 0,
            evaluated_item_count=record["evaluated_item_count"] or 0,
            runner_provenance=json.loads(_record_value(record, "runner_provenance_json"))
            if _record_value(record, "runner_provenance_json")
            else None,
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


def _record_value(record: Mapping[str, Any], key: str) -> Any:
    try:
        return record[key]
    except (IndexError, KeyError):
        return None
