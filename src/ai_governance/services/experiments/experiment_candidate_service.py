from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from ai_governance.domain.datasets import DatasetStatus
from ai_governance.domain.experiments import (
    CandidateComparison,
    ExperimentCandidate,
    ExperimentStatus,
)
from ai_governance.domain.models import ModelStatus
from ai_governance.domain.prompts import PromptStatus
from ai_governance.ontology.synchronization import (
    OntologySyncEventPublisherProtocol,
)
from ai_governance.repositories.dataset_repository import DatasetRepository
from ai_governance.repositories.experiment_candidate_repository import (
    ExperimentCandidateRepository,
)
from ai_governance.repositories.experiment_repository import ExperimentRepository
from ai_governance.repositories.model_repository import ModelRepository
from ai_governance.repositories.prompt_repository import PromptRepository


class ExperimentCandidateNotFoundError(Exception):
    """
    Raised when a candidate operation references an unknown candidate.
    """


class ExperimentCandidateReferenceError(Exception):
    """
    Raised when a candidate references an invalid experiment or registry asset.
    """


class ExperimentCandidateLifecycleError(Exception):
    """
    Raised when a candidate change is not allowed by experiment state.
    """


class ExperimentCandidateService:
    """
    Application service for experiment candidate governance.

    The service validates experiment ownership and immutable registry
    references before a candidate is persisted for evaluation.
    """

    def __init__(
        self,
        candidate_repository: ExperimentCandidateRepository,
        experiment_repository: ExperimentRepository,
        prompt_repository: PromptRepository,
        model_repository: ModelRepository,
        dataset_repository: DatasetRepository,
        id_generator: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
        ontology_event_publisher: OntologySyncEventPublisherProtocol
        | None = None,
    ) -> None:
        self._candidate_repository = candidate_repository
        self._experiment_repository = experiment_repository
        self._prompt_repository = prompt_repository
        self._model_repository = model_repository
        self._dataset_repository = dataset_repository
        self._id_generator = id_generator or (lambda: str(uuid4()))
        self._clock = clock or (lambda: datetime.now(UTC))
        self._ontology_event_publisher = ontology_event_publisher

    def create_candidate(
        self,
        experiment_id: str,
        name: str,
        prompt_id: str,
        prompt_version: str,
        model_id: str,
        model_version: str,
        dataset_id: str,
        dataset_version: str,
        evaluation_provider: str,
        temperature: float,
        top_p: float,
        max_tokens: int,
        metadata: dict[str, Any] | None = None,
    ) -> ExperimentCandidate:
        """
        Create and register a candidate for a draft experiment.
        """

        candidate = ExperimentCandidate(
            candidate_id=self._id_generator(),
            experiment_id=experiment_id,
            name=name,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            model_id=model_id,
            model_version=model_version,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            evaluation_provider=evaluation_provider,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            metadata=metadata or {},
            created_at=self._clock(),
        )

        return self.register_candidate(candidate)

    def register_candidate(
        self,
        candidate: ExperimentCandidate,
    ) -> ExperimentCandidate:
        """
        Persist a candidate after validating experiment and asset references.
        """

        experiment = self._get_experiment(candidate.experiment_id)

        if experiment.status != ExperimentStatus.DRAFT:
            raise ExperimentCandidateLifecycleError(
                "Candidates can only be added to draft experiments."
            )

        self.validate_candidate_references(candidate)
        self._candidate_repository.save(candidate)
        self._publish_candidate_event("CandidateCreated", candidate)

        return candidate

    def get_candidate(
        self,
        candidate_id: str,
    ) -> ExperimentCandidate:
        """
        Retrieve one candidate by ID.
        """

        candidate = self._candidate_repository.find_by_id(candidate_id)

        if candidate is None:
            raise ExperimentCandidateNotFoundError(
                f"Candidate '{candidate_id}' does not exist."
            )

        return candidate

    def list_experiment_candidates(
        self,
        experiment_id: str,
    ) -> list[ExperimentCandidate]:
        """
        Return every candidate belonging to one experiment.
        """

        self._get_experiment(experiment_id)

        return self._candidate_repository.find_by_experiment_id(
            experiment_id
        )

    def compare_candidate_configuration(
        self,
        baseline_candidate_id: str,
        candidate_candidate_id: str,
    ) -> CandidateComparison:
        """
        Compare two candidate configurations before evaluation results.
        """

        baseline = self.get_candidate(baseline_candidate_id)
        candidate = self.get_candidate(candidate_candidate_id)

        return CandidateComparison(
            baseline_candidate_id=baseline.candidate_id,
            candidate_candidate_id=candidate.candidate_id,
            prompt_id_changed=baseline.prompt_id != candidate.prompt_id,
            prompt_version_changed=(
                baseline.prompt_version != candidate.prompt_version
            ),
            model_id_changed=baseline.model_id != candidate.model_id,
            model_version_changed=(
                baseline.model_version != candidate.model_version
            ),
            dataset_id_changed=baseline.dataset_id != candidate.dataset_id,
            dataset_version_changed=(
                baseline.dataset_version != candidate.dataset_version
            ),
            evaluation_provider_changed=(
                baseline.evaluation_provider
                != candidate.evaluation_provider
            ),
            temperature_changed=(
                baseline.temperature != candidate.temperature
            ),
            top_p_changed=baseline.top_p != candidate.top_p,
            max_tokens_changed=(
                baseline.max_tokens != candidate.max_tokens
            ),
            metadata_changed=baseline.metadata != candidate.metadata,
        )

    def validate_candidate_references(
        self,
        candidate: ExperimentCandidate,
    ) -> None:
        """
        Ensure the candidate references governed assets that still qualify
        for experiment execution.
        """

        prompt = self._prompt_repository.find_by_id(candidate.prompt_id)
        if prompt is None or prompt.version != candidate.prompt_version:
            raise ExperimentCandidateReferenceError(
                "Candidate references an unknown prompt version."
            )
        if prompt.status == PromptStatus.ARCHIVED:
            raise ExperimentCandidateReferenceError(
                "Candidate references an archived prompt."
            )

        model = self._model_repository.find_by_id(candidate.model_id)
        if model is None or model.version != candidate.model_version:
            raise ExperimentCandidateReferenceError(
                "Candidate references an unknown model version."
            )
        if model.status == ModelStatus.ARCHIVED:
            raise ExperimentCandidateReferenceError(
                "Candidate references an archived model."
            )

        dataset = self._dataset_repository.find_by_id(candidate.dataset_id)
        if (
            dataset is None
            or dataset.version != candidate.dataset_version
        ):
            raise ExperimentCandidateReferenceError(
                "Candidate references an unknown dataset version."
            )
        if dataset.status == DatasetStatus.ARCHIVED:
            raise ExperimentCandidateReferenceError(
                "Candidate references an archived dataset."
            )

    def _get_experiment(
        self,
        experiment_id: str,
    ):
        experiment = self._experiment_repository.find_by_id(experiment_id)

        if experiment is None:
            raise ExperimentCandidateReferenceError(
                f"Experiment '{experiment_id}' does not exist."
            )

        return experiment

    def _publish_candidate_event(
        self,
        event_type: str,
        candidate: ExperimentCandidate,
    ) -> None:
        if self._ontology_event_publisher is None:
            return
        self._ontology_event_publisher.publish_entity_event(
            event_type,
            entity_type="Candidate",
            entity_id=candidate.candidate_id,
            scope_identifier="experiment_service",
            payload={
                "candidate_id": candidate.candidate_id,
                "experiment_id": candidate.experiment_id,
                "prompt_id": candidate.prompt_id,
                "model_id": candidate.model_id,
                "dataset_id": candidate.dataset_id,
            },
        )
