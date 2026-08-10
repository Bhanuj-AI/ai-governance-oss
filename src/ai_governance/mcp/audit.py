from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextvars import ContextVar, Token
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from collections.abc import Mapping
from typing import Any, Protocol
from uuid import uuid4

from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.databases.postgres.database import PostgresDatabase
from ai_governance.mcp.dto import WriteEnvelope
from ai_governance.version import __version__


SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "password",
    "provider_config",
    "secret",
    "token",
}

_AUDIT_PERSISTENCE_ENABLED: ContextVar[bool] = ContextVar(
    "mcp_audit_persistence_enabled", default=True
)


def set_audit_persistence(enabled: bool) -> Token:
    return _AUDIT_PERSISTENCE_ENABLED.set(enabled)


def reset_audit_persistence(token: Token) -> None:
    _AUDIT_PERSISTENCE_ENABLED.reset(token)


@dataclass(frozen=True)
class MCPExecutionAuditRecord:
    """
    MCP write-operation audit record.
    """

    audit_id: str
    request_id: str
    correlation_id: str
    tool_name: str
    tool_version: str
    actor_id: str
    actor_type: str
    agent_name: str | None
    agent_session_id: str | None
    client_name: str | None
    client_version: str | None
    idempotency_key: str
    operation_type: str
    resource_type: str
    resource_id: str | None
    request_hash: str
    request_summary: dict[str, Any]
    resolved_versions: dict[str, Any]
    reason: str
    dry_run: bool
    status: str
    job_id: str | None
    result_reference: str | None
    error_code: str | None
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None
    duration_ms: float | None
    metadata: dict[str, Any] = field(default_factory=dict)
    organization_id: str = "org_default"
    project_id: str = "project_default"


class MCPExecutionAuditStore(Protocol):
    """
    Persistence boundary for MCP execution audit rows.
    """

    def save(self, record: MCPExecutionAuditRecord) -> None:
        """
        Persist the latest state for an audit record.
        """

    def list_records(self) -> list[MCPExecutionAuditRecord]:
        """
        Return persisted audit records.
        """


class InMemoryMCPExecutionAuditStore:
    """
    Test-friendly MCP execution audit store.
    """

    def __init__(self) -> None:
        self._records: dict[str, MCPExecutionAuditRecord] = {}

    def save(self, record: MCPExecutionAuditRecord) -> None:
        self._records[record.audit_id] = record

    def list_records(self) -> list[MCPExecutionAuditRecord]:
        return sorted(
            self._records.values(),
            key=lambda record: (record.started_at, record.audit_id),
        )


class SQLiteMCPExecutionAuditStore:
    """
    SQLite-backed MCP execution audit store.
    """

    _UPSERT_SQL = """
    INSERT OR REPLACE INTO mcp_execution_audit (
        audit_id,
        request_id,
        correlation_id,
        tool_name,
        tool_version,
        actor_id,
        actor_type,
        agent_name,
        agent_session_id,
        client_name,
        client_version,
        idempotency_key,
        operation_type,
        resource_type,
        resource_id,
        request_hash,
        request_summary_json,
        resolved_versions_json,
        reason,
        dry_run,
        status,
        job_id,
        result_reference,
        error_code,
        error_message,
        started_at,
        completed_at,
        duration_ms,
        metadata_json
        , organization_id
        , project_id
    )
    VALUES (
        :audit_id,
        :request_id,
        :correlation_id,
        :tool_name,
        :tool_version,
        :actor_id,
        :actor_type,
        :agent_name,
        :agent_session_id,
        :client_name,
        :client_version,
        :idempotency_key,
        :operation_type,
        :resource_type,
        :resource_id,
        :request_hash,
        :request_summary_json,
        :resolved_versions_json,
        :reason,
        :dry_run,
        :status,
        :job_id,
        :result_reference,
        :error_code,
        :error_message,
        :started_at,
        :completed_at,
        :duration_ms,
        :metadata_json
        , :organization_id
        , :project_id
    )
    """

    _SELECT_SQL = """
    SELECT
        audit_id,
        request_id,
        correlation_id,
        tool_name,
        tool_version,
        actor_id,
        actor_type,
        agent_name,
        agent_session_id,
        client_name,
        client_version,
        idempotency_key,
        operation_type,
        resource_type,
        resource_id,
        request_hash,
        request_summary_json,
        resolved_versions_json,
        reason,
        dry_run,
        status,
        job_id,
        result_reference,
        error_code,
        error_message,
        started_at,
        completed_at,
        duration_ms,
        metadata_json
        , organization_id
        , project_id
    FROM mcp_execution_audit
    ORDER BY started_at, audit_id
    """

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def save(self, record: MCPExecutionAuditRecord) -> None:
        with self._database.connect() as connection:
            try:
                connection.execute(self._UPSERT_SQL, _to_sqlite_record(record))
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def list_records(self) -> list[MCPExecutionAuditRecord]:
        with self._database.connect() as connection:
            rows = connection.execute(self._SELECT_SQL).fetchall()

        return [_from_sqlite_record(row) for row in rows]


