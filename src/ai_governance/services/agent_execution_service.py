"""Application service for agent execution trace ingestion and reads.

``AgentExecutionService`` owns tenant authorization, idempotent event
ingestion, execution lifecycle transitions, and the read model for
agent execution traces. It does not execute agents or manage agent sessions.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import uuid4

from ai_governance.domain.agent_execution import (
    AgentExecution,
    AgentExecutionEvent,
    AgentExecutionStatus,
    EventType,
    ToolCallContext,
    WorkflowStep,
    WorkflowStepLifecycle,
)
from ai_governance.domain.agent_execution.agent_execution_event import (
    ActorType,
)
from ai_governance.domain.agent_execution.errors import (
    AgentExecutionIdempotencyConflict,
    AgentExecutionInvalidTransition,
    AgentExecutionNotFound,
)
from ai_governance.domain.runtime_findings.finding import ReconciliationWindow
from ai_governance.repositories.agent_execution_repository import (
    AgentExecutionAgentListFilters,
    AgentExecutionAgentSummary,
    AgentExecutionEventListFilters,
    AgentExecutionEventRepository,
    AgentExecutionListFilters,
    AgentExecutionRepository,
)
from ai_governance.repositories.runtime_finding_repository import (
    RuntimeFindingRepository,
)
from ai_governance.tenancy.domain import TenantContext
from ai_governance.tenancy.errors import AuthorizationDenied
from ai_governance.tenancy.permissions import Permission


class ProjectionTrigger(Protocol):
    """Optional callback to trigger async graph projection after terminal state."""

    def trigger(self, execution_id: str, organization_id: str, project_id: str | None) -> None: ...

class AuthorizationEnforcer(Protocol):
    """Fine-grained authorization enforcement boundary."""

    def authorize(self, request: object) -> object: ...


@dataclass(frozen=True)
class AgentExecutionSummary:
    """Lightweight read model for execution listings."""

    execution_id: str
    agent_id: str
    agent_name: str
    runtime_provider: str
    external_execution_id: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    event_count: int

    @property
    def duration_seconds(self) -> float | None:
        if self.completed_at is None:
            return None
        return (self.completed_at - self.started_at).total_seconds()


@dataclass(frozen=True)
class AgentExecutionDetail:
    """Full read model for a single execution with its events."""

    execution: AgentExecution
    events: list[AgentExecutionEvent]
    event_counts: dict[str, int]


@dataclass(frozen=True)
class AgentExecutionListPage:
    """Cursor-based paginated execution listing."""

    items: list[AgentExecutionSummary]
    next_cursor: str | None


@dataclass(frozen=True)
class AgentExecutionAgentListPage:
    """Offset-paginated observed-agent index."""

    items: list[AgentExecutionAgentSummary]
    next_offset: int | None


class AgentExecutionService:
    """Application-facing operations for agent execution traces.

    This service is the single entry point for external runtime ingestion
    and platform-side reads. It enforces tenant isolation, idempotency,
    lifecycle invariants, and privacy constraints.
    """

    def __init__(
        self,
        execution_repository: AgentExecutionRepository,
        event_repository: AgentExecutionEventRepository,
        authorization_enforcer: AuthorizationEnforcer | None = None,
        configuration_service: Any | None = None,
        runtime_finding_repository: RuntimeFindingRepository | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._execution_repo = execution_repository
        self._event_repo = event_repository
        self._authorization_enforcer = authorization_enforcer
        self._configuration_service = configuration_service
        self._runtime_finding_repository = runtime_finding_repository
        self._clock = clock or (lambda: datetime.now(UTC))

    def register_projection_trigger(self, trigger: ProjectionTrigger) -> None:
        """Register an async projection trigger for terminal state transitions."""
        self._projection_trigger = trigger

    def _trigger_projection(self, execution: AgentExecution) -> None:
        """Schedule async graph projection after terminal state."""
        if self._projection_trigger is None:
            return
        try:
            self._projection_trigger.trigger(
                execution.execution_id,
                execution.organization_id,
                execution.project_id,
            )
        except Exception:  # noqa: BLE001, S110 - ingestion must survive projection faults.
            # Projection failure must never affect runtime ingestion.
            pass

        self._projection_trigger: ProjectionTrigger | None = None

    # -- Authorization --------------------------------------------------------

    def _authorize(self, context: TenantContext, permission: Permission) -> None:
        if self._authorization_enforcer is None:
            return
        from ai_governance.authorization.contracts import (
            AuthorizationEnforcementRequest,
            AuthorizationResourceFacts,
        )

        resource = AuthorizationResourceFacts(
            resource_type="agent_execution",
            organization_id=context.organization_id,
            project_id=context.project_id,
        )
        request = AuthorizationEnforcementRequest(context, permission.value, resource)
        try:
            decision = self._authorization_enforcer.authorize(request)
        except Exception as error:
            raise AuthorizationDenied(None) from error
        if not decision.allowed:
            raise AuthorizationDenied(decision)

    # -- Execution lifecycle --------------------------------------------------

    def ingest_start(
        self,
        *,
        agent_id: str,
        agent_name: str,
        agent_version: str,
        external_execution_id: str,
        runtime_provider: str,
        correlation_id: str | None = None,
        parent_execution_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        context: TenantContext,
    ) -> AgentExecution:
        """Ingest an EXECUTION_STARTED event and create/transition the execution.

        This is the primary ingestion entry point for external runtimes.
        Duplicate delivery with the same (tenant, runtime_provider,
        external_execution_id) is idempotent.
        """
        self._authorize(context, Permission.AGENT_EXECUTION_INGEST)

        now = self._clock()
        idempotency_key = _idempotency_key_for_start(
            external_execution_id, runtime_provider, context
        )

        # Check for existing execution with same external ID.
        existing = self._execution_repo.get_by_external_id(
            external_execution_id, runtime_provider, context.organization_id, context.project_id
        )

        if existing is not None:
            # Idempotent replay: return existing execution.
            if existing.is_terminal:
                return existing
            # Transition to RUNNING if still RECEIVED.
            if existing.status is AgentExecutionStatus.RECEIVED:
                updated = self._execution_repo.update_status(
                    existing.execution_id,
                    context.organization_id,
                    context.project_id,
                    AgentExecutionStatus.RUNNING,
                    None,
                    existing.version,
                )
                return updated
            return existing

        # Create new execution.
        execution_id = str(uuid4())
        execution = AgentExecution(
            execution_id=execution_id,
            organization_id=context.organization_id,
            project_id=context.project_id,
            agent_id=agent_id,
            agent_name=agent_name,
            agent_version=agent_version,
            external_execution_id=external_execution_id,
            runtime_provider=runtime_provider,
            status=AgentExecutionStatus.RECEIVED,
            started_at=now,
            completed_at=None,
            correlation_id=correlation_id,
            parent_execution_id=parent_execution_id,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )

        # Persist execution.
        self._execution_repo.save(execution)

        # Create and persist EXECUTION_STARTED event.
        start_event = AgentExecutionEvent(
            event_id=str(uuid4()),
            execution_id=execution_id,
            organization_id=context.organization_id,
            project_id=context.project_id,
            event_type=EventType.EXECUTION_STARTED,
            sequence_number=0,
            occurred_at=now,
            received_at=now,
            correlation_id=correlation_id,
            causation_id=None,
            actor_id=agent_id,
            actor_type=ActorType.AGENT,
            resource_references=(),
            evidence_references=(),
            attributes={
                "agent_name": agent_name,
                "agent_version": agent_version,
                "runtime_provider": runtime_provider,
                "external_execution_id": external_execution_id,
            },
            event_schema_version="1",
        )
        self._event_repo.save(start_event, idempotency_key=idempotency_key)

        # Transition to RUNNING.
        updated = self._execution_repo.update_status(
            execution_id,
            context.organization_id,
            context.project_id,
            AgentExecutionStatus.RUNNING,
            None,
            0,
        )
        return updated

    def ingest_event(
        self,
        *,
        execution_id: str,
        event_type: EventType,
        attributes: dict[str, Any],
        context: TenantContext,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        actor_id: str | None = None,
        actor_type: ActorType | None = None,
        workflow_step: WorkflowStep | None = None,
        tool_call_context: ToolCallContext | None = None,
        resource_references: list[str] | None = None,
        evidence_references: list[str] | None = None,
        occurred_at: datetime | None = None,
    ) -> AgentExecutionEvent:
        """Ingest a runtime event (MODEL_CALL, TOOL_CALL, WORKFLOW_STEP, etc.).

        Events are append-only and immutable after persistence.
        Duplicate delivery with the same idempotency key is a no-op if
        the payload matches; conflicting payloads raise a conflict.
        """
        self._authorize(context, Permission.AGENT_EXECUTION_INGEST)

        execution = self._execution_repo.get(
            execution_id, context.organization_id, context.project_id
        )
        if execution is None:
            raise AgentExecutionNotFound(
                f"Execution '{execution_id}' not found in tenant scope."
            )
        if execution.is_terminal:
            raise AgentExecutionInvalidTransition(
                f"Cannot ingest events for terminal execution '{execution_id}'."
            )

        if idempotency_key is not None:
            existing = self._event_repo.find_by_idempotency_key(
                idempotency_key,
                execution_id,
                context.organization_id,
                context.project_id,
            )
            if existing is not None:
                if (
                    existing.event_type is not event_type
                    or dict(existing.attributes) != attributes
                    or existing.workflow_step != workflow_step
                    or existing.tool_call_context != tool_call_context
                ):
                    raise AgentExecutionIdempotencyConflict(
                        f"Idempotency key conflict for execution '{execution_id}'."
                    )
                return existing

        self._validate_workflow_step_transition(
            execution_id,
            event_type,
            workflow_step,
            context,
        )

        now = self._clock()
        event_occurred_at = occurred_at or now
        contract = self._finalization_contract_for(event_occurred_at, context)
        if contract is not None:
            # A persisted decision contract is authoritative.  A later
            # settings edit may govern future windows, but cannot reopen this
            # one or relabel a late delivery as on-time. Legacy contracts
            # without a recorded cutoff are conservatively too late.
            cutoff = contract.finalization_cutoff_at
            lateness_hours = contract.lateness_policy_hours
            late_for_runtime_findings = cutoff is None or now > cutoff
        else:
            lateness_hours = self._runtime_findings_lateness_hours(context)
            cutoff = _runtime_findings_cutoff(event_occurred_at, lateness_hours)
            late_for_runtime_findings = now > cutoff
        seq = self._event_repo.max_sequence_number(
            execution_id, context.organization_id, context.project_id
        ) + 1

        event = AgentExecutionEvent(
            event_id=str(uuid4()),
            execution_id=execution_id,
            organization_id=context.organization_id,
            project_id=context.project_id,
            event_type=event_type,
            sequence_number=seq,
            occurred_at=event_occurred_at,
            received_at=now,
            late_for_runtime_findings=late_for_runtime_findings,
            runtime_findings_finalization_cutoff_at=cutoff,
            runtime_findings_lateness_policy_hours=lateness_hours,
            correlation_id=correlation_id or execution.correlation_id,
            causation_id=causation_id,
            actor_id=actor_id,
            actor_type=actor_type,
            workflow_step=workflow_step,
            tool_call_context=tool_call_context,
            resource_references=tuple(resource_references or []),
            evidence_references=tuple(evidence_references or []),
            attributes=attributes,
            event_schema_version="1",
        )

        return self._event_repo.save(event, idempotency_key=idempotency_key)

    def _validate_workflow_step_transition(
        self,
        execution_id: str,
        event_type: EventType,
        workflow_step: WorkflowStep | None,
        context: TenantContext,
    ) -> None:
        """Validate durable step lifecycle and same-execution nesting.

        The event stream is the only workflow structure retained by the
        control plane.  Looking up prior events in the same tenant-scoped
        execution proves parent references cannot cross executions without
        introducing a parallel workflow datastore.
        """
        if event_type is not EventType.WORKFLOW_STEP:
            if workflow_step is not None:
                raise ValueError(
                    "workflow_step evidence is valid only for WORKFLOW_STEP events."
                )
            return
        if not isinstance(workflow_step, WorkflowStep):
            raise TypeError(
                "WORKFLOW_STEP events require typed workflow_step evidence."
            )

        events = self._event_repo.list_by_execution(
            execution_id,
            context.organization_id,
            context.project_id,
        )
        prior_steps = [
            event.workflow_step
            for event in events
            if event.event_type is EventType.WORKFLOW_STEP
            and event.workflow_step is not None
        ]
        if (
            workflow_step.parent_step_id is not None
            and workflow_step.parent_step_id
            not in {step.step_id for step in prior_steps}
        ):
            raise AgentExecutionInvalidTransition(
                "parent_step_id must reference a workflow step in the same execution."
            )

        same_step = [
            step for step in prior_steps if step.step_id == workflow_step.step_id
        ]
        started = [
            step for step in same_step
            if step.lifecycle is WorkflowStepLifecycle.STARTED
        ]
        terminal = [
            step for step in same_step
            if step.lifecycle
            in {WorkflowStepLifecycle.COMPLETED, WorkflowStepLifecycle.FAILED}
        ]

        if workflow_step.lifecycle is WorkflowStepLifecycle.STARTED:
            if same_step:
                raise AgentExecutionInvalidTransition(
                    f"Workflow step '{workflow_step.step_id}' has already started."
                )
            return

        if not started:
            raise AgentExecutionInvalidTransition(
                f"Workflow step '{workflow_step.step_id}' must start before it terminates."
            )
        if terminal:
            raise AgentExecutionInvalidTransition(
                f"Workflow step '{workflow_step.step_id}' is already terminal."
            )

    def _runtime_findings_lateness_hours(self, context: TenantContext) -> int:
        if self._configuration_service is None:
            return 2
        try:
            from ai_governance.settings_control.domain import SettingContext
            return int(self._configuration_service.get(
                "runtime_findings.reconciliation.allowed_lateness_hours",
                SettingContext(context.organization_id, context.project_id),
            ))
        except Exception:  # noqa: BLE001 - unavailable settings use the safe default.
            return 2

    def _finalization_contract_for(
        self,
        occurred_at: datetime,
        context: TenantContext,
    ) -> ReconciliationWindow | None:
        if self._runtime_finding_repository is None:
            return None
        contracts = self._runtime_finding_repository.finalized_windows_covering(
            occurred_at,
            context.organization_id,
            context.project_id,
        )
        if not contracts:
            return None
        # The event-level boolean means "late for at least one finalized
        # Runtime Findings decision". The earliest cutoff is therefore the
        # conservative, auditable contract to record on the event; a legacy
        # window without a cutoff wins because it cannot safely be reopened.
        return min(
            contracts,
            key=lambda window: window.finalization_cutoff_at or datetime.min.replace(tzinfo=UTC),
        )


    def mark_completed(
        self,
        execution_id: str,
        status: AgentExecutionStatus,
        context: TenantContext,
    ) -> AgentExecution:
        """Mark an execution as terminal (SUCCEEDED, FAILED, CANCELLED)."""
        self._authorize(context, Permission.AGENT_EXECUTION_INGEST)

        execution = self._execution_repo.get(
            execution_id, context.organization_id, context.project_id
        )
        if execution is None:
            raise AgentExecutionNotFound(
                f"Execution '{execution_id}' not found."
            )
        if execution.is_terminal:
            return execution  # Idempotent terminal.

        now = self._clock()
        updated = self._execution_repo.update_status(
            execution_id,
            context.organization_id,
            context.project_id,
            status,
            now,
            execution.version,
        )

        # Emit EXECUTION_COMPLETED event.
        completed_event = AgentExecutionEvent(
            event_id=str(uuid4()),
            execution_id=execution_id,
            organization_id=context.organization_id,
            project_id=context.project_id,
            event_type=EventType.EXECUTION_COMPLETED,
            sequence_number=self._event_repo.max_sequence_number(
                execution_id, context.organization_id, context.project_id
            ) + 1,
            occurred_at=now,
            received_at=now,
            correlation_id=execution.correlation_id,
            causation_id=None,
            actor_id=execution.agent_id,
            actor_type=ActorType.SYSTEM,
            resource_references=(),
            evidence_references=(),
            attributes={
                "final_status": status.value,
                "duration_seconds": execution.duration_seconds,
            },
            event_schema_version="1",
        )
        self._event_repo.save(completed_event)
        return updated

    # -- Reads ----------------------------------------------------------------

    def get_execution(
        self,
        execution_id: str,
        context: TenantContext,
    ) -> AgentExecution | None:
        """Retrieve one execution by its platform-owned ID."""
        self._authorize(context, Permission.AGENT_EXECUTION_READ)
        return self._execution_repo.get(
            execution_id, context.organization_id, context.project_id
        )

    def get_execution_detail(
        self,
        execution_id: str,
        context: TenantContext,
    ) -> AgentExecutionDetail | None:
        """Retrieve an execution with its full event timeline."""
        self._authorize(context, Permission.AGENT_EXECUTION_READ)

        execution = self.get_execution(execution_id, context)
        if execution is None:
            return None

        events = self._event_repo.list_by_execution(
            execution_id, context.organization_id, context.project_id
        )

        # Compute event type counts.
        counts: dict[str, int] = {}
        for event in events:
            key = event.event_type.value
            counts[key] = counts.get(key, 0) + 1

        return AgentExecutionDetail(
            execution=execution,
            events=events,
            event_counts=counts,
        )

    def list_executions(
        self,
        *,
        agent_id: str | None = None,
        status: AgentExecutionStatus | None = None,
        runtime_provider: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        cursor: str | None = None,
        limit: int = 20,
        context: TenantContext,
    ) -> AgentExecutionListPage:
        """List executions with cursor-based pagination."""
        self._authorize(context, Permission.AGENT_EXECUTION_READ)

        filters = AgentExecutionListFilters(
            agent_id=agent_id,
            status=status,
            runtime_provider=runtime_provider,
            created_after=created_after,
            created_before=created_before,
            limit=limit + 1,  # Fetch one extra to determine if there's a next page.
        )

        executions = self._execution_repo.list(
            filters, context.organization_id, context.project_id
        )

        has_more = len(executions) > limit
        if has_more:
            executions = executions[:limit]

        items = []
        for exec_item in executions:
            event_count = self._event_repo.max_sequence_number(
                exec_item.execution_id, context.organization_id, context.project_id
            ) + 1
            items.append(
                AgentExecutionSummary(
                    execution_id=exec_item.execution_id,
                    agent_id=exec_item.agent_id,
                    agent_name=exec_item.agent_name,
                    runtime_provider=exec_item.runtime_provider,
                    external_execution_id=exec_item.external_execution_id,
                    status=exec_item.status.value,
                    started_at=exec_item.started_at,
                    completed_at=exec_item.completed_at,
                    event_count=event_count,
                )
            )

        next_cursor = None
        if has_more and items:
            last_item = items[-1]
            next_cursor = _encode_cursor(
                last_item.started_at.isoformat(), last_item.execution_id
            )

        return AgentExecutionListPage(items=items, next_cursor=next_cursor)

    def list_agents(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        context: TenantContext,
    ) -> AgentExecutionAgentListPage:
        """List agents observed in execution evidence for the current tenant."""
        self._authorize(context, Permission.AGENT_EXECUTION_READ)

        items = self._execution_repo.list_agents(
            AgentExecutionAgentListFilters(limit=limit + 1, offset=offset),
            context.organization_id,
            context.project_id,
        )
        has_more = len(items) > limit
        if has_more:
            items = items[:limit]

        return AgentExecutionAgentListPage(
            items=items,
            next_offset=offset + limit if has_more else None,
        )

    def list_events(
        self,
        execution_id: str,
        context: TenantContext,
        event_type: EventType | None = None,
        limit: int = 100,
    ) -> list[AgentExecutionEvent]:
        """List events for an execution."""
        self._authorize(context, Permission.AGENT_EXECUTION_READ)

        execution = self._execution_repo.get(
            execution_id, context.organization_id, context.project_id
        )
        if execution is None:
            raise AgentExecutionNotFound(
                f"Execution '{execution_id}' not found."
            )

        filters = AgentExecutionEventListFilters(
            event_type=event_type,
            limit=limit,
        )
        return self._event_repo.list_by_execution(
            execution_id, context.organization_id, context.project_id, filters
        )


# -- Helpers ------------------------------------------------------------------


def _idempotency_key_for_start(
    external_execution_id: str,
    runtime_provider: str,
    context: TenantContext,
) -> str:
    """Generate a deterministic idempotency key for execution start."""
    raw = f"{context.organization_id}:{context.project_id or ''}:{runtime_provider}:{external_execution_id}"
    return f"start:{hashlib.sha256(raw.encode()).hexdigest()[:32]}"


def _encode_cursor(timestamp: str, execution_id: str) -> str:
    """Encode a cursor for pagination."""
    raw = f"{timestamp}:{execution_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _runtime_findings_cutoff(occurred_at: datetime, lateness_hours: int) -> datetime:
    cadence_seconds = 48 * 60 * 60
    boundary = datetime.fromtimestamp(
        ((int(occurred_at.astimezone(UTC).timestamp()) // cadence_seconds) + 1) * cadence_seconds,
        UTC,
    )
    return boundary + timedelta(hours=lateness_hours)
