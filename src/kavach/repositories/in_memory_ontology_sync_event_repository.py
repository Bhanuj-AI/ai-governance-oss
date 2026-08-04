from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import RLock

from kavach.ontology.synchronization.events import (
    OntologySyncEvent,
    OntologySyncEventFilter,
    OntologySyncEventRepository,
    OntologySyncEventStatus,
)


class InMemoryOntologySyncEventRepository(OntologySyncEventRepository):
    """
    In-memory ontology sync event repository for tests and local workflows.
    """

    def __init__(self) -> None:
        self._events: dict[str, OntologySyncEvent] = {}
        self._lock = RLock()

    def save(self, event: OntologySyncEvent) -> None:
        with self._lock:
            self._events[event.event_id] = event

    def find_by_id(self, event_id: str) -> OntologySyncEvent | None:
        with self._lock:
            return self._events.get(event_id)

    def list_events(
        self,
        filters: OntologySyncEventFilter | None = None,
        *,
        limit: int = 100,
    ) -> list[OntologySyncEvent]:
        with self._lock:
            events = sorted(
                self._events.values(),
                key=lambda event: (event.created_at, event.event_id),
            )
            if filters is not None:
                events = [event for event in events if _matches_filter(event, filters)]
            return events[:limit]

    def acquire_next(
        self,
        worker_id: str,
        *,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> OntologySyncEvent | None:
        now = now or datetime.now(UTC)
        with self._lock:
            due_events = [
                event
                for event in sorted(
                    self._events.values(),
                    key=lambda item: (item.created_at, item.event_id),
                )
                if _is_due_for_processing(event, now)
            ]
            if not due_events:
                return None

            event = due_events[0]
            acquired = replace(
                event,
                status=OntologySyncEventStatus.PROCESSING,
                updated_at=now,
                locked_by=worker_id,
                lock_expires_at=now + timedelta(seconds=lease_seconds),
            )
            self._events[acquired.event_id] = acquired
            return acquired


def _matches_filter(
    event: OntologySyncEvent,
    filters: OntologySyncEventFilter,
) -> bool:
    return (
        (filters.status is None or event.status == filters.status)
        and (filters.entity_type is None or event.entity_type == filters.entity_type)
        and (filters.entity_id is None or event.entity_id == filters.entity_id)
        and (
            filters.correlation_id is None
            or event.correlation_id == filters.correlation_id
        )
        and (filters.event_type is None or event.event_type == filters.event_type)
        and (
            filters.organization_id is None
            or event.organization_id == filters.organization_id
        )
        and (filters.project_id is None or event.project_id == filters.project_id)
    )


def _is_due_for_processing(
    event: OntologySyncEvent,
    now: datetime,
) -> bool:
    if event.status == OntologySyncEventStatus.PENDING:
        return True
    if event.status == OntologySyncEventStatus.FAILED:
        return event.next_retry_at is None or event.next_retry_at <= now
    if (
        event.status == OntologySyncEventStatus.PROCESSING
        and event.lock_expires_at is not None
    ):
        return event.lock_expires_at <= now
    return False
