"""PostgreSQL repository for durable ontology-projection events."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, final

from ai_governance.databases.postgres.database import PostgresDatabase
from ai_governance.ontology.synchronization.events import (
    OntologySyncEvent,
    OntologySyncEventFilter,
    OntologySyncEventRepository,
    OntologySyncEventStatus,
)
from psycopg.types.json import Jsonb


@final
class PostgresOntologySyncEventRepository(OntologySyncEventRepository):
    """Use ``SKIP LOCKED`` so sync workers can safely scale horizontally."""

    _SELECT_COLUMNS = """
    SELECT event_id, event_type, entity_type, entity_id, scope_identifier,
           correlation_id, payload_json::text AS payload_json, status, retry_count,
           created_at::text AS created_at, updated_at::text AS updated_at,
           completed_at::text AS completed_at, error_message,
           next_retry_at::text AS next_retry_at, last_error,
           failed_at::text AS failed_at,
           reconciliation_report_json::text AS reconciliation_report_json,
           locked_by, lock_expires_at::text AS lock_expires_at,
           organization_id, project_id
    FROM ontology_sync_event
    """

    _UPSERT_SQL = """
    INSERT INTO ontology_sync_event (
        event_id, event_type, entity_type, entity_id, scope_identifier,
        correlation_id, payload_json, status, retry_count, created_at, updated_at,
        completed_at, error_message, next_retry_at, last_error, failed_at,
        reconciliation_report_json, locked_by, lock_expires_at, organization_id,
        project_id
    ) VALUES (
        %(event_id)s, %(event_type)s, %(entity_type)s, %(entity_id)s,
        %(scope_identifier)s, %(correlation_id)s, %(payload_json)s, %(status)s,
        %(retry_count)s, %(created_at)s, %(updated_at)s, %(completed_at)s,
        %(error_message)s, %(next_retry_at)s, %(last_error)s, %(failed_at)s,
        %(reconciliation_report_json)s, %(locked_by)s, %(lock_expires_at)s,
        %(organization_id)s, %(project_id)s
    ) ON CONFLICT(event_id) DO UPDATE SET
        event_type=EXCLUDED.event_type, entity_type=EXCLUDED.entity_type,
        entity_id=EXCLUDED.entity_id, scope_identifier=EXCLUDED.scope_identifier,
        correlation_id=EXCLUDED.correlation_id, payload_json=EXCLUDED.payload_json,
        status=EXCLUDED.status, retry_count=EXCLUDED.retry_count,
        updated_at=EXCLUDED.updated_at, completed_at=EXCLUDED.completed_at,
        error_message=EXCLUDED.error_message, next_retry_at=EXCLUDED.next_retry_at,
        last_error=EXCLUDED.last_error, failed_at=EXCLUDED.failed_at,
        reconciliation_report_json=EXCLUDED.reconciliation_report_json,
        locked_by=EXCLUDED.locked_by, lock_expires_at=EXCLUDED.lock_expires_at,
        organization_id=EXCLUDED.organization_id, project_id=EXCLUDED.project_id
    """

    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def save(self, event: OntologySyncEvent) -> None:
        with self._database.connect() as connection:
            try:
                connection.execute(self._UPSERT_SQL, _to_record(event))
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def find_by_id(self, event_id: str) -> OntologySyncEvent | None:
        with self._database.connect() as connection:
            row = connection.execute(
                f"{self._SELECT_COLUMNS} WHERE event_id=%s", (event_id,)
            ).fetchone()
        return _from_record(row) if row else None

    def list_events(
        self,
        filters: OntologySyncEventFilter | None = None,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[OntologySyncEvent]:
        clauses: list[str] = []
        parameters: dict[str, object] = {"limit": limit, "offset": offset}
        if filters:
            for name, value in (
                ("status", filters.status.value if filters.status else None),
                ("entity_type", filters.entity_type),
                ("entity_id", filters.entity_id),
                ("correlation_id", filters.correlation_id),
                ("event_type", filters.event_type),
                ("organization_id", filters.organization_id),
                ("project_id", filters.project_id),
            ):
                if value is not None:
                    clauses.append(f"{name}=%({name})s")
                    parameters[name] = value
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._database.connect() as connection:
            rows = connection.execute(
                f"{self._SELECT_COLUMNS} {where} "
                "ORDER BY created_at DESC, event_id DESC "
                "LIMIT %(limit)s OFFSET %(offset)s",
                parameters,
            ).fetchall()
        return [_from_record(row) for row in rows]

    def acquire_next(
        self,
        worker_id: str,
        *,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> OntologySyncEvent | None:
        now = now or datetime.now(UTC)
        expires_at = now + timedelta(seconds=lease_seconds)
        query = """
            WITH candidate AS (
                SELECT event_id FROM ontology_sync_event
                WHERE status=%(pending)s
                   OR (status=%(failed)s AND (next_retry_at IS NULL OR next_retry_at <= %(now)s))
                   OR (status=%(processing)s AND lock_expires_at IS NOT NULL AND lock_expires_at <= %(now)s)
                ORDER BY created_at, event_id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE ontology_sync_event AS event
            SET status=%(processing)s, updated_at=%(now)s, locked_by=%(worker_id)s,
                lock_expires_at=%(expires_at)s
            FROM candidate
            WHERE event.event_id=candidate.event_id
            RETURNING event.event_id, event.event_type, event.entity_type,
                event.entity_id, event.scope_identifier, event.correlation_id,
                event.payload_json::text AS payload_json, event.status,
                event.retry_count, event.created_at::text AS created_at,
                event.updated_at::text AS updated_at,
                event.completed_at::text AS completed_at, event.error_message,
                event.next_retry_at::text AS next_retry_at, event.last_error,
                event.failed_at::text AS failed_at,
                event.reconciliation_report_json::text AS reconciliation_report_json,
                event.locked_by, event.lock_expires_at::text AS lock_expires_at,
                event.organization_id, event.project_id
        """
        with self._database.connect() as connection:
            row = connection.execute(
                query,
                {
                    "pending": OntologySyncEventStatus.PENDING.value,
                    "failed": OntologySyncEventStatus.FAILED.value,
                    "processing": OntologySyncEventStatus.PROCESSING.value,
                    "now": now,
                    "worker_id": worker_id,
                    "expires_at": expires_at,
                },
            ).fetchone()
            connection.commit()
        return _from_record(row) if row else None


def _to_record(event: OntologySyncEvent) -> dict[str, object]:
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "scope_identifier": event.scope_identifier,
        "correlation_id": event.correlation_id,
        "payload_json": Jsonb(dict(event.payload)),
        "status": event.status.value,
        "retry_count": event.retry_count,
        "created_at": event.created_at,
        "updated_at": event.updated_at,
        "completed_at": event.completed_at,
        "error_message": event.error_message,
        "next_retry_at": event.next_retry_at,
        "last_error": event.last_error,
        "failed_at": event.failed_at,
        "reconciliation_report_json": (
            Jsonb(dict(event.reconciliation_report))
            if event.reconciliation_report is not None
            else None
        ),
        "locked_by": event.locked_by,
        "lock_expires_at": event.lock_expires_at,
        "organization_id": event.organization_id,
        "project_id": event.project_id,
    }


def _from_record(row: Mapping[str, Any]) -> OntologySyncEvent:
    return OntologySyncEvent(
        event_id=row["event_id"],
        event_type=row["event_type"],
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        scope_identifier=row["scope_identifier"],
        correlation_id=row["correlation_id"],
        payload=json.loads(row["payload_json"] or "{}"),
        status=OntologySyncEventStatus(row["status"]),
        retry_count=row["retry_count"],
        created_at=_datetime(row["created_at"]),
        updated_at=_datetime(row["updated_at"]),
        completed_at=_datetime(row["completed_at"]),
        error_message=row["error_message"],
        next_retry_at=_datetime(row["next_retry_at"]),
        last_error=row["last_error"],
        failed_at=_datetime(row["failed_at"]),
        reconciliation_report=(
            json.loads(row["reconciliation_report_json"])
            if row["reconciliation_report_json"] is not None
            else None
        ),
        locked_by=row["locked_by"],
        lock_expires_at=_datetime(row["lock_expires_at"]),
        organization_id=row["organization_id"],
        project_id=row["project_id"],
    )


def _datetime(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