class PostgresMCPExecutionAuditStore:
    """PostgreSQL-backed MCP audit evidence for multi-node deployments."""

    _UPSERT_SQL = """
    INSERT INTO mcp_execution_audit (
        audit_id, request_id, correlation_id, tool_name, tool_version, actor_id,
        actor_type, agent_name, agent_session_id, client_name, client_version,
        idempotency_key, operation_type, resource_type, resource_id, request_hash,
        request_summary_json, resolved_versions_json, reason, dry_run, status,
        job_id, result_reference, error_code, error_message, started_at,
        completed_at, duration_ms, metadata_json, organization_id, project_id
    ) VALUES (
        %(audit_id)s, %(request_id)s, %(correlation_id)s, %(tool_name)s,
        %(tool_version)s, %(actor_id)s, %(actor_type)s, %(agent_name)s,
        %(agent_session_id)s, %(client_name)s, %(client_version)s,
        %(idempotency_key)s, %(operation_type)s, %(resource_type)s,
        %(resource_id)s, %(request_hash)s, %(request_summary_json)s,
        %(resolved_versions_json)s, %(reason)s, %(dry_run)s, %(status)s,
        %(job_id)s, %(result_reference)s, %(error_code)s, %(error_message)s,
        %(started_at)s, %(completed_at)s, %(duration_ms)s, %(metadata_json)s,
        %(organization_id)s, %(project_id)s
    ) ON CONFLICT(audit_id) DO UPDATE SET
        request_id=EXCLUDED.request_id, correlation_id=EXCLUDED.correlation_id,
        tool_name=EXCLUDED.tool_name, tool_version=EXCLUDED.tool_version,
        actor_id=EXCLUDED.actor_id, actor_type=EXCLUDED.actor_type,
        agent_name=EXCLUDED.agent_name, agent_session_id=EXCLUDED.agent_session_id,
        client_name=EXCLUDED.client_name, client_version=EXCLUDED.client_version,
        idempotency_key=EXCLUDED.idempotency_key,
        operation_type=EXCLUDED.operation_type, resource_type=EXCLUDED.resource_type,
        resource_id=EXCLUDED.resource_id, request_hash=EXCLUDED.request_hash,
        request_summary_json=EXCLUDED.request_summary_json,
        resolved_versions_json=EXCLUDED.resolved_versions_json, reason=EXCLUDED.reason,
        dry_run=EXCLUDED.dry_run, status=EXCLUDED.status, job_id=EXCLUDED.job_id,
        result_reference=EXCLUDED.result_reference, error_code=EXCLUDED.error_code,
        error_message=EXCLUDED.error_message, completed_at=EXCLUDED.completed_at,
        duration_ms=EXCLUDED.duration_ms, metadata_json=EXCLUDED.metadata_json,
        organization_id=EXCLUDED.organization_id, project_id=EXCLUDED.project_id
    """

    _SELECT_SQL = """
    SELECT audit_id, request_id, correlation_id, tool_name, tool_version, actor_id,
           actor_type, agent_name, agent_session_id, client_name, client_version,
           idempotency_key, operation_type, resource_type, resource_id, request_hash,
           request_summary_json::text AS request_summary_json,
           resolved_versions_json::text AS resolved_versions_json, reason, dry_run,
           status, job_id, result_reference, error_code, error_message,
           started_at::text AS started_at, completed_at::text AS completed_at,
           duration_ms, metadata_json::text AS metadata_json, organization_id,
           project_id
    FROM mcp_execution_audit
    ORDER BY started_at, audit_id
    """

    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def save(self, record: MCPExecutionAuditRecord) -> None:
        with self._database.connect() as connection:
            try:
                connection.execute(self._UPSERT_SQL, _to_postgres_record(record))
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def list_records(self) -> list[MCPExecutionAuditRecord]:
        with self._database.connect() as connection:
            rows = connection.execute(self._SELECT_SQL).fetchall()
        return [_from_postgres_record(row) for row in rows]


