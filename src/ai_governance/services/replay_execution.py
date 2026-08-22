"""Phase 2 execution orchestration for governed workflow replays.

The execution handler is intentionally framework-neutral. It reconstructs a
frozen replay through a registered adapter, persists a *new* workflow
execution, and records immutable source-to-produced lineage. It does not
perform evaluation, comparison, drift analysis, or provider-SDK calls; those
belong to the subsequent replay-evaluation job.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from ai_governance.domain.jobs import Job, JobResult, JobStatus
from ai_governance.domain.replay import (
    ReplayConfiguration,
    ReplayFailure,
    ReplayFailureStage,
    ReplayStatus,
)
from ai_governance.domain.replay.errors import (
    ReplayAdapterConfigurationInvalid,
    ReplayAdapterNotFound,
    ReplayExecutionIdentityConflict,
    ReplayExecutionPersistenceFailed,
    ReplayLineagePersistenceFailed,
    ReplayReconstructionFailed,
)
from ai_governance.domain.workflow_execution import WorkflowExecution
from ai_governance.events import EventPublisher, ResourceLifecycleEvent
from ai_governance.repositories.replay_repository import ReplayRepository
from ai_governance.services.replay_application_service import ReplaySourceResolver
from ai_governance.tenancy.domain import TenantContext


@dataclass(frozen=True)
class ReplayExecutionContext:
    """Immutable inputs supplied to an execution adapter for one job attempt.

    ``new_execution_id`` is reserved by the replay aggregate before adapter
    invocation. Adapters must return that exact identity and should consult the
    cancellation token at safe runtime boundaries. ``metadata`` is an adapter
    extension point; durable lineage is added by the handler after execution.
    """

    replay_id: str
    source_execution_id: str
    new_execution_id: str
    organization_id: str
    project_id: str
    actor_id: str
    request_id: str
    correlation_id: str | None
    attempt: int
    cancellation_token: ReplayCancellationToken
    metadata: dict[str, Any]


class ReplayCancellationToken(Protocol):
    """Small cooperative-cancellation contract exposed to replay adapters."""

    @property
    def is_cancelled(self) -> bool: ...


class ReplayExecutionAdapter(Protocol):
    """Adapter boundary for reconstructing one frozen workflow execution.

    Implementations validate replay-specific runtime requirements before
    running and must return a new ``WorkflowExecution`` with the reserved ID.
    They never persist the execution or mutate the source; those operations are
    kept in ``ReplayJobHandler`` so lineage remains consistent across adapters.
    """

    @property
    def name(self) -> str: ...

    def validate_configuration(
        self, source_execution: WorkflowExecution, configuration: ReplayConfiguration
    ) -> None: ...

    def replay(
        self,
        source_execution: WorkflowExecution,
        configuration: ReplayConfiguration,
        context: ReplayExecutionContext,
    ) -> WorkflowExecution: ...


class ReplayExecutionAdapterRegistry:
    """Named, explicit registry of execution adapters available to workers.

    Names are persisted in ``ReplayConfiguration``. Duplicate registration is
    rejected to avoid deployment-order-dependent replay behavior, while lookup
    failures become structured ``ReplayAdapterNotFound`` errors.
    """

    def __init__(self) -> None:
        self._adapters: dict[str, ReplayExecutionAdapter] = {}

    def register(self, adapter: ReplayExecutionAdapter) -> None:
        """Register one adapter under its stable configuration name."""
        if adapter.name in self._adapters:
            raise ValueError(f"Replay adapter '{adapter.name}' is already registered.")
        self._adapters[adapter.name] = adapter

    def resolve(self, name: str) -> ReplayExecutionAdapter:
        """Return an adapter or raise a replay-specific availability error."""
        try:
            return self._adapters[name]
        except KeyError as error:
            raise ReplayAdapterNotFound(
                f"Replay adapter '{name}' is unavailable."
            ) from error

    def descriptors(self) -> list[dict[str, str]]:
        return [{"name": name} for name in sorted(self._adapters)]


class HistoricalReplayExecutionAdapter:
    """Built-in deterministic adapter for persisted historical evidence.

    It reconstructs a completed execution exclusively from the immutable source
    snapshot and frozen configuration held by the Replay.  Deployments that
    need to call a workflow runtime can register another adapter name instead;
    the worker never resolves mutable workflow versions or live defaults.
    """

    name = "historical"

    def validate_configuration(
        self, source_execution: WorkflowExecution, configuration: ReplayConfiguration
    ) -> None:
        if source_execution.workflow_id != configuration.workflow_id:
            raise ValueError("Source workflow does not match the frozen configuration.")
        if source_execution.workflow_version != configuration.workflow_version:
            raise ValueError("Source workflow version does not match frozen evidence.")

    def replay(
        self,
        source_execution: WorkflowExecution,
        configuration: ReplayConfiguration,
        context: ReplayExecutionContext,
    ) -> WorkflowExecution:
        if context.cancellation_token.is_cancelled:
            raise ReplayReconstructionFailed("Replay cancellation requested.")
        return WorkflowExecution(
            workflow_id=configuration.workflow_id,
            execution_id=context.new_execution_id,
            workflow_name=source_execution.workflow_name,
            workflow_version=configuration.workflow_version,
            execution_status="COMPLETED",
            input=dict(source_execution.input),
            final_state=dict(source_execution.final_state),
            events=[*source_execution.events, {"type": "REPLAY_COMPLETED"}],
            organization_id=context.organization_id,
            project_id=context.project_id,
            execution_adapter=self.name,
            input_snapshot_ref=configuration.input_snapshot_ref,
            state_snapshot_ref=configuration.state_snapshot_ref,
            artifact_refs=list(configuration.artifact_refs),
            prompt_refs=list(configuration.prompt_refs),
            model_refs=list(configuration.model_refs),
            dataset_refs=list(configuration.dataset_refs),
            policy_refs=list(configuration.policy_refs),
            runtime_parameters=dict(configuration.runtime_parameters),
            metadata=dict(context.metadata),
            created_at=datetime.now(UTC),
        )


class ReplayExecutionStore(Protocol):
    """Persistence boundary for produced workflow executions and later reads."""

    def save(self, execution: WorkflowExecution) -> None: ...

    def get_execution(
        self, execution_id: str, context: TenantContext
    ) -> WorkflowExecution | None: ...


class _RepositoryCancellationToken:
    """Cancellation token backed by the current, tenant-scoped Replay state."""

    def __init__(
        self,
        replay_repository: ReplayRepository,
        replay_id: str,
        context: TenantContext,
    ) -> None:
        self._repository = replay_repository
        self._replay_id = replay_id
        self._context = context

    @property
    def is_cancelled(self) -> bool:
        replay = self._repository.get(
            self._replay_id,
            self._context.organization_id,
            self._context.project_id or "",
        )
        return (
            replay is None
            or replay.status is ReplayStatus.CANCELLED
            or replay.cancel_requested_at is not None
        )


class ReplayJobHandler:
    """Execute a ``REPLAY_EXECUTION`` job using the replay's frozen evidence.

    The handler reserves the replay execution ID before invoking an adapter and
    uses optimistic replay updates after each lifecycle transition. Thus a
    retried worker keeps the same replay, job, configuration hash, and produced
    execution identity. Once a matching execution is saved with lineage
    metadata, the replay becomes ``EXECUTION_COMPLETED`` and can be evaluated
    by Phase 3.

    The handler validates tenant linkage, adapter availability, configuration,
    and returned execution identity. It supports cooperative cancellation and
    records structured failures without modifying the original execution.
    """

    def __init__(
        self,
        replay_repository: ReplayRepository,
        source_resolver: ReplaySourceResolver,
        execution_store: ReplayExecutionStore,
        adapter_registry: ReplayExecutionAdapterRegistry,
        execution_id_generator,
        clock=None,
        event_publisher: EventPublisher | None = None,
    ) -> None:
        self._replay_repository = replay_repository
        self._source_resolver = source_resolver
        self._execution_store = execution_store
        self._adapter_registry = adapter_registry
        self._execution_id_generator = execution_id_generator
        self._clock = clock or (lambda: datetime.now(UTC))
        self._event_publisher = event_publisher

    def handle(self, job: Job) -> JobResult:
        """Run or resume one replay execution job.

        ``EXECUTION_COMPLETED`` is idempotently successful: no adapter is run
        again. For queued work, the method starts the replay, reserves an ID,
        reconstructs the source via the selected adapter, persists the new
        execution plus source lineage, and transitions to completion. Any error
        before completion is mapped to replay failure evidence and a failed job
        result; job-worker retry policy remains outside this handler.
        """
        context = _context(job)
        replay_id = str(job.input_refs["replay_id"])
        replay = self._replay_repository.get(
            replay_id, context.organization_id, context.project_id or ""
        )
        if replay is None or replay.job_id != job.job_id:
            return JobResult(
                job.job_id, JobStatus.FAILED, None, "Replay job linkage is invalid."
            )
        if replay.status in {
            ReplayStatus.EXECUTION_COMPLETED,
            ReplayStatus.EVALUATING,
            ReplayStatus.COMPARING,
            ReplayStatus.COMPLETED,
        } and replay.replay_execution_id:
            return JobResult(job.job_id, JobStatus.SUCCEEDED, _result_ref(replay), None)
        if replay.status in {ReplayStatus.CANCELLED, ReplayStatus.ARCHIVED}:
            return JobResult(
                job.job_id,
                JobStatus.CANCELLED,
                None,
                "Replay is cancelled or archived.",
            )
        try:
            if replay.status is ReplayStatus.QUEUED:
                replay = self._replay_repository.update(
                    replay.mark_running(max(job.attempt_count, 1), self._clock()),
                    replay.version,
                )
                self._publish_lifecycle_event(replay, "started")
            if replay.replay_execution_id is None:
                replay = self._replay_repository.update(
                    replay.reserve_replay_execution_id(
                        self._execution_id_generator(), self._clock()
                    ),
                    replay.version,
                )
            source = self._source_resolver.get_execution(
                replay.source_execution_id, context
            )
            if source is None:
                raise ReplayReconstructionFailed(
                    "Source execution is no longer available."
                )
            configuration = replay.configuration
            if configuration is None:
                raise ReplayReconstructionFailed("Replay configuration is not frozen.")
            adapter = self._adapter_registry.resolve(configuration.execution_adapter)
            try:
                adapter.validate_configuration(source, configuration)
            except Exception as error:
                raise ReplayAdapterConfigurationInvalid(str(error)) from error
            token = _RepositoryCancellationToken(
                self._replay_repository, replay.replay_id, context
            )
            if token.is_cancelled:
                return self._cancel(replay, job)
            try:
                execution = adapter.replay(
                    source,
                    configuration,
                    ReplayExecutionContext(
                        replay_id=replay.replay_id,
                        source_execution_id=replay.source_execution_id,
                        new_execution_id=replay.replay_execution_id,
                        organization_id=context.organization_id,
                        project_id=context.project_id or "",
                        actor_id=context.actor_id,
                        request_id=context.request_id,
                        correlation_id=context.correlation_id,
                        attempt=max(job.attempt_count, 1),
                        cancellation_token=token,
                        metadata={},
                    ),
                )
            except Exception:
                if token.is_cancelled:
                    return self._cancel(replay, job)
                raise
            if token.is_cancelled:
                return self._cancel(replay, job)
            if execution.execution_id != replay.replay_execution_id:
                raise ReplayExecutionIdentityConflict(
                    "Adapter returned an unexpected execution ID."
                )
            if execution.execution_id == replay.source_execution_id:
                raise ReplayExecutionIdentityConflict(
                    "Replay execution ID equals source execution ID."
                )
            execution.organization_id = context.organization_id
            execution.project_id = context.project_id or ""
            execution.metadata = {
                **execution.metadata,
                "replay_id": replay.replay_id,
                "source_execution_id": replay.source_execution_id,
                "source_workflow_id": source.workflow_id,
                "source_workflow_version": source.workflow_version,
                "configuration_hash": configuration.configuration_hash,
                "job_id": job.job_id,
                "job_attempt": job.attempt_count,
            }
            self._execution_store.save(execution)
            completed = self._replay_repository.update(
                replay.mark_execution_completed(self._clock()), replay.version
            )
            self._publish_lifecycle_event(completed, "completed")
            return JobResult(
                job.job_id, JobStatus.SUCCEEDED, _result_ref(completed), None
            )
        except Exception as error:  # noqa: BLE001 - job failures must be finalized as failed results.
            return self._fail(replay, job, error)

    def _cancel(self, replay, job: Job) -> JobResult:
        """Finalize a previously requested cancellation when execution is safe to stop."""
        if (
            replay.status is ReplayStatus.RUNNING
            and replay.cancel_requested_at is not None
        ):
            replay = self._replay_repository.update(
                replay.mark_cancelled(self._clock()), replay.version
            )
            self._publish_lifecycle_event(replay, "cancelled")
        return JobResult(
            job.job_id, JobStatus.CANCELLED, None, "Replay cancellation requested."
        )

    def _fail(self, replay, job: Job, error: Exception) -> JobResult:
        """Persist a classified execution failure while retaining partial evidence."""
        if replay.status not in {
            ReplayStatus.READY,
            ReplayStatus.QUEUED,
            ReplayStatus.RUNNING,
        }:
            return JobResult(job.job_id, JobStatus.FAILED, None, str(error))
        failure = ReplayFailure(
            code=type(error).__name__,
            message=str(error),
            stage=_failure_stage(error),
            details={"job_id": job.job_id, "retryable": False},
            occurred_at=self._clock(),
        )
        failed = self._replay_repository.update(
            replay.mark_execution_failed(failure, self._clock()), replay.version
        )
        self._publish_lifecycle_event(failed, "failed")
        return JobResult(job.job_id, JobStatus.FAILED, None, str(error))

    def _publish_lifecycle_event(self, replay, state: str) -> None:
        """Publish a generic replay transition after its repository update."""
        if self._event_publisher is None:
            return
        asyncio.run(
            self._event_publisher.publish(
                ResourceLifecycleEvent(
                    tenant={
                        "organization_id": replay.organization_id,
                        "project_id": replay.project_id,
                    },
                    resource_kind="replay",
                    resource_id=replay.replay_id,
                    state=state,
                    payload={"mode": replay.mode.value},
                )
            )
        )


def _context(job: Job) -> TenantContext:
    """Return the original tenant context, never caller-supplied worker scope."""
    context = job.execution_context
    if context is None:
        raise ReplayReconstructionFailed(
            "Replay job is missing tenant execution context."
        )
    return TenantContext(
        context.organization_id,
        context.project_id,
        context.actor_id,
        context.submitted_request_id,
        context.correlation_id,
    )


def _result_ref(replay) -> str:
    return f"workflow_execution:{replay.replay_execution_id}"


def _failure_stage(error: Exception) -> ReplayFailureStage:
    if isinstance(error, ReplayAdapterNotFound):
        return ReplayFailureStage.ADAPTER_RESOLUTION
    if isinstance(error, ReplayAdapterConfigurationInvalid):
        return ReplayFailureStage.RECONSTRUCTION
    if isinstance(error, ReplayExecutionIdentityConflict):
        return ReplayFailureStage.EXECUTION
    if isinstance(error, ReplayExecutionPersistenceFailed):
        return ReplayFailureStage.EXECUTION_PERSISTENCE
    if isinstance(error, ReplayLineagePersistenceFailed):
        return ReplayFailureStage.LINEAGE_PERSISTENCE
    return ReplayFailureStage.EXECUTION
