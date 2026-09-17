"""Runnable durable worker for ontology projection events."""

from __future__ import annotations

import signal
import socket
from threading import Event


class OntologySyncWorkerRuntime:
    def __init__(self, worker) -> None:
        self._worker = worker
        self._stop_event = Event()

    def stop(self, *_args) -> None:
        self._stop_event.set()

    def run_forever(self) -> None:
        self._worker.run_forever(self._stop_event)


def create_ontology_sync_worker_runtime(*, worker_id: str | None = None):
    """Build a projector from the same repository dependencies as the API."""
    from ai_governance.api.dependencies.repositories import (
        get_dataset_repository,
        get_evaluation_repository,
        get_evaluation_run_repository,
        get_experiment_candidate_repository,
        get_experiment_repository,
        get_governance_decision_repository,
        get_job_repository,
        get_leaderboard_repository,
        get_model_repository,
        get_ontology_graph_repository,
        get_ontology_sync_event_repository,
        get_policy_administration_repository,
        get_prompt_repository,
    )
    from ai_governance.ontology import EntityType, OntologyService
    from ai_governance.ontology.synchronization import (
        CandidateOntologySynchronizer,
        DatasetOntologySynchronizer,
        DiffBasedOntologyReconciler,
        DiffRepositorySynchronizer,
        EvaluationResultOntologySynchronizer,
        EvaluationRunOntologySynchronizer,
        ExperimentOntologySynchronizer,
        GovernanceDecisionOntologySynchronizer,
        JobOntologySynchronizer,
        LeaderboardOntologySynchronizer,
        ModelOntologySynchronizer,
        OntologySynchronizationWorker,
        PolicyOntologySynchronizer,
        PromptOntologySynchronizer,
    )

    service = OntologyService(get_ontology_graph_repository())
    prompt_repository = get_prompt_repository()
    model_repository = get_model_repository()
    dataset_repository = get_dataset_repository()
    experiment_repository = get_experiment_repository()
    candidate_repository = get_experiment_candidate_repository()
    evaluation_run_repository = get_evaluation_run_repository()
    evaluation_repository = get_evaluation_repository()
    job_repository = get_job_repository()
    leaderboard_repository = get_leaderboard_repository()
    decision_repository = get_governance_decision_repository()
    policy_repository = get_policy_administration_repository()
    specs = (
        (PromptOntologySynchronizer(service, prompt_repository), prompt_repository.find_all, "prompt_registry", EntityType.PROMPT_VERSION.value, lambda item: item.prompt_id),
        (ModelOntologySynchronizer(service, model_repository), model_repository.find_all, "model_registry", EntityType.MODEL_VERSION.value, lambda item: item.model_id),
        (DatasetOntologySynchronizer(service, dataset_repository), dataset_repository.find_all, "dataset_registry", EntityType.DATASET_VERSION.value, lambda item: item.dataset_id),
        (ExperimentOntologySynchronizer(service, experiment_repository), experiment_repository.find_all, "experiment_service", EntityType.EXPERIMENT.value, lambda item: item.experiment_id),
        (CandidateOntologySynchronizer(service, candidate_repository), candidate_repository.find_all, "experiment_candidate_service", EntityType.CANDIDATE.value, lambda item: item.candidate_id),
        (EvaluationRunOntologySynchronizer(service, evaluation_run_repository), evaluation_run_repository.find_all, "evaluation_run_repository", EntityType.EVALUATION_RUN.value, lambda item: item.run_id),
        (LeaderboardOntologySynchronizer(service, leaderboard_repository, evaluation_run_repository), leaderboard_repository.find_all, "leaderboard_repository", EntityType.LEADERBOARD.value, lambda item: item.leaderboard_id),
        (JobOntologySynchronizer(service, job_repository), job_repository.list_jobs, "job_control_plane", EntityType.JOB.value, lambda item: item.job_id),
        (PolicyOntologySynchronizer(service, policy_repository), policy_repository.list_definitions, "policy_administration", EntityType.POLICY.value, lambda item: item.policy_id, policy_repository.get_definition),
        (GovernanceDecisionOntologySynchronizer(service), decision_repository.list, "governance_decisions", EntityType.GOVERNANCE_DECISION.value, lambda item: item.decision_id),
        (EvaluationResultOntologySynchronizer(service, evaluation_repository), lambda: (), "evaluation_repository", EntityType.EVALUATION_RESULT.value, lambda item: item.evaluation_id, evaluation_repository.find_by_evaluation_id),
    )
    synchronizers = tuple(
        DiffRepositorySynchronizer(
            synchronizer=synchronizer,
            list_entities=list_entities,
            primary_entity_resolver=lambda item, resolver=resolver, entity_type=entity_type: (entity_type, resolver(item)),
            projection_source=scope,
            scope_identifier=scope,
            entity_type=entity_type,
            entity_id_resolver=resolver,
            entity_loader=(spec[5] if len(spec) > 5 else None),
        )
        for spec in specs
        for synchronizer, list_entities, scope, entity_type, resolver in (spec[:5],)
    )
    return OntologySyncWorkerRuntime(
        OntologySynchronizationWorker(
            get_ontology_sync_event_repository(),
            DiffBasedOntologyReconciler(service, synchronizers),
            worker_id=worker_id or f"ontology-sync-{socket.gethostname()}",
        )
    )


def main() -> None:
    runtime = create_ontology_sync_worker_runtime()
    signal.signal(signal.SIGINT, runtime.stop)
    signal.signal(signal.SIGTERM, runtime.stop)
    runtime.run_forever()


if __name__ == "__main__":
    main()