class MCPExecutionAuditLog:
    """
    Durable MCP execution audit log.
    """

    def __init__(
        self,
        store: MCPExecutionAuditStore | None = None,
    ) -> None:
        self._store = store or InMemoryMCPExecutionAuditStore()
        self._non_persisted: set[str] = set()

    @classmethod
    def in_memory(cls) -> MCPExecutionAuditLog:
        return cls(InMemoryMCPExecutionAuditStore())

    @classmethod
    def sqlite(
        cls,
        database_path: str | Path,
    ) -> MCPExecutionAuditLog:
        database = SQLiteDatabase(Path(database_path))
        database.database_path.parent.mkdir(parents=True, exist_ok=True)
        database.initialize()
        return cls(SQLiteMCPExecutionAuditStore(database))

    @classmethod
    def postgres(cls, dsn: str) -> MCPExecutionAuditLog:
        """Build an audit log backed by the PostgreSQL audit schema."""
        database = PostgresDatabase(dsn)
        database.initialize()
        return cls(PostgresMCPExecutionAuditStore(database))

    def start(
        self,
        *,
        tool_name: str,
        operation_type: str,
        resource_type: str,
        resource_id: str | None,
        envelope: WriteEnvelope,
        payload: dict[str, Any],
        resolved_versions: dict[str, Any] | None = None,
    ) -> MCPExecutionAuditRecord:
        now = datetime.now(UTC)
        record = MCPExecutionAuditRecord(
            audit_id=str(uuid4()),
            request_id=envelope.request_id,
            correlation_id=envelope.correlation_id or envelope.request_id,
            tool_name=tool_name,
            tool_version=__version__,
            actor_id=envelope.requested_by,
            actor_type=envelope.actor_type,
            agent_name=envelope.agent_name,
            agent_session_id=envelope.agent_session_id,
            client_name=envelope.client_name,
            client_version=envelope.client_version,
            idempotency_key=envelope.idempotency_key,
            operation_type=operation_type,
            resource_type=resource_type,
            resource_id=resource_id,
            request_hash=request_hash(payload),
            request_summary=safe_summary(payload),
            resolved_versions=dict(resolved_versions or {}),
            reason=envelope.reason,
            dry_run=envelope.dry_run,
            status="STARTED",
            job_id=None,
            result_reference=None,
            error_code=None,
            error_message=None,
            started_at=now,
            completed_at=None,
            duration_ms=None,
            metadata=envelope.audit_metadata(),
            organization_id=_envelope_organization_id(envelope),
            project_id=_envelope_project_id(envelope),
        )
        if _AUDIT_PERSISTENCE_ENABLED.get():
            self._store.save(record)
        else:
            self._non_persisted.add(record.audit_id)
        return record

    def complete(
        self,
        record: MCPExecutionAuditRecord,
        *,
        status: str,
        job_id: str | None = None,
        result_reference: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> MCPExecutionAuditRecord:
        completed_at = datetime.now(UTC)
        completed = replace(
            record,
            status=status,
            job_id=job_id,
            result_reference=result_reference,
            error_code=error_code,
            error_message=error_message,
            completed_at=completed_at,
            duration_ms=(completed_at - record.started_at).total_seconds() * 1000,
        )
        if record.audit_id in self._non_persisted:
            self._non_persisted.discard(record.audit_id)
        else:
            self._store.save(completed)
        return completed

    def save_record(
        self,
        record: MCPExecutionAuditRecord,
    ) -> MCPExecutionAuditRecord:
        """
        Persist a fully materialized audit record.
        """
        self._store.save(record)
        return record

    def get(
        self,
        audit_id: str,
        organization_id: str | None = None,
        project_id: str | None = None,
    ) -> MCPExecutionAuditRecord | None:
        for record in self._store.list_records():
            if (
                record.audit_id == audit_id
                and (
                    organization_id is None or record.organization_id == organization_id
                )
                and (project_id is None or record.project_id == project_id)
            ):
                return record
        return None

    def find_by_request(
        self,
        request_id: str,
    ) -> list[MCPExecutionAuditRecord]:
        return self.list_records(request_id=request_id)

    def find_by_correlation(
        self,
        correlation_id: str,
    ) -> list[MCPExecutionAuditRecord]:
        return self.list_records(correlation_id=correlation_id)

    def all_records(
        self,
    ) -> list[MCPExecutionAuditRecord]:
        """
        Return every persisted audit record without additional filtering.
        """
        return self._store.list_records()

    def list_records(
        self,
        *,
        request_id: str | None = None,
        correlation_id: str | None = None,
        tool_name: str | None = None,
        status: str | None = None,
        actor_id: str | None = None,
        organization_id: str | None = None,
        project_id: str | None = None,
        limit: int = 100,
    ) -> list[MCPExecutionAuditRecord]:
        records = self._store.list_records()
        if organization_id is not None:
            records = [
                record
                for record in records
                if record.organization_id == organization_id
            ]
        if project_id is not None:
            records = [record for record in records if record.project_id == project_id]
        if request_id is not None:
            records = [record for record in records if record.request_id == request_id]
        if correlation_id is not None:
            records = [
                record for record in records if record.correlation_id == correlation_id
            ]
        if tool_name is not None:
            records = [record for record in records if record.tool_name == tool_name]
        if status is not None:
            records = [record for record in records if record.status == status]
        if actor_id is not None:
            records = [record for record in records if record.actor_id == actor_id]
        return records[:limit]

    @staticmethod
    def is_interrupted(
        record: MCPExecutionAuditRecord,
        *,
        older_than_seconds: int,
        now: datetime | None = None,
    ) -> bool:
        if record.status != "STARTED" or record.completed_at is not None:
            return False
        resolved_now = now or datetime.now(UTC)
        return resolved_now - record.started_at > timedelta(
            seconds=older_than_seconds,
        )


def request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def safe_summary(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: (
                "<redacted>" if key.lower() in SENSITIVE_KEYS else safe_summary(value)
            )
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [safe_summary(value) for value in payload]
    return payload


def _to_sqlite_record(
    record: MCPExecutionAuditRecord,
) -> dict[str, Any]:
    return {
        "audit_id": record.audit_id,
        "request_id": record.request_id,
        "correlation_id": record.correlation_id,
        "tool_name": record.tool_name,
        "tool_version": record.tool_version,
        "actor_id": record.actor_id,
        "actor_type": record.actor_type,
        "agent_name": record.agent_name,
        "agent_session_id": record.agent_session_id,
        "client_name": record.client_name,
        "client_version": record.client_version,
        "idempotency_key": record.idempotency_key,
        "operation_type": record.operation_type,
        "resource_type": record.resource_type,
        "resource_id": record.resource_id,
        "request_hash": record.request_hash,
        "request_summary_json": json.dumps(
            record.request_summary,
            sort_keys=True,
        ),
        "resolved_versions_json": json.dumps(
            record.resolved_versions,
            sort_keys=True,
        ),
        "reason": record.reason,
        "dry_run": int(record.dry_run),
        "status": record.status,
        "job_id": record.job_id,
        "result_reference": record.result_reference,
        "error_code": record.error_code,
        "error_message": record.error_message,
        "started_at": _datetime_to_text(record.started_at),
        "completed_at": _optional_datetime_to_text(record.completed_at),
        "duration_ms": record.duration_ms,
        "metadata_json": json.dumps(record.metadata, sort_keys=True),
        "organization_id": record.organization_id,
        "project_id": record.project_id,
    }


def _from_sqlite_record(
    row: sqlite3.Row,
) -> MCPExecutionAuditRecord:
    return MCPExecutionAuditRecord(
        audit_id=str(row["audit_id"]),
        request_id=str(row["request_id"]),
        correlation_id=str(row["correlation_id"]),
        tool_name=str(row["tool_name"]),
        tool_version=str(row["tool_version"]),
        actor_id=str(row["actor_id"]),
        actor_type=str(row["actor_type"]),
        agent_name=row["agent_name"],
        agent_session_id=row["agent_session_id"],
        client_name=row["client_name"],
        client_version=row["client_version"],
        idempotency_key=str(row["idempotency_key"]),
        operation_type=str(row["operation_type"]),
        resource_type=str(row["resource_type"]),
        resource_id=row["resource_id"],
        request_hash=str(row["request_hash"]),
        request_summary=json.loads(row["request_summary_json"]),
        resolved_versions=json.loads(row["resolved_versions_json"]),
        reason=str(row["reason"]),
        dry_run=bool(row["dry_run"]),
        status=str(row["status"]),
        job_id=row["job_id"],
        result_reference=row["result_reference"],
        error_code=row["error_code"],
        error_message=row["error_message"],
        started_at=_datetime_from_text(str(row["started_at"])),
        completed_at=(
            _datetime_from_text(str(row["completed_at"]))
            if row["completed_at"] is not None
            else None
        ),
        duration_ms=row["duration_ms"],
        metadata=json.loads(row["metadata_json"]),
        organization_id=str(row["organization_id"]),
        project_id=str(row["project_id"]),
    )


def _to_postgres_record(record: MCPExecutionAuditRecord) -> dict[str, Any]:
    from psycopg.types.json import Jsonb

    row = _to_sqlite_record(record)
    row["dry_run"] = bool(record.dry_run)
    row["started_at"] = record.started_at
    row["completed_at"] = record.completed_at
    row["request_summary_json"] = Jsonb(record.request_summary)
    row["resolved_versions_json"] = Jsonb(record.resolved_versions)
    row["metadata_json"] = Jsonb(record.metadata)
    return row


def _from_postgres_record(row: Mapping[str, Any]) -> MCPExecutionAuditRecord:
    return MCPExecutionAuditRecord(
        audit_id=str(row["audit_id"]),
        request_id=str(row["request_id"]),
        correlation_id=str(row["correlation_id"]),
        tool_name=str(row["tool_name"]),
        tool_version=str(row["tool_version"]),
        actor_id=str(row["actor_id"]),
        actor_type=str(row["actor_type"]),
        agent_name=row["agent_name"],
        agent_session_id=row["agent_session_id"],
        client_name=row["client_name"],
        client_version=row["client_version"],
        idempotency_key=str(row["idempotency_key"]),
        operation_type=str(row["operation_type"]),
        resource_type=str(row["resource_type"]),
        resource_id=row["resource_id"],
        request_hash=str(row["request_hash"]),
        request_summary=json.loads(row["request_summary_json"]),
        resolved_versions=json.loads(row["resolved_versions_json"]),
        reason=str(row["reason"]),
        dry_run=bool(row["dry_run"]),
        status=str(row["status"]),
        job_id=row["job_id"],
        result_reference=row["result_reference"],
        error_code=row["error_code"],
        error_message=row["error_message"],
        started_at=_datetime_from_text(str(row["started_at"])),
        completed_at=(
            _datetime_from_text(str(row["completed_at"]))
            if row["completed_at"] is not None
            else None
        ),
        duration_ms=row["duration_ms"],
        metadata=json.loads(row["metadata_json"]),
        organization_id=str(row["organization_id"]),
        project_id=str(row["project_id"]),
    )


def _envelope_organization_id(envelope: WriteEnvelope) -> str:
    context = getattr(envelope, "context", None)
    return getattr(context, "organization_id", None) or os.getenv(
        "AI_GOVERNANCE_BOOTSTRAP_ORGANIZATION_ID", "org_default"
    )


def _envelope_project_id(envelope: WriteEnvelope) -> str:
    context = getattr(envelope, "context", None)
    return getattr(context, "project_id", None) or os.getenv(
        "AI_GOVERNANCE_BOOTSTRAP_PROJECT_ID", "project_default"
    )


def _datetime_to_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _optional_datetime_to_text(value: datetime | None) -> str | None:
    return _datetime_to_text(value) if value is not None else None


def _datetime_from_text(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed
