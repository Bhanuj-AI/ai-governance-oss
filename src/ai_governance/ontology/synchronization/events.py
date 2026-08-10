from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Protocol
from uuid import uuid4
from threading import Event
from time import monotonic

from ai_governance.ontology.synchronization.diff_reconciliation import (
    DiffBasedOntologyReconciler,
    DiffReconciliationReport,
)
from ai_governance.settings_control.domain import SettingContext
from ai_governance.settings_control.operational import duration_seconds

LOGGER = logging.getLogger(__name__)


class OntologySyncEventStatus(str, Enum):
    """
    Processing lifecycle for an ontology synchronization event.
    """

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class OntologySyncEvent:
    """
    Durable request to reconcile ontology projection state.

    Events identify either one primary ontology entity or a named reconciliation
    scope. Workers process events by invoking `DiffBasedOntologyReconciler`;
    they never mutate graph state directly.
    """

    event_type: str
    entity_type: str
    correlation_id: str
    event_id: str = field(default_factory=lambda: str(uuid4()))
    entity_id: str | None = None
    scope_identifier: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    status: OntologySyncEventStatus = OntologySyncEventStatus.PENDING
    retry_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    error_message: str | None = None
    next_retry_at: datetime | None = None
    last_error: str | None = None
    failed_at: datetime | None = None
    reconciliation_report: Mapping[str, Any] | None = None
    locked_by: str | None = None
    lock_expires_at: datetime | None = None
    organization_id: str = "org_default"
    project_id: str = "project_default"

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError("event_id is required.")
        if not self.event_type:
            raise ValueError("event_type is required.")
        if not self.entity_type:
            raise ValueError("entity_type is required.")
        if not self.correlation_id:
            raise ValueError("correlation_id is required.")
        if self.entity_id is None and self.scope_identifier is None:
            raise ValueError("Either entity_id or scope_identifier is required.")


@dataclass(frozen=True)
class OntologySyncEventFilter:
    """
    Optional filters for operational event listing.
    """

    status: OntologySyncEventStatus | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    correlation_id: str | None = None
    event_type: str | None = None
    organization_id: str | None = None
    project_id: str | None = None


@dataclass(frozen=True)
class OntologySyncMetrics:
    """
    Aggregate event-store metrics for synchronization operations.
    """

    total_events: int
    pending_events: int
    processing_events: int
    completed_events: int
    failed_events: int
    dead_letter_events: int
    cancelled_events: int

    def to_dict(self) -> dict[str, int]:
        return {
            "total_events": self.total_events,
            "pending_events": self.pending_events,
            "processing_events": self.processing_events,
            "completed_events": self.completed_events,
            "failed_events": self.failed_events,
            "dead_letter_events": self.dead_letter_events,
            "cancelled_events": self.cancelled_events,
        }


