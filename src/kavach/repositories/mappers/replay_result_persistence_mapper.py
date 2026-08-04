from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from kavach.domain.replay import (
    ReplayComparisonSummary,
    ReplayDriftSummary,
    ReplayResult,
)


class ReplayResultPersistenceMapper:
    @staticmethod
    def to_persistence_record(result: ReplayResult) -> dict[str, Any]:
        return {
            "result_id": result.result_id,
            "replay_id": result.replay_id,
            "source_execution_id": result.source_execution_id,
            "replay_execution_id": result.replay_execution_id,
            "baseline_evaluation_id": result.baseline_evaluation_id,
            "replay_evaluation_id": result.replay_evaluation_id,
            "comparison_id": result.comparison_id,
            "drift_id": result.drift_id,
            "baseline_strategy": result.baseline_strategy,
            "comparison_summary_json": json.dumps(result.comparison_summary.__dict__, sort_keys=True),
            "drift_summary_json": json.dumps({
                "severity": result.drift_summary.severity,
                "changed_metrics": list(result.drift_summary.changed_metrics),
                "new_metrics": list(result.drift_summary.new_metrics),
                "removed_metrics": list(result.drift_summary.removed_metrics),
                "analyzer_version": result.drift_summary.analyzer_version,
                "threshold_policy": dict(result.drift_summary.threshold_policy),
            }, sort_keys=True),
            "organization_id": result.organization_id,
            "project_id": result.project_id,
            "created_at": result.created_at.isoformat(),
            "metadata_json": json.dumps(dict(result.metadata), sort_keys=True),
        }

    @staticmethod
    def from_persistence_record(record: Mapping[str, Any]) -> ReplayResult:
        comparison = json.loads(str(record["comparison_summary_json"]))
        drift = json.loads(str(record["drift_summary_json"]))
        return ReplayResult(
            result_id=str(record["result_id"]), replay_id=str(record["replay_id"]),
            source_execution_id=str(record["source_execution_id"]),
            replay_execution_id=str(record["replay_execution_id"]),
            baseline_evaluation_id=str(record["baseline_evaluation_id"]),
            replay_evaluation_id=str(record["replay_evaluation_id"]),
            comparison_id=str(record["comparison_id"]), drift_id=str(record["drift_id"]),
            baseline_strategy=str(record["baseline_strategy"]),
            comparison_summary=ReplayComparisonSummary(**comparison),
            drift_summary=ReplayDriftSummary(
                severity=drift["severity"], changed_metrics=tuple(drift["changed_metrics"]),
                new_metrics=tuple(drift["new_metrics"]), removed_metrics=tuple(drift["removed_metrics"]),
                analyzer_version=drift["analyzer_version"], threshold_policy=drift["threshold_policy"],
            ),
            organization_id=str(record["organization_id"]), project_id=str(record["project_id"]),
            created_at=datetime.fromisoformat(str(record["created_at"])),
            metadata=json.loads(str(record["metadata_json"])),
        )
