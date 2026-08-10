from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from ai_governance.domain.evaluation_dataset import EvaluationDataset
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.evaluation.evaluation_metrics import EvaluationMetricSpec


@dataclass(frozen=True)
class EvaluationRequest:
    """
    Canonical input passed from AI Governance Control Plane orchestration into a provider adapter.

    EvaluationRequest keeps provider implementations independent from workflow
    and persistence internals. Adapters receive the original execution, the
    normalized dataset text, requested metric specs, provider-specific runtime
    config, and the provider descriptor snapshot created by the service.

    Example:
        request = EvaluationRequest(
            execution=execution,
            dataset=dataset,
            metric_specs=(EvaluationMetricSpec("answer_relevance"),),
            provider_config={"model": "judge-model"},
            provider_descriptor_snapshot=snapshot.to_dict(),
        )

        provider.evaluate(request)
    """

    execution: WorkflowExecution
    dataset: EvaluationDataset
    metric_specs: Sequence[EvaluationMetricSpec] = field(
        default_factory=tuple
    )
    provider_config: Mapping[str, Any] = field(default_factory=dict)
    provider_descriptor_snapshot: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        """
        Freeze sequence and mapping inputs after construction.
        """
        object.__setattr__(self, "metric_specs", tuple(self.metric_specs))
        object.__setattr__(
            self,
            "provider_config",
            MappingProxyType(dict(self.provider_config)),
        )
        if self.provider_descriptor_snapshot is not None:
            object.__setattr__(
                self,
                "provider_descriptor_snapshot",
                MappingProxyType(dict(self.provider_descriptor_snapshot)),
            )

    @property
    def execution_id(self) -> str:
        """
        Compatibility shortcut for dataset.execution_id.
        """
        return self.dataset.execution_id

    @property
    def input_text(self) -> str:
        """
        Compatibility shortcut for dataset.input_text.
        """
        return self.dataset.input_text

    @property
    def context_text(self) -> str:
        """
        Compatibility shortcut for dataset.context_text.
        """
        return self.dataset.context_text

    @property
    def output_text(self) -> str:
        """
        Compatibility shortcut for dataset.output_text.
        """
        return self.dataset.output_text

    @property
    def metadata(self) -> dict[str, Any]:
        """
        Compatibility shortcut for dataset.metadata.
        """
        return self.dataset.metadata
