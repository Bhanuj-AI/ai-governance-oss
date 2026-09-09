from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from ai_governance.domain.evaluation_result import (
    EvaluationArtifact,
    EvaluationResult,
    EvaluationSampleResult,
)
from ai_governance.evaluation.evaluation_request import EvaluationRequest
from ai_governance.providers.provider_descriptor import ProviderDescriptor


@dataclass(frozen=True)
class BatchEvaluationResult:
    """Generic provider response for one invocation covering many samples."""

    sample_results: tuple[EvaluationSampleResult, ...]
    artifacts: tuple[EvaluationArtifact, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.sample_results:
            raise ValueError("BatchEvaluationResult requires at least one sample result.")
        sample_ids = [result.sample_id for result in self.sample_results]
        if len(sample_ids) != len(set(sample_ids)):
            raise ValueError("BatchEvaluationResult sample IDs must be unique.")
        object.__setattr__(self, "sample_results", tuple(self.sample_results))
        object.__setattr__(self, "artifacts", tuple(self.artifacts))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class EvaluationWorkloadEstimate:
    """Provider-declared preflight volume for one candidate repetition.

    The control plane cannot safely infer a batch provider's sample count or
    model-call count from its dataset record count. Providers that know their
    bounded work can expose it through this generic value without coupling the
    experiment domain to provider-specific configuration fields.
    """

    runner_invocation_count: int
    expected_sample_result_count: int | None

    def __post_init__(self) -> None:
        if self.runner_invocation_count < 0:
            raise ValueError("runner_invocation_count must not be negative.")
        if (
            self.expected_sample_result_count is not None
            and self.expected_sample_result_count < 0
        ):
            raise ValueError("expected_sample_result_count must not be negative.")


class EvaluationWorkloadEstimator(Protocol):
    """Optional provider SPI for an exact, bounded preflight estimate."""

    def estimate_workload(
        self,
        provider_config: Mapping[str, Any],
    ) -> EvaluationWorkloadEstimate:
        """Describe one candidate repetition without executing the provider."""
        ...


class EvaluationExecutionDeadlineProvider(Protocol):
    """Optional SPI for the maximum duration of one provider invocation."""

    def execution_timeout_seconds(
        self,
        provider_config: Mapping[str, Any],
    ) -> int | None:
        """Return a validated provider-call timeout, or ``None`` if unbounded."""
        ...


class EvaluationRunConfigurationValidator(Protocol):
    """Optional SPI for pre-dispatch validation of a fully resolved run."""

    def validate_run_configuration(
        self,
        provider_config: Mapping[str, Any],
    ) -> None:
        """Reject unsupported model, transport, task, or scaffold combinations."""
        ...


class EvaluationProvider(Protocol):
    """
    Provider contract for evaluation frameworks.

    EvaluationProvider defines the integration boundary between the
    AI Governance Control Plane Evaluation Plane and external evaluation engines.

    Supported implementations may include:

    - TruLens
    - Phoenix
    - DeepEval
    - RAGAS
    - Snowflake Cortex Judge
    - Custom evaluation engines

    Implementations are responsible for converting an EvaluationRequest into
    one or more evaluation metrics and returning an EvaluationResult.

    Architectural Boundary:

        WorkflowExecution
                ↓
        EvaluationDatasetBuilder
                ↓
        EvaluationRequest
                ↓
        EvaluationProvider
                ↓
        EvaluationResult

    Design Goals:

    - Vendor independence
    - Provider pluggability
    - Consistent evaluation contract
    - Future extensibility

    EvaluationService and EvaluationWorker should depend only on this
    contract and never on concrete evaluation implementations.

    Example:
        class ExampleProvider:
            @property
            def descriptor(self) -> ProviderDescriptor:
                return ProviderDescriptor(...)

            def evaluate(
                self,
                request: EvaluationRequest,
            ) -> EvaluationResult:
                return EvaluationResult(...)
    """

    @property
    def descriptor(self) -> ProviderDescriptor:
        """
        Return a secret-free provider descriptor for capability discovery.
        """
        ...

    def evaluate(self, request: EvaluationRequest) -> EvaluationResult:
        """
        Evaluate a canonical evaluation request and return the resulting
        evaluation metrics.

        Args:
            request: Provider-agnostic evaluation request.

        Returns:
            EvaluationResult containing evaluation metrics and metadata.
        """
        ...
