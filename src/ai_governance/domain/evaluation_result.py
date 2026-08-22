from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class EvaluationMetric:
    """
    Single scored metric returned by an evaluation provider.

    Example:
        EvaluationMetric(
            metric_name="answer_relevance",
            metric_value=0.92,
            explanation="The answer addresses the requested topic.",
        )
    """

    metric_name: str
    metric_value: float
    explanation: str | None = None


@dataclass
class EvaluationArtifact:
    """
    Optional provider output linked to an evaluation result.

    Artifacts can point to external files, traces, reports, or embedded
    payloads. Use metadata for small descriptive fields and payload for
    provider-specific structured content.

    Example:
        EvaluationArtifact(
            artifact_type="trace",
            uri="s3://bucket/evaluations/trace.json",
            metadata={"format": "json"},
        )
    """

    artifact_type: str
    uri: str | None = None
    payload: Mapping[str, Any] | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationResult:
    """
    Provider-agnostic result returned from the evaluation boundary.

    EvaluationResult stores the public evaluation identity, provider identity,
    metrics, optional artifacts, and provider metadata. New provider fields are
    excluded from dataclass equality so older tests and callers comparing core
    metric results continue to behave predictably.

    Example:
        EvaluationResult(
            evaluation_id="eval_123",
            execution_id="exec_123",
            evaluator_type="example_provider",
            evaluator_version="1.0",
            metrics=[
                EvaluationMetric("answer_relevance", 0.92),
            ],
            provider_descriptor_snapshot=snapshot.to_dict(),
        )
    """

    evaluation_id: str

    execution_id: str

    evaluator_type: str
    evaluator_version: str

    metrics: list[EvaluationMetric]

    metadata: dict[str, Any] = field(default_factory=dict)
    artifacts: list[EvaluationArtifact] = field(
        default_factory=list,
        compare=False,
    )
    provider_metadata: Mapping[str, Any] = field(
        default_factory=dict,
        compare=False,
    )
    provider_descriptor_snapshot: Mapping[str, Any] | None = field(
        default=None,
        compare=False,
    )
    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC),
        compare=False,
    )
    organization_id: str = field(default="org_default", compare=False)
    project_id: str = field(default="project_default", compare=False)

    def __post_init__(self) -> None:
        """
        Preserve compatibility between metadata and provider_metadata fields.
        """
        if not self.provider_metadata and self.metadata:
            self.provider_metadata = dict(self.metadata)
        elif self.provider_metadata and not self.metadata:
            self.metadata = dict(self.provider_metadata)

        if self.provider_descriptor_snapshot is not None:
            self.provider_descriptor_snapshot = dict(self.provider_descriptor_snapshot)

    @property
    def provider_name(self) -> str:
        """
        Alias for evaluator_type.
        """
        return self.evaluator_type

    @property
    def provider_version(self) -> str:
        """
        Alias for evaluator_version.
        """
        return self.evaluator_version
