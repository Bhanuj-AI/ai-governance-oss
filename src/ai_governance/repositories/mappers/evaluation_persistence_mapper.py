from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

from ai_governance.domain.evaluation_result import (
    EvaluationArtifact,
    EvaluationMetric,
    EvaluationResult,
)


class EvaluationPersistenceMapper:
    """
    Maps EvaluationResult domain objects to and from their persistence
    representation.

    Repository implementations are responsible for executing SQL.
    This mapper owns the translation between the domain model and the
    flattened persistence records.
    """

    @staticmethod
    def to_persistence_records(
        result: EvaluationResult,
    ) -> list[dict[str, Any]]:
        """
        Convert an EvaluationResult into one persistence record per metric.
        """

        metadata_json = json.dumps(result.metadata)
        provider_metadata_json = json.dumps(dict(result.provider_metadata))
        provider_descriptor_snapshot_json = (
            json.dumps(result.provider_descriptor_snapshot)
            if result.provider_descriptor_snapshot is not None
            else None
        )
        artifacts_json = json.dumps(
            [
                {
                    "artifact_type": artifact.artifact_type,
                    "uri": artifact.uri,
                    "payload": artifact.payload,
                    "metadata": dict(artifact.metadata),
                }
                for artifact in result.artifacts
            ]
        )
        created_at = result.created_at.isoformat()

        return [
            {
                "evaluation_id": result.evaluation_id,
                "execution_id": result.execution_id,
                "evaluator_type": result.evaluator_type,
                "evaluator_version": result.evaluator_version,
                "metric_name": metric.metric_name,
                "metric_score": metric.metric_value,
                "explanation": metric.explanation,
                "metadata_json": metadata_json,
                "provider_metadata_json": provider_metadata_json,
                "provider_descriptor_snapshot_json": (
                    provider_descriptor_snapshot_json
                ),
                "artifacts_json": artifacts_json,
                "created_at": created_at,
                "organization_id": result.organization_id,
                "project_id": result.project_id,
            }
            for metric in result.metrics
        ]

    @staticmethod
    def from_persistence_records(
        records: Iterable[Mapping[str, Any]],
    ) -> list[EvaluationResult]:
        """
        Convert persistence records into EvaluationResult objects.
        """

        grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)

        for record in records:
            grouped[record["evaluation_id"]].append(record)

        results: list[EvaluationResult] = []

        for evaluation_records in grouped.values():
            first = evaluation_records[0]

            metrics = [
                EvaluationMetric(
                    metric_name=record["metric_name"],
                    metric_value=record["metric_score"],
                    explanation=record["explanation"],
                )
                for record in evaluation_records
            ]

            results.append(
                EvaluationResult(
                    evaluation_id=first["evaluation_id"],
                    execution_id=first["execution_id"],
                    evaluator_type=first["evaluator_type"],
                    evaluator_version=first["evaluator_version"],
                    metrics=metrics,
                    metadata=json.loads(first["metadata_json"] or "{}"),
                    artifacts=[
                        EvaluationArtifact(
                            artifact_type=artifact["artifact_type"],
                            uri=artifact.get("uri"),
                            payload=artifact.get("payload"),
                            metadata=artifact.get("metadata", {}),
                        )
                        for artifact in json.loads(
                            _record_value(first, "artifacts_json", "[]") or "[]"
                        )
                    ],
                    provider_metadata=json.loads(
                        _record_value(
                            first,
                            "provider_metadata_json",
                            first["metadata_json"],
                        )
                        or "{}"
                    ),
                    provider_descriptor_snapshot=json.loads(descriptor_snapshot_json)
                    if (
                        descriptor_snapshot_json := _record_value(
                            first,
                            "provider_descriptor_snapshot_json",
                            None,
                        )
                    )
                    is not None
                    else None,
                    created_at=datetime.fromisoformat(created_at)
                    if (
                        created_at := _record_value(
                            first,
                            "created_at",
                            None,
                        )
                    )
                    is not None
                    else datetime.now(UTC),
                    organization_id=_record_value(
                        first, "organization_id", "org_default"
                    ),
                    project_id=_record_value(first, "project_id", "project_default"),
                )
            )

        return results


def _record_value(
    record: Mapping[str, Any],
    field_name: str,
    default: Any,
) -> Any:
    try:
        return record[field_name]
    except (KeyError, IndexError):
        return default
