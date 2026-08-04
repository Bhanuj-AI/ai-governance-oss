"""Application-facing lifecycle operations for governed workflow replays.

``ReplayApplicationService`` owns tenant authorization, idempotent request
submission, frozen historical configuration, and transitions into the Job
Execution Plane. It intentionally does not execute workflows, query concrete
storage, evaluate providers, compare metrics, or write ontology projections.
Those responsibilities stay with the replay job handlers and their dedicated
application boundaries.
"""

from __future__ import annotations

import hashlib
import asyncio
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from kavach.domain.replay import (
    Replay,
    ReplayConfiguration,
    ReplayConfigurationSource,
    ReplayFailure,
    ReplayFailureStage,
    ReplayMode,
    ReplayStatus,
)
from kavach.domain.replay.errors import (
    ReplayIdempotencyConflict,
    ReplayInvalidMode,
    ReplayInvalidTransition,
    ReplayCancellationFailed,
    ReplayNotFound,
    ReplayNotReplayable,
    ReplaySourceNotFound,
    ReplayJobSubmissionFailed,
    ReplayEvaluationNotReady,
    ReplayEvaluationSubmissionFailed,
    ReplayResultNotFound,
    ReplayNotCancellable,
    ReplayNotReady,
    ReplayUnauthorized,
)
from kavach.domain.jobs import JobExecutionContext, JobStatus, JobSubmission, JobType
from kavach.domain.workflow_execution import WorkflowExecution
from kavach.events import EventPublisher, ResourceLifecycleEvent
from kavach.authorization.contracts import (
    AuthorizationEnforcementRequest,
    AuthorizationEnforcer,
    AuthorizationResourceFacts,
)
from kavach.repositories.replay_repository import ReplayListFilters, ReplayRepository
from kavach.repositories.replay_result_repository import ReplayResultRepository
from kavach.tenancy.domain import TenantContext
from kavach.tenancy.errors import AuthorizationDenied
from kavach.tenancy.permissions import Permission


class ReplaySourceResolver(Protocol):
    """Read-only source-execution boundary used while creating a Replay."""

    def get_execution(
        self, execution_id: str, context: TenantContext
    ) -> WorkflowExecution | None: ...


class ReplayabilityValidator(Protocol):
    """Validates and freezes immutable source evidence for a future replay."""

    def validate(
        self,
        source_execution: WorkflowExecution,
        context: TenantContext,
    ) -> ReplayConfiguration: ...


class HistoricalReplayabilityValidator:
    """Build a replay configuration solely from persisted execution evidence.

    The validator rejects cross-project sources, incomplete workflow snapshots,
    and mutable aliases such as ``latest``. Its output records stable
    input/state references, resolved artifacts, and a deterministic
    configuration hash; it never resolves a live workflow version or runtime
    default.
    """

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))

    def validate(
        self,
        source_execution: WorkflowExecution,
        context: TenantContext,
    ) -> ReplayConfiguration:
        """Return frozen configuration evidence or explain why replay is unsafe."""
        if (
            source_execution.organization_id != context.organization_id
            or source_execution.project_id != (context.project_id or "")
        ):
            raise ReplayNotReplayable("Source execution belongs to another project.")
        if (
            not source_execution.workflow_id.strip()
            or not source_execution.workflow_version.strip()
        ):
            raise ReplayNotReplayable(
                "Source execution is missing workflow version evidence."
            )
        if source_execution.input is None:
            raise ReplayNotReplayable("Source execution is missing its input snapshot.")
        if source_execution.final_state is None:
            raise ReplayNotReplayable("Source execution is missing its state snapshot.")
        if not source_execution.execution_adapter.strip():
            raise ReplayNotReplayable(
                "Source execution is missing its execution adapter."
            )

        input_ref = source_execution.input_snapshot_ref or _inline_reference(
            "input", source_execution.input
        )
        state_ref = source_execution.state_snapshot_ref or _inline_reference(
            "state", source_execution.final_state
        )
        references = (
            input_ref,
            state_ref,
            *(source_execution.artifact_refs or ()),
            *(source_execution.prompt_refs or ()),
            *(source_execution.model_refs or ()),
            *(source_execution.dataset_refs or ()),
            *(source_execution.policy_refs or ()),
        )
        if any(_is_mutable_alias(reference) for reference in references):
            raise ReplayNotReplayable(
                "Source execution contains a mutable configuration reference."
            )
        payload = {
            "workflow_id": source_execution.workflow_id,
            "workflow_version": source_execution.workflow_version,
            "execution_adapter": source_execution.execution_adapter,
            "input_snapshot_ref": input_ref,
            "state_snapshot_ref": state_ref,
            "artifact_refs": source_execution.artifact_refs or [],
            "prompt_refs": source_execution.prompt_refs or [],
            "model_refs": source_execution.model_refs or [],
            "dataset_refs": source_execution.dataset_refs or [],
            "policy_refs": source_execution.policy_refs or [],
            "runtime_parameters": source_execution.runtime_parameters or {},
            "configuration_source": ReplayConfigurationSource.ORIGINAL.value,
        }
        return ReplayConfiguration(
            workflow_id=source_execution.workflow_id,
            workflow_version=source_execution.workflow_version,
            execution_adapter=source_execution.execution_adapter,
            input_snapshot_ref=input_ref,
            state_snapshot_ref=state_ref,
            artifact_refs=tuple(source_execution.artifact_refs or ()),
            prompt_refs=tuple(source_execution.prompt_refs or ()),
            model_refs=tuple(source_execution.model_refs or ()),
            dataset_refs=tuple(source_execution.dataset_refs or ()),
            policy_refs=tuple(source_execution.policy_refs or ()),
            runtime_parameters=source_execution.runtime_parameters or {},
            resolved_at=self._clock(),
            configuration_hash=_hash(payload),
        )


