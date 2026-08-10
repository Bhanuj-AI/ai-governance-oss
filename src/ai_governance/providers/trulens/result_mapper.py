from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from ai_governance.domain.evaluation_result import (
    EvaluationArtifact,
    EvaluationMetric,
    EvaluationResult,
)
from ai_governance.evaluation.evaluation_request import EvaluationRequest

_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "token",
)


class TruLensResultMapper:
    """
    Converts TruLens adapter output into AI Governance Control Plane-owned result objects.
    """

    def to_evaluation_result(
        self,
        request: EvaluationRequest,
        raw_result: Mapping[str, Any],
        provider_metadata: Mapping[str, Any],
    ) -> EvaluationResult:
        metrics = [
            EvaluationMetric(
                metric_name=record["name"],
                metric_value=float(record["value"]),
                explanation=record.get("explanation"),
            )
            for record in raw_result.get("metrics", [])
        ]

        artifacts = []
        timings = raw_result.get("timings")
        if timings:
            artifacts.append(
                EvaluationArtifact(
                    artifact_type="trulens_timings",
                    payload={"timings": timings},
                    metadata={"provider": "trulens"},
                )
            )

        safe_metadata = self.safe_metadata(provider_metadata)

        return EvaluationResult(
            evaluation_id=str(uuid4()),
            execution_id=request.execution_id,
            evaluator_type="trulens",
            evaluator_version=str(safe_metadata.get("provider_version", "")),
            metrics=metrics,
            metadata=dict(safe_metadata),
            artifacts=artifacts,
            provider_metadata=safe_metadata,
            provider_descriptor_snapshot=request.provider_descriptor_snapshot,
            created_at=datetime.now(UTC),
        )

    def safe_metadata(
        self,
        metadata: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            key: value
            for key, value in metadata.items()
            if not self._is_sensitive_key(key)
        }

    @staticmethod
    def _is_sensitive_key(
        key: str,
    ) -> bool:
        normalized = key.lower()
        return any(part in normalized for part in _SENSITIVE_KEY_PARTS)
