"""Runnable worker runtime for durable Replay execution and evaluation jobs."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
from uuid import uuid4
from collections.abc import Callable
from time import sleep

from ai_governance.domain.jobs import Job, JobResult, JobStatus, JobType
from ai_governance.domain.replay import ReplayStatus
from ai_governance.events import EventPublisher
from ai_governance.plugins import create_plugin_registry
from ai_governance.services.async_job_handlers import EvaluationJobHandler, ExperimentJobHandler
from ai_governance.services.job_executor import JobExecutor
from ai_governance.services.replay_application_service import ReplayApplicationService
from ai_governance.services.replay_execution import (
    HistoricalReplayExecutionAdapter,
    ReplayExecutionAdapterRegistry,
    ReplayJobHandler,
)
from ai_governance.services.replay_evaluation import ReplayEvaluationJobHandler
from ai_governance.tenancy.domain import TenantContext
from ai_governance.workers.job_worker import JobWorker

LOGGER = logging.getLogger(__name__)


class _AutoEvaluationReplayHandler:
    """Execute a replay then idempotently submit its evaluation work.

    The underlying ``ReplayJobHandler`` remains the registered execution
    handler.  This small runtime decorator adds the cross-job handoff only
    after the produced execution and source lineage have been committed.
    """

    def __init__(
        self,
        execution_handler: ReplayJobHandler,
        replays,
        application_service: ReplayApplicationService,
        evaluation_provider: str,
    ) -> None:
        self._execution_handler = execution_handler
        self._replays = replays
        self._application_service = application_service
        self._evaluation_provider = evaluation_provider

    def handle(self, job: Job) -> JobResult:
        outcome = self._execution_handler.handle(job)
        if outcome.status is not JobStatus.SUCCEEDED:
            return outcome
        context = _tenant_context(job)
        replay_id = str(job.input_refs["replay_id"])
        replay = self._replays.get(
            replay_id, context.organization_id, context.project_id or ""
        )
        if replay is None:
            return JobResult(job.job_id, JobStatus.FAILED, None, "Replay disappeared.")
        if replay.status is ReplayStatus.EXECUTION_COMPLETED:
            # The application service reuses the stable replay-evaluation
            # idempotency key, so a redelivered execution job cannot create a
            # second evaluation job or a second produced execution identity.
            self._application_service.evaluate(
                replay.replay_id,
                context,
                evaluation_provider=str(
                    replay.metadata.get("evaluation_provider")
                    or self._evaluation_provider
                ),
            )
        return outcome


class ReplayWorkerRuntime:
    """Own a ``JobWorker`` configured for both Replay job types.

    ``run_forever`` is deliberately process-neutral: invoke it in the API
    lifespan for all-in-one development, or run ``python -m
    ai_governance.workers.replay_worker_runtime`` as a separate Docker service.  Job
    leases make either topology safe against duplicate claims.
    """

    def __init__(self, worker: JobWorker, poll_seconds: float = 1.0) -> None:
        self._worker = worker
        self._poll_seconds = poll_seconds
        self._stopping = False

    def stop(self, *_args) -> None:
        """Ask the loop to finish after its current handler boundary."""
        self._stopping = True

    def run_once(self) -> Job | None:
        """Claim and execute one durable job."""
        return self._worker.run_once()

    def run_forever(self) -> None:
        """Poll until interrupted; expired leases are recovered by ``JobWorker``."""
        while not self._stopping:
            try:
                if self.run_once() is None:
                    sleep(self._poll_seconds)
            except Exception:
                LOGGER.exception("Replay job worker iteration failed")
                sleep(self._poll_seconds)


def create_replay_worker_runtime(
    *,
    worker_id: str | None = None,
    poll_seconds: float | None = None,
    lease_seconds: int | None = None,
    evaluation_provider: str | None = None,
    extra_adapters: Callable[[ReplayExecutionAdapterRegistry], None] | None = None,
    event_publisher: EventPublisher | None = None,
) -> ReplayWorkerRuntime:
    """Build runtime dependencies using the same durable factories as the API."""
    from ai_governance.api.dependencies.evaluation import get_evaluation_api_service
    from ai_governance.api.dependencies.provider_installations import (
        get_provider_installation_service,
    )
    from ai_governance.api.dependencies.providers import get_provider_registry
    from ai_governance.api.dependencies.runtime_connections import (
        get_runtime_connection_service,
    )
    from ai_governance.api.dependencies.repositories import (
        get_dataset_repository,
        get_evaluation_repository,
        get_evaluation_run_repository,
        get_experiment_candidate_repository,
        get_experiment_repository,
        get_job_repository,
        get_leaderboard_repository,
        get_model_repository,
        get_prompt_repository,
        get_replay_repository,
        get_replay_result_repository,
    )
    from ai_governance.api.dependencies.replay import get_replay_source_resolver
    from ai_governance.api.dependencies.settings_control import (
        get_configuration_service,
        get_provider_installation_repository,
        get_runtime_connection_repository,
    )
    from ai_governance.services.evaluation_api_service import EvaluationApiService
    from ai_governance.services.experiment_api_service import ExperimentApiService
    from ai_governance.services.job_api_service import JobApiService
    from ai_governance.services.candidate_execution_runtime import (
        CandidateExecutionRuntime,
        ModelRuntimeAdapterRegistry,
        OpenAIModelRuntimeAdapter,
    )
    from ai_governance.services.dataset_item_reader import S3DatasetItemReader
    from ai_governance.datasets import dataset_object_store_from_environment

    provider_registry = get_provider_registry()
    configuration_service = get_configuration_service(
        request=None,
        event_publisher=None,
    )
    provider_installation_service = get_provider_installation_service(
        repository=get_provider_installation_repository(),
        provider_registry=provider_registry,
    )
    runtime_connection_service = get_runtime_connection_service(
        repository=get_runtime_connection_repository(),
        configuration_service=configuration_service,
    )

    job_repository = get_job_repository()
    replay_repository = get_replay_repository()
    results = get_replay_result_repository()
    source_store = get_replay_source_resolver()
    job_service = JobApiService(job_repository, event_publisher=event_publisher)
    application = ReplayApplicationService(
        replay_repository=replay_repository,
        source_resolver=source_store,
        job_service=job_service,
        result_repository=results,
        provider_installation_service=provider_installation_service,
    )
    evaluations: EvaluationApiService = get_evaluation_api_service(
        provider_registry=provider_registry,
        provider_installation_service=provider_installation_service,
        evaluation_repository=get_evaluation_repository(),
        ontology_event_publisher=None,
        configuration_service=None,
    )
    experiments = ExperimentApiService(
        experiment_repository=get_experiment_repository(),
        candidate_repository=get_experiment_candidate_repository(),
        evaluation_run_repository=get_evaluation_run_repository(),
        evaluation_repository=get_evaluation_repository(),
        leaderboard_repository=get_leaderboard_repository(),
        prompt_repository=get_prompt_repository(),
        model_repository=get_model_repository(),
        dataset_repository=get_dataset_repository(),
        provider_registry=provider_registry,
        provider_installation_service=provider_installation_service,
        runtime_connection_service=runtime_connection_service,
        candidate_execution_runtime=CandidateExecutionRuntime(
            prompt_repository=get_prompt_repository(),
            model_repository=get_model_repository(),
            dataset_repository=get_dataset_repository(),
            runtime_connection_service=runtime_connection_service,
            dataset_item_reader=S3DatasetItemReader(dataset_object_store_from_environment()),
            adapter_registry=ModelRuntimeAdapterRegistry((OpenAIModelRuntimeAdapter(),)),
            execution_store=source_store,
            event_publisher=event_publisher,
        ),
    )
    registry = ReplayExecutionAdapterRegistry()
    registry.register(HistoricalReplayExecutionAdapter())
    if extra_adapters is not None:
        extra_adapters(registry)
    execution_handler = ReplayJobHandler(
        replay_repository=replay_repository,
        source_resolver=source_store,
        execution_store=source_store,
        adapter_registry=registry,
        execution_id_generator=lambda: uuid4().hex,
        event_publisher=event_publisher,
    )
    executor = JobExecutor(
        {
            JobType.EVALUATION: EvaluationJobHandler(evaluations),
            JobType.EXPERIMENT: ExperimentJobHandler(experiments),
            JobType.REPLAY_EXECUTION: _AutoEvaluationReplayHandler(
                execution_handler,
                replay_repository,
                application,
                evaluation_provider
                or os.getenv("AI_GOVERNANCE_REPLAY_EVALUATION_PROVIDER", "trulens"),
            ),
            JobType.REPLAY_EVALUATION: ReplayEvaluationJobHandler(
                replay_repository=replay_repository,
                result_repository=results,
                source_resolver=source_store,
            evaluation_api_service=evaluations,
            provider_installation_service=provider_installation_service,
            ),
        }
    )
    return ReplayWorkerRuntime(
        JobWorker(
            worker_id=worker_id
            or os.getenv("AI_GOVERNANCE_WORKER_ID", f"replay-worker-{socket.gethostname()}"),
            repository=job_repository,
            executor=executor,
            lease_seconds=lease_seconds
            or int(os.getenv("AI_GOVERNANCE_WORKER_LEASE_SECONDS", "300")),
            job_types=(
                JobType.EVALUATION,
                JobType.EXPERIMENT,
                JobType.REPLAY_EXECUTION,
                JobType.REPLAY_EVALUATION,
            ),
            job_operations={
                JobType.EVALUATION: ("evaluation.submit_async",),
                JobType.EXPERIMENT: ("experiment.run_async",),
            },
            event_publisher=event_publisher,
        ),
        poll_seconds=poll_seconds
        or float(os.getenv("AI_GOVERNANCE_WORKER_POLL_SECONDS", "1")),
    )


def _tenant_context(job: Job) -> TenantContext:
    if job.execution_context is None:
        raise ValueError("Replay job is missing its tenant execution context.")
    context = job.execution_context
    return TenantContext(
        context.organization_id,
        context.project_id,
        context.actor_id,
        context.submitted_request_id,
        context.correlation_id,
    )


def main() -> None:
    """Start the standalone Replay worker process."""
    parser = argparse.ArgumentParser(description="Run the AI Governance Control Plane job worker")
    parser.add_argument("--once", action="store_true", help="Process at most one job")
    arguments = parser.parse_args()
    extension_registry = create_plugin_registry()
    extension_registry.start()
    try:
        runtime = create_replay_worker_runtime(
            event_publisher=extension_registry.events
        )
        signal.signal(signal.SIGINT, runtime.stop)
        signal.signal(signal.SIGTERM, runtime.stop)
        if arguments.once:
            runtime.run_once()
        else:
            runtime.run_forever()
    finally:
        extension_registry.stop()


if __name__ == "__main__":
    main()