class OntologySyncEventRepository(Protocol):
    """
    Persistence contract for ontology synchronization events.
    """

    def save(self, event: OntologySyncEvent) -> None: ...

    def find_by_id(self, event_id: str) -> OntologySyncEvent | None: ...

    def list_events(
        self,
        filters: OntologySyncEventFilter | None = None,
        *,
        limit: int = 100,
    ) -> list[OntologySyncEvent]: ...

    def acquire_next(
        self,
        worker_id: str,
        *,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> OntologySyncEvent | None: ...


class OntologySyncEventPublisherProtocol(Protocol):
    """
    Minimal publisher protocol used by domain services.
    """

    def publish_entity_event(
        self,
        event_type: str,
        *,
        entity_type: str,
        entity_id: str,
        correlation_id: str | None = None,
        scope_identifier: str | None = None,
        payload: Mapping[str, Any] | None = None,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> OntologySyncEvent: ...

    def publish_scope_event(
        self,
        event_type: str,
        *,
        entity_type: str,
        scope_identifier: str,
        correlation_id: str | None = None,
        payload: Mapping[str, Any] | None = None,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> OntologySyncEvent: ...


class OntologySyncEventPublisher:
    """
    Publishes durable synchronization events after domain state changes.
    """

    def __init__(
        self,
        repository: OntologySyncEventRepository,
        *,
        id_generator: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
        configuration_service=None,
    ) -> None:
        self._repository = repository
        self._id_generator = id_generator or (lambda: str(uuid4()))
        self._clock = clock or (lambda: datetime.now(UTC))
        self._configuration_service = configuration_service

    def publish_entity_event(
        self,
        event_type: str,
        *,
        entity_type: str,
        entity_id: str,
        correlation_id: str | None = None,
        scope_identifier: str | None = None,
        payload: Mapping[str, Any] | None = None,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> OntologySyncEvent:
        """
        Record a request to reconcile one primary ontology entity.
        """

        now = self._clock()
        event = OntologySyncEvent(
            event_id=self._id_generator(),
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            scope_identifier=scope_identifier,
            correlation_id=correlation_id or self._id_generator(),
            payload=payload or {},
            created_at=now,
            updated_at=now,
            organization_id=organization_id,
            project_id=project_id,
        )
        self._repository.save(event)
        return event

    def publish_scope_event(
        self,
        event_type: str,
        *,
        entity_type: str,
        scope_identifier: str,
        correlation_id: str | None = None,
        payload: Mapping[str, Any] | None = None,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> OntologySyncEvent:
        """
        Record a request to reconcile all entities in a named scope.
        """

        now = self._clock()
        event = OntologySyncEvent(
            event_id=self._id_generator(),
            event_type=event_type,
            entity_type=entity_type,
            scope_identifier=scope_identifier,
            correlation_id=correlation_id or self._id_generator(),
            payload=payload or {},
            created_at=now,
            updated_at=now,
            organization_id=organization_id,
            project_id=project_id,
        )
        self._repository.save(event)
        return event


@dataclass(frozen=True)
class OntologySyncRetryPolicy:
    """
    Retry policy for transient synchronization event failures.
    """

    max_retries: int = 3
    base_delay_seconds: int = 30
    max_delay_seconds: int = 900

    def next_retry_at(self, retry_count: int, now: datetime) -> datetime:
        delay = min(
            self.base_delay_seconds * (2 ** max(retry_count - 1, 0)),
            self.max_delay_seconds,
        )
        return now + timedelta(seconds=delay)


class OntologySyncProcessingError(Exception):
    """
    Error raised when an event cannot be processed.
    """

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = True,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable


class OntologySynchronizationWorker:
    """
    Background worker that turns sync events into diff reconciliation runs.
    """

    def __init__(
        self,
        repository: OntologySyncEventRepository,
        reconciler: DiffBasedOntologyReconciler,
        *,
        worker_id: str = "ontology-sync-worker",
        retry_policy: OntologySyncRetryPolicy | None = None,
        lease_seconds: int = 60,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._reconciler = reconciler
        self._worker_id = worker_id
        self._retry_policy = retry_policy or OntologySyncRetryPolicy()
        self._lease_seconds = lease_seconds
        self._clock = clock or (lambda: datetime.now(UTC))
        # Configuration is optional; standalone workers use the safe default
        # projection and reconciliation intervals in ``run_forever``.
        self._configuration_service = None

    def process_next(self) -> OntologySyncEvent | None:
        """
        Process one pending or retryable event if any are due.
        """

        event = self._repository.acquire_next(
            self._worker_id,
            lease_seconds=self._lease_seconds,
            now=self._clock(),
        )
        if event is None:
            return None

        try:
            report = self._run_reconciliation(event)
        except OntologySyncProcessingError as exc:
            return self._mark_failed(event, str(exc), retryable=exc.retryable)
        except Exception as exc:
            return self._mark_failed(event, str(exc), retryable=True)

        metrics = report.metrics.to_dict()
        if report.metrics.repair_failures:
            message = (
                "Reconciliation completed with "
                f"{report.metrics.repair_failures} repair failure(s)."
            )
            return self._mark_failed(event, message, retryable=True)

        completed = replace(
            event,
            status=OntologySyncEventStatus.COMPLETED,
            updated_at=self._clock(),
            completed_at=self._clock(),
            error_message=None,
            last_error=None,
            failed_at=None,
            next_retry_at=None,
            reconciliation_report=metrics,
            locked_by=None,
            lock_expires_at=None,
        )
        self._repository.save(completed)
        LOGGER.info(
            "Ontology synchronization event completed: event_id=%s metrics=%s",
            completed.event_id,
            metrics,
        )
        return completed

    def process_batch(self, limit: int = 100) -> list[OntologySyncEvent]:
        """
        Process up to `limit` due events.
        """

        processed: list[OntologySyncEvent] = []
        for _ in range(limit):
            event = self.process_next()
            if event is None:
                break
            processed.append(event)
        return processed

    def run_forever(
        self,
        stop_event: Event,
        *,
        context: SettingContext | None = None,
        batch_size: int = 100,
    ) -> None:
        """Run projection batches and periodic full reconciliation until stopped."""
        context = context or SettingContext()
        next_reconciliation = monotonic()
        while not stop_event.is_set():
            self.process_batch(batch_size)
            if self._configuration_service is None:
                projection_interval = 30.0
                reconciliation_interval = 300.0
            else:
                projection_interval = duration_seconds(
                    self._configuration_service.get(
                        "ontology.projection_interval", context
                    )
                )
                reconciliation_interval = duration_seconds(
                    self._configuration_service.get(
                        "ontology.reconciliation_interval", context
                    )
                )
            now = monotonic()
            if now >= next_reconciliation:
                self._reconciler.reconcile_all()
                next_reconciliation = now + reconciliation_interval
            stop_event.wait(projection_interval)

    def _run_reconciliation(
        self,
        event: OntologySyncEvent,
    ) -> DiffReconciliationReport:
        if event.entity_id is not None:
            return self._reconciler.reconcile_entity(
                event.entity_type,
                event.entity_id,
            )
        if event.scope_identifier is not None:
            return self._reconciler.reconcile_scope(event.scope_identifier)
        raise OntologySyncProcessingError(
            "Event has neither entity_id nor scope_identifier.",
            retryable=False,
        )

    def _mark_failed(
        self,
        event: OntologySyncEvent,
        message: str,
        *,
        retryable: bool,
    ) -> OntologySyncEvent:
        now = self._clock()
        retry_count = event.retry_count + 1
        should_retry = retryable and retry_count <= self._retry_policy.max_retries
        failed = replace(
            event,
            status=(
                OntologySyncEventStatus.FAILED
                if should_retry
                else OntologySyncEventStatus.DEAD_LETTER
            ),
            retry_count=retry_count,
            updated_at=now,
            completed_at=None if should_retry else now,
            error_message=message,
            last_error=message,
            failed_at=now,
            next_retry_at=(
                self._retry_policy.next_retry_at(retry_count, now)
                if should_retry
                else None
            ),
            locked_by=None,
            lock_expires_at=None,
        )
        self._repository.save(failed)
        LOGGER.warning(
            "Ontology synchronization event failed: event_id=%s status=%s error=%s",
            failed.event_id,
            failed.status.value,
            message,
        )
        return failed


class OntologySyncEventService:
    """
    Operational facade for synchronization event status APIs.
    """

    def __init__(
        self,
        repository: OntologySyncEventRepository,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(UTC))

    def list_events(
        self,
        filters: OntologySyncEventFilter | None = None,
        *,
        limit: int = 100,
    ) -> list[OntologySyncEvent]:
        return self._repository.list_events(filters, limit=limit)

    def get_event(
        self,
        event_id: str,
        organization_id: str | None = None,
        project_id: str | None = None,
    ) -> OntologySyncEvent:
        event = self._repository.find_by_id(event_id)
        if (
            event is None
            or (
                organization_id is not None and event.organization_id != organization_id
            )
            or (project_id is not None and event.project_id != project_id)
        ):
            raise KeyError(f"Ontology sync event '{event_id}' was not found.")
        return event

    def retry_event(
        self,
        event_id: str,
        organization_id: str | None = None,
        project_id: str | None = None,
    ) -> OntologySyncEvent:
        event = self.get_event(event_id, organization_id, project_id)
        if event.status not in {
            OntologySyncEventStatus.FAILED,
            OntologySyncEventStatus.DEAD_LETTER,
        }:
            raise ValueError("Only failed or dead-letter events can be retried.")
        retried = replace(
            event,
            status=OntologySyncEventStatus.PENDING,
            updated_at=self._clock(),
            completed_at=None,
            error_message=None,
            next_retry_at=None,
            locked_by=None,
            lock_expires_at=None,
        )
        self._repository.save(retried)
        return retried

    def cancel_event(
        self,
        event_id: str,
        organization_id: str | None = None,
        project_id: str | None = None,
    ) -> OntologySyncEvent:
        event = self.get_event(event_id, organization_id, project_id)
        if event.status != OntologySyncEventStatus.PENDING:
            raise ValueError("Only pending events can be cancelled.")
        now = self._clock()
        cancelled = replace(
            event,
            status=OntologySyncEventStatus.CANCELLED,
            updated_at=now,
            completed_at=now,
            error_message="Cancelled by operator.",
            locked_by=None,
            lock_expires_at=None,
        )
        self._repository.save(cancelled)
        return cancelled

    def metrics(
        self, organization_id: str | None = None, project_id: str | None = None
    ) -> OntologySyncMetrics:
        events = self._repository.list_events(
            OntologySyncEventFilter(
                organization_id=organization_id, project_id=project_id
            ),
            limit=10_000,
        )
        by_status = {
            status: sum(1 for event in events if event.status == status)
            for status in OntologySyncEventStatus
        }
        return OntologySyncMetrics(
            total_events=len(events),
            pending_events=by_status[OntologySyncEventStatus.PENDING],
            processing_events=by_status[OntologySyncEventStatus.PROCESSING],
            completed_events=by_status[OntologySyncEventStatus.COMPLETED],
            failed_events=by_status[OntologySyncEventStatus.FAILED],
            dead_letter_events=by_status[OntologySyncEventStatus.DEAD_LETTER],
            cancelled_events=by_status[OntologySyncEventStatus.CANCELLED],
        )
