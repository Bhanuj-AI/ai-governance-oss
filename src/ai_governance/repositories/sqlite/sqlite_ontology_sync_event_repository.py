from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any, final

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.ontology.synchronization.events import (
    OntologySyncEvent,
    OntologySyncEventFilter,
    OntologySyncEventRepository,
    OntologySyncEventStatus,
)


@final
class SQLiteOntologySyncEventRepository(OntologySyncEventRepository):
    """
    SQLite implementation of the ontology sync event repository.
    """

    _INSERT_SQL = """
    INSERT OR REPLACE INTO ontology_sync_event (
        event_id,
        event_type,
        entity_type,
        entity_id,
        scope_identifier,
        correlation_id,
        payload_json,
        status,
        retry_count,
        created_at,
        updated_at,
        completed_at,
        error_message,
        next_retry_at,
        last_error,
        failed_at,
        reconciliation_report_json,
        locked_by,
        lock_expires_at
        , organization_id
        , project_id
    )
    VALUES (
        :event_id,
        :event_type,
        :entity_type,
        :entity_id,
        :scope_identifier,
        :correlation_id,
        :payload_json,
        :status,
        :retry_count,
        :created_at,
        :updated_at,
        :completed_at,
        :error_message,
        :next_retry_at,
        :last_error,
        :failed_at,
        :reconciliation_report_json,
        :locked_by,
        :lock_expires_at
        , :organization_id
        , :project_id
    )
    """

    _SELECT_COLUMNS = """
    SELECT
        event_id,
        event_type,
        entity_type,
        entity_id,
        scope_identifier,
        correlation_id,
        payload_json,
        status,
        retry_count,
        created_at,
        updated_at,
        completed_at,
        error_message,
        next_retry_at,
        last_error,
        failed_at,
        reconciliation_report_json,
        locked_by,
        lock_expires_at
        , organization_id
        , project_id
    FROM ontology_sync_event
    """

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def save(self, event: OntologySyncEvent) -> None:
        with self._database.connect() as connection:
            try:
                connection.execute(self._INSERT_SQL, _to_record(event))
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def find_by_id(self, event_id: str) -> OntologySyncEvent | None:
        with self._database.connect() as connection:
            row = connection.execute(
                f"{self._SELECT_COLUMNS} WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return _from_record(row) if row is not None else None

    def list_events(
        self,
        filters: OntologySyncEventFilter | None = None,
        *,
        limit: int = 100,
    ) -> list[OntologySyncEvent]:
        where: list[str] = []
        values: list[Any] = []
        if filters is not None:
            if filters.status is not None:
                where.append("status = ?")
                values.append(filters.status.value)
            if filters.entity_type is not None:
                where.append("entity_type = ?")
                values.append(filters.entity_type)
            if filters.entity_id is not None:
                where.append("entity_id = ?")
                values.append(filters.entity_id)
            if filters.correlation_id is not None:
                where.append("correlation_id = ?")
                values.append(filters.correlation_id)
            if filters.event_type is not None:
                where.append("event_type = ?")
                values.append(filters.event_type)
            if filters.organization_id is not None:
                where.append("organization_id = ?")
                values.append(filters.organization_id)
            if filters.project_id is not None:
                where.append("project_id = ?")
                values.append(filters.project_id)

        where_clause = f"WHERE {' AND '.join(where)} " if where else ""
        values.append(limit)
        with self._database.connect() as connection:
            rows = connection.execute(
                f"{self._SELECT_COLUMNS} "
                f"{where_clause}"
                "ORDER BY created_at, event_id "
                "LIMIT ?",
                values,
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
        with self._database.connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    f"{self._SELECT_COLUMNS} "
                    "WHERE "
                    "status = ? OR "
                    "(status = ? AND (next_retry_at IS NULL OR next_retry_at <= ?)) "
                    "OR (status = ? AND lock_expires_at IS NOT NULL AND lock_expires_at <= ?) "
                    "ORDER BY created_at, event_id "
                    "LIMIT 1",
                    (
                        OntologySyncEventStatus.PENDING.value,
                        OntologySyncEventStatus.FAILED.value,
                        _datetime_to_text(now),
                        OntologySyncEventStatus.PROCESSING.value,
                        _datetime_to_text(now),
                    ),
                ).fetchone()

                if row is None:
                    connection.commit()
                    return None

                event = _from_record(row)
                acquired = replace(
                    event,
                    status=OntologySyncEventStatus.PROCESSING,
                    updated_at=now,
                    locked_by=worker_id,
                    lock_expires_at=now + timedelta(seconds=lease_seconds),
                )
                connection.execute(self._INSERT_SQL, _to_record(acquired))
                connection.commit()
                return acquired
            except Exception:
                connection.rollback()
                raise


def _to_record(event: OntologySyncEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "scope_identifier": event.scope_identifier,
        "correlation_id": event.correlation_id,
        "payload_json": json.dumps(dict(event.payload), sort_keys=True),
        "status": event.status.value,
        "retry_count": event.retry_count,
        "created_at": _datetime_to_text(event.created_at),
        "updated_at": _datetime_to_text(event.updated_at),
        "completed_at": _datetime_to_text(event.completed_at),
        "error_message": event.error_message,
        "next_retry_at": _datetime_to_text(event.next_retry_at),
        "last_error": event.last_error,
        "failed_at": _datetime_to_text(event.failed_at),
        "reconciliation_report_json": (
            json.dumps(dict(event.reconciliation_report), sort_keys=True)
            if event.reconciliation_report is not None
            else None
        ),
        "locked_by": event.locked_by,
        "lock_expires_at": _datetime_to_text(event.lock_expires_at),
        "organization_id": event.organization_id,
        "project_id": event.project_id,
    }


def _from_record(row: Any) -> OntologySyncEvent:
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
        created_at=_text_to_datetime(row["created_at"]),
        updated_at=_text_to_datetime(row["updated_at"]),
        completed_at=_text_to_datetime(row["completed_at"]),
        error_message=row["error_message"],
        next_retry_at=_text_to_datetime(row["next_retry_at"]),
        last_error=row["last_error"],
        failed_at=_text_to_datetime(row["failed_at"]),
        reconciliation_report=(
            json.loads(row["reconciliation_report_json"])
            if row["reconciliation_report_json"] is not None
            else None
        ),
        locked_by=row["locked_by"],
        lock_expires_at=_text_to_datetime(row["lock_expires_at"]),
        organization_id=row["organization_id"],
        project_id=row["project_id"],
    )


def _datetime_to_text(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _text_to_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
