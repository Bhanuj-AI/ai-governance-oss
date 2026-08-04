from __future__ import annotations

from typing import Protocol

from kavach.domain.evaluation_result import EvaluationResult
from kavach.evaluation.evaluation_request import EvaluationRequest
from kavach.providers.provider_descriptor import ProviderDescriptor


class EvaluationProvider(Protocol):
    """
    Provider contract for evaluation frameworks.

    EvaluationProvider defines the integration boundary between the
    Kavach Evaluation Plane and external evaluation engines.

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