class ReplayApplicationService:
    """Coordinate Replay lifecycle requests within an authorized tenant scope.

    Phase 1 creates a durable draft and freezes source evidence. Phase 2
    submits one execution job and supports cooperative cancellation. Phase 3
    submits a separate evaluation job and exposes immutable result evidence.
    Long-running work belongs to the job handlers; this service persists only
    aggregate transitions around submissions.

    Each operation uses tenant-scoped repository contracts and the appropriate
    replay permission. Stable job keys plus persisted job references make
    transport retries idempotent rather than creating duplicate work.
    """

    def __init__(
        self,
        replay_repository: ReplayRepository,
        source_resolver: ReplaySourceResolver,
        replayability_validator: ReplayabilityValidator | None = None,
        authorization_service: Any | None = None,
        job_service: Any | None = None,
        configuration_service: Any | None = None,
        result_repository: ReplayResultRepository | None = None,
        provider_installation_service: Any | None = None,
        id_generator: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
        event_publisher: EventPublisher | None = None,
        authorization_enforcers: tuple[AuthorizationEnforcer, ...] = (),
    ) -> None:
        self._replay_repository = replay_repository
        self._source_resolver = source_resolver
        self._clock = clock or (lambda: datetime.now(UTC))
        self._validator = replayability_validator or HistoricalReplayabilityValidator(
            self._clock
        )
        self._authorization_service = authorization_service
        self._job_service = job_service
        self._configuration_service = configuration_service
        self._result_repository = result_repository
        self._provider_installation_service = provider_installation_service
        self._id_generator = id_generator or (lambda: str(uuid4()))
        self._event_publisher = event_publisher
        self._authorization_enforcers = authorization_enforcers

    def create(
        self,
        *,
        source_execution_id: str,
        context: TenantContext,
        idempotency_key: str,
        mode: ReplayMode | str = ReplayMode.FULL,
        configuration_source: ReplayConfigurationSource
        | str = ReplayConfigurationSource.ORIGINAL,
        metadata: Mapping[str, Any] | None = None,
    ) -> Replay:
        """Create and freeze a replay request without executing it.

        A DRAFT is persisted before source validation so an invalid request
        remains queryable evidence. The idempotency key is bound to a canonical
        tenant-scoped request hash: identical calls return the existing replay,
        while different inputs raise ``ReplayIdempotencyConflict``. Missing or
        non-replayable evidence turns that saved draft into a structured FAILED
        replay rather than discarding the request.
        """
        self._authorize(context, Permission.REPLAY_CREATE)
        mode = self._mode(mode)
        source = self._configuration_source(configuration_source)
        metadata = metadata or {}
        project_id = context.project_id or ""
        input_hash = _hash(
            {
                "organization_id": context.organization_id,
                "project_id": project_id,
                "source_execution_id": source_execution_id,
                "mode": mode.value,
                "configuration_source": source.value,
                "metadata": metadata,
            }
        )
        existing = self._replay_repository.find_by_idempotency(
            idempotency_key, context.organization_id, project_id
        )
        if existing is not None:
            if existing.input_hash == input_hash:
                return existing
            raise ReplayIdempotencyConflict(
                "Idempotency key was already used for a different replay request."
            )

        draft = Replay.create(
            replay_id=self._id_generator(),
            source_execution_id=source_execution_id,
            mode=mode,
            requested_by=context.actor_id,
            organization_id=context.organization_id,
            project_id=project_id,
            request_id=context.request_id,
            correlation_id=context.correlation_id,
            idempotency_key=idempotency_key,
            input_hash=input_hash,
            metadata=metadata,
            now=self._clock(),
        )
        draft = self._replay_repository.save(draft)
        self._publish_lifecycle_event(draft, "created")
        try:
            configuration = self._resolve_configuration(source_execution_id, context)
            ready = draft.mark_ready(configuration, self._clock())
            persisted = self._replay_repository.update(ready, draft.version)
            self._publish_lifecycle_event(persisted, "ready")
            return persisted
        except (ReplaySourceNotFound, ReplayNotReplayable) as error:
            failure = ReplayFailure(
                code=type(error).__name__,
                message=str(error),
                stage=(
                    ReplayFailureStage.SOURCE_RESOLUTION
                    if isinstance(error, ReplaySourceNotFound)
                    else ReplayFailureStage.VALIDATION
                ),
                details={"source_execution_id": source_execution_id},
                occurred_at=self._clock(),
            )
            failed = draft.mark_failed(failure, self._clock())
            persisted = self._replay_repository.update(failed, draft.version)
            self._publish_lifecycle_event(persisted, "failed")
            return persisted

    def dry_run(
        self,
        *,
        source_execution_id: str,
        context: TenantContext,
        mode: ReplayMode | str = ReplayMode.FULL,
        configuration_source: ReplayConfigurationSource
        | str = ReplayConfigurationSource.ORIGINAL,
    ) -> ReplayConfiguration:
        """Resolve frozen configuration without saving a Replay or reserving keys."""
        self._authorize(context, Permission.REPLAY_CREATE)
        self._mode(mode)
        self._configuration_source(configuration_source)
        return self._resolve_configuration(source_execution_id, context)

    def get(self, replay_id: str, context: TenantContext) -> Replay:
        """Return one replay only when it belongs to the active tenant project."""
        self._authorize(context, Permission.REPLAY_READ)
        replay = self._replay_repository.get(
            replay_id, context.organization_id, context.project_id or ""
        )
        if replay is None:
            raise ReplayNotFound(f"Replay '{replay_id}' was not found.")
        return replay

    def list(
        self, context: TenantContext, filters: ReplayListFilters | None = None
    ) -> list[Replay]:
        """List tenant-scoped replays using bounded repository filters."""
        self._authorize(context, Permission.REPLAY_READ)
        return self._replay_repository.list(
            filters or ReplayListFilters(),
            context.organization_id,
            context.project_id or "",
        )

    def list_recent_terminal(
        self, context: TenantContext, *, limit: int = 3
    ) -> list[Replay]:
        """Return a bounded, tenant-scoped history of terminal replay jobs.

        The Intelligence layer uses this evidence-only query for historical
        reasoning. It neither reconstructs a result nor changes replay state.
        """
        if not 1 <= limit <= 20:
            raise ValueError("Replay history limit must be between 1 and 20.")
        self._authorize(context, Permission.REPLAY_READ)
        replays = self._replay_repository.list(
            ReplayListFilters(limit=100),
            context.organization_id,
            context.project_id or "",
        )
        terminal = [
            replay
            for replay in replays
            if replay.status in {
                ReplayStatus.COMPLETED,
                ReplayStatus.FAILED,
                ReplayStatus.CANCELLED,
                ReplayStatus.ARCHIVED,
            }
        ]
        return sorted(
            terminal,
            key=lambda replay: replay.completed_at or replay.updated_at,
            reverse=True,
        )[:limit]

    def archive(self, replay_id: str, context: TenantContext) -> Replay:
        """Archive eligible replay state without deleting execution or result evidence."""
        self._authorize(context, Permission.REPLAY_ARCHIVE)
        replay = self.get(replay_id, context)
        try:
            archived = replay.archive(self._clock())
        except ValueError as error:
            raise ReplayInvalidTransition(str(error)) from error
        persisted = self._replay_repository.archive(archived, replay.version)
        self._publish_lifecycle_event(persisted, "archived")
        return persisted

    def submit(self, replay_id: str, context: TenantContext) -> Replay:
        """Submit the single governed execution job for a READY replay.

        Job input contains references and the frozen configuration hash, never
        full workflow input or provider state. Queued, running, and completed
        execution replays return unchanged, making retries idempotent. The
        aggregate is queued only after Job Plane submission succeeds.
        """
        self._authorize(context, Permission.REPLAY_EXECUTE)
        replay = self.get(replay_id, context)
        self._enforce_operation(context, "replay.execute", replay)
        if replay.status in {
            ReplayStatus.QUEUED,
            ReplayStatus.RUNNING,
            ReplayStatus.EXECUTION_COMPLETED,
        }:
            return replay
        if replay.status is not ReplayStatus.READY or replay.configuration is None:
            raise ReplayNotReady(
                f"Replay '{replay_id}' is not ready for execution submission."
            )
        if self._job_service is None:
            raise ReplayJobSubmissionFailed("Replay job service is not configured.")
        try:
            job = self._job_service.submit(
                JobSubmission(
                    job_type=JobType.REPLAY_EXECUTION,
                    input_refs={
                        "replay_id": replay.replay_id,
                        "source_execution_id": replay.source_execution_id,
                        "configuration_hash": replay.configuration.configuration_hash,
                        "execution_adapter": replay.configuration.execution_adapter,
                        "organization_id": context.organization_id,
                        "project_id": context.project_id or "",
                        "request_id": context.request_id,
                        "correlation_id": context.correlation_id,
                    },
                    idempotency_key=(
                        f"replay-execution:{context.organization_id}:"
                        f"{context.project_id or ''}:{replay.replay_id}"
                    ),
                    submitted_by=context.actor_id,
                    max_attempts=self._max_attempts(context),
                    execution_context=JobExecutionContext(
                        organization_id=context.organization_id,
                        project_id=context.project_id or "",
                        actor_id=context.actor_id,
                        submitted_request_id=context.request_id,
                        correlation_id=context.correlation_id,
                    ),
                )
            )
        except Exception as error:
            raise ReplayJobSubmissionFailed(
                f"Replay job submission failed: {error}"
            ) from error
        try:
            queued = replay.mark_queued(job.job_id, self._clock())
            persisted = self._replay_repository.update(queued, replay.version)
            self._publish_lifecycle_event(persisted, "queued")
            return persisted
        except ValueError as error:
            raise ReplayNotReady(str(error)) from error

    def cancel(self, replay_id: str, context: TenantContext) -> Replay:
        """Request cooperative cancellation without deleting durable evidence.

        READY replays cancel immediately. Active work records a cancellation
        request and delegates to the linked job; execution/evaluation handlers
        observe it at safe boundaries. Completed executions, evaluations,
        comparisons, drift, and results remain available for governance review.
        """
        self._authorize(context, Permission.REPLAY_CANCEL)
        replay = self.get(replay_id, context)
        self._enforce_operation(context, "replay.cancel", replay)
        if replay.status not in {
            ReplayStatus.READY,
            ReplayStatus.QUEUED,
            ReplayStatus.RUNNING,
            ReplayStatus.EXECUTION_COMPLETED,
            ReplayStatus.EVALUATING,
            ReplayStatus.COMPARING,
        }:
            raise ReplayNotCancellable(
                f"Replay '{replay_id}' cannot be cancelled from {replay.status.value}."
            )
        requested = replay.request_cancellation(self._clock())
        if replay.status is ReplayStatus.READY:
            cancelled = requested.mark_cancelled(self._clock())
            persisted = self._replay_repository.update(cancelled, replay.version)
            self._publish_lifecycle_event(persisted, "cancelled")
            return persisted
        job_id = (
            replay.evaluation_job_id
            if replay.status in {ReplayStatus.EVALUATING, ReplayStatus.COMPARING}
            else replay.job_id
        )
        if self._job_service is None or job_id is None:
            raise ReplayCancellationFailed("Replay job service is not configured.")
        persisted = self._replay_repository.update(requested, replay.version)
        try:
            job = self._job_service.cancel(job_id, context)
        except Exception as error:
            raise ReplayCancellationFailed(
                f"Replay cancellation failed: {error}"
            ) from error
        if job.status is JobStatus.CANCELLED:
            cancelled = self._replay_repository.update(
                persisted.mark_cancelled(self._clock()), persisted.version
            )
            self._publish_lifecycle_event(cancelled, "cancelled")
            return cancelled
        return persisted

    def validate_submission(self, replay_id: str, context: TenantContext) -> Replay:
        """Validate execution submission without creating a job or changing state."""
        self._authorize(context, Permission.REPLAY_EXECUTE)
        replay = self.get(replay_id, context)
        if replay.status is not ReplayStatus.READY or replay.configuration is None:
            raise ReplayNotReady(
                f"Replay '{replay_id}' is not ready for execution submission."
            )
        if self._job_service is None:
            raise ReplayJobSubmissionFailed("Replay job service is not configured.")
        return replay

    def validate_cancellation(self, replay_id: str, context: TenantContext) -> Replay:
        """Validate cancellation eligibility without changing the replay or job."""
        self._authorize(context, Permission.REPLAY_CANCEL)
        replay = self.get(replay_id, context)
        if replay.status not in {
            ReplayStatus.READY,
            ReplayStatus.QUEUED,
            ReplayStatus.RUNNING,
            ReplayStatus.EXECUTION_COMPLETED,
            ReplayStatus.EVALUATING,
            ReplayStatus.COMPARING,
        }:
            raise ReplayNotCancellable(
                f"Replay '{replay_id}' cannot be cancelled from {replay.status.value}."
            )
        job_id = (
            replay.evaluation_job_id
            if replay.status in {ReplayStatus.EVALUATING, ReplayStatus.COMPARING}
            else replay.job_id
        )
        if replay.status is not ReplayStatus.READY and (
            self._job_service is None or job_id is None
        ):
            raise ReplayCancellationFailed("Replay job service is not configured.")
        return replay

    def evaluate(
        self,
        replay_id: str,
        context: TenantContext,
        *,
        evaluation_provider: str | None = None,
        provider_installation_id: str | None = None,
        baseline_strategy: str = "LATEST_COMPATIBLE",
        baseline_evaluation_id: str | None = None,
    ) -> Replay:
        """Submit the separate Phase 3 evaluation job for a completed execution.

        Only an ``EXECUTION_COMPLETED`` replay with a persisted produced
        execution may enter evaluation. Repeated calls in ``EVALUATING``,
        ``COMPARING``, or ``COMPLETED`` return the existing replay and job
        reference. Job input contains stable execution/evidence references,
        selected baseline intent, tenant correlation data, and the effective
        drift policy—not execution payloads or complete evaluation artifacts.
        """
        self._authorize(context, Permission.REPLAY_EVALUATE)
        replay = self.get(replay_id, context)
        if replay.status in {
            ReplayStatus.EVALUATING,
            ReplayStatus.COMPARING,
            ReplayStatus.COMPLETED,
        }:
            return replay
        if (
            replay.status is not ReplayStatus.EXECUTION_COMPLETED
            or not replay.replay_execution_id
        ):
            raise ReplayEvaluationNotReady(
                f"Replay '{replay_id}' is not ready for evaluation."
            )
        if self._job_service is None:
            raise ReplayEvaluationSubmissionFailed(
                "Replay job service is not configured."
            )
        provider = evaluation_provider or str(
            replay.metadata.get("evaluation_provider", "")
        )
        if provider_installation_id:
            if self._provider_installation_service is None:
                raise ReplayEvaluationSubmissionFailed("Provider installations are unavailable in this runtime.")
            provider = self._provider_installation_service.resolve_provider_type(
                provider_installation_id, context
            ).provider_type
        if not provider:
            raise ReplayEvaluationSubmissionFailed(
                "An evaluation provider must be supplied for this replay."
            )
        strategy = baseline_strategy.upper()
        if strategy == "EXPLICIT" and not baseline_evaluation_id:
            raise ReplayEvaluationSubmissionFailed(
                "An explicit baseline evaluation ID is required."
            )
        try:
            job = self._job_service.submit(
                JobSubmission(
                    job_type=JobType.REPLAY_EVALUATION,
                    input_refs={
                        "replay_id": replay.replay_id,
                        "source_execution_id": replay.source_execution_id,
                        "replay_execution_id": replay.replay_execution_id,
                        "evaluation_provider": provider,
                        "provider_installation_id": provider_installation_id,
                        "evaluation_configuration_hash": replay.configuration.configuration_hash
                        if replay.configuration
                        else "",
                        "baseline_strategy": strategy,
                        "explicit_baseline_evaluation_id": baseline_evaluation_id,
                        "drift_threshold_policy": self._drift_threshold_policy(context),
                        "organization_id": context.organization_id,
                        "project_id": context.project_id or "",
                        "request_id": context.request_id,
                        "correlation_id": context.correlation_id,
                    },
                    idempotency_key=(
                        f"replay-evaluation:{context.organization_id}:"
                        f"{context.project_id or ''}:{replay.replay_id}"
                    ),
                    submitted_by=context.actor_id,
                    max_attempts=self._evaluation_max_attempts(context),
                    execution_context=JobExecutionContext(
                        organization_id=context.organization_id,
                        project_id=context.project_id or "",
                        actor_id=context.actor_id,
                        submitted_request_id=context.request_id,
                        correlation_id=context.correlation_id,
                    ),
                )
            )
            persisted = self._replay_repository.update(
                replay.mark_evaluating(job.job_id, self._clock()), replay.version
            )
            self._publish_lifecycle_event(persisted, "evaluating")
            return persisted
        except Exception as error:
            raise ReplayEvaluationSubmissionFailed(
                f"Replay evaluation submission failed: {error}"
            ) from error

    def get_result(self, replay_id: str, context: TenantContext):
        """Return immutable terminal evidence for a completed tenant replay.

        Results are not reconstructed from mutable aggregate state. A persisted
        result reference is required and the result is loaded through the
        dedicated immutable-result repository; absent or inaccessible evidence
        raises ``ReplayResultNotFound``.
        """
        self._authorize(context, Permission.REPLAY_RESULT_READ)
        replay = self.get(replay_id, context)
        if self._result_repository is None or not replay.result_id:
            raise ReplayResultNotFound(f"Replay '{replay_id}' has no finalized result.")
        result = self._result_repository.get(
            replay.result_id, context.organization_id, context.project_id or ""
        )
        if result is None:
            raise ReplayResultNotFound(
                f"Replay result '{replay.result_id}' was not found."
            )
        return result

    def _resolve_configuration(
        self, source_execution_id: str, context: TenantContext
    ) -> ReplayConfiguration:
        """Load source evidence through the resolver and freeze configuration."""
        source = self._source_resolver.get_execution(source_execution_id, context)
        if source is None:
            raise ReplaySourceNotFound(
                f"Source execution '{source_execution_id}' was not found."
            )
        return self._validator.validate(source, context)

    def _publish_lifecycle_event(self, replay: Replay, state: str) -> None:
        """Publish a generic replay fact only after its durable transition."""
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

    def _authorize(self, context: TenantContext, permission: Permission) -> None:
        """Map control-plane denials to the Replay domain's public error type."""
        if self._authorization_service is None:
            return
        try:
            self._authorization_service.require(context, permission)
        except AuthorizationDenied as error:
            raise ReplayUnauthorized(str(error)) from error

    def _enforce_operation(
        self, context: TenantContext, action: str, replay: Replay
    ) -> None:
        """Run generic plugin constraints only after the Core RBAC gate passed."""
        if not self._authorization_enforcers:
            return
        resource = AuthorizationResourceFacts(
            resource_type="Replay",
            resource_id=replay.replay_id,
            organization_id=replay.organization_id,
            project_id=replay.project_id or None,
            owner_id=replay.requested_by,
            lifecycle_state=replay.status.value,
            version=replay.version,
        )
        request = AuthorizationEnforcementRequest(context, action, resource)
        for enforcer in self._authorization_enforcers:
            try:
                decision = enforcer.authorize(request)
            except Exception as error:
                raise ReplayUnauthorized("Fine-grained authorization evaluation failed.") from error
            if not decision.allowed:
                detail = decision.reason_code
                if decision.decision_id:
                    detail = f"{detail} (decision {decision.decision_id})"
                raise ReplayUnauthorized(detail)

    def _max_attempts(self, context: TenantContext) -> int:
        """Resolve the configured execution retry budget for this tenant scope."""
        if self._configuration_service is None:
            return 3
        from kavach.settings_control.operational import setting_context

        return int(
            self._configuration_service.get(
                "replay.max_attempts", setting_context(context)
            )
        )

    def validate_evaluation(
        self,
        replay_id: str,
        context: TenantContext,
        *,
        evaluation_provider: str | None = None,
        provider_installation_id: str | None = None,
        baseline_strategy: str = "LATEST_COMPATIBLE",
        baseline_evaluation_id: str | None = None,
    ) -> Replay:
        """Validate Phase 3 inputs without reserving a job or mutating a replay."""
        self._authorize(context, Permission.REPLAY_EVALUATE)
        replay = self.get(replay_id, context)
        if (
            replay.status is not ReplayStatus.EXECUTION_COMPLETED
            or not replay.replay_execution_id
        ):
            raise ReplayEvaluationNotReady(
                f"Replay '{replay_id}' is not ready for evaluation."
            )
        if provider_installation_id:
            if self._provider_installation_service is None:
                raise ReplayEvaluationSubmissionFailed(
                    "Provider installations are unavailable in this runtime."
                )
            self._provider_installation_service.resolve_provider_type(
                provider_installation_id, context
            )
        elif not evaluation_provider and not replay.metadata.get("evaluation_provider"):
            raise ReplayEvaluationSubmissionFailed(
                "An evaluation provider must be supplied for this replay."
            )
        if baseline_strategy.upper() == "EXPLICIT" and not baseline_evaluation_id:
            raise ReplayEvaluationSubmissionFailed(
                "An explicit baseline evaluation ID is required."
            )
        return replay

    def _evaluation_max_attempts(self, context: TenantContext) -> int:
        """Resolve the independent retry budget for replay evaluation jobs."""
        if self._configuration_service is None:
            return 3
        from kavach.settings_control.operational import setting_context

        return int(
            self._configuration_service.get(
                "replay.evaluation_max_attempts", setting_context(context)
            )
        )

    def _drift_threshold_policy(self, context: TenantContext) -> dict[str, Any]:
        """Capture effective governed drift policy in the immutable job input."""
        if self._configuration_service is None:
            return {"policy": "governance-default-v1"}
        from kavach.settings_control.operational import setting_context

        return dict(
            self._configuration_service.get(
                "replay.drift_threshold_policy", setting_context(context)
            )
        )

    @staticmethod
    def _mode(value: ReplayMode | str) -> ReplayMode:
        try:
            return ReplayMode(value)
        except ValueError as error:
            raise ReplayInvalidMode("Only FULL replay mode is supported.") from error

    @staticmethod
    def _configuration_source(
        value: ReplayConfigurationSource | str,
    ) -> ReplayConfigurationSource:
        try:
            return ReplayConfigurationSource(value)
        except ValueError as error:
            raise ReplayNotReplayable(
                "Only ORIGINAL replay configuration is supported."
            ) from error


def _inline_reference(kind: str, value: object) -> str:
    return f"inline:{kind}:{_hash(value)}"


def _hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _is_mutable_alias(reference: str) -> bool:
    tokens = {token.lower() for token in reference.replace("/", ":").split(":")}
    return bool(tokens & {"latest", "active", "current", "default"})
