"""Durable, privacy-safe evidence for every MCP tool invocation.

This is deliberately separate from ``mcp.audit``.  The latter proves business
mutations; this module proves that a caller invoked an MCP tool, including
read-only tools and rejected calls.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from ai_governance.databases.postgres.database import PostgresDatabase
from ai_governance.databases.sqlite.database import SQLiteDatabase
from ai_governance.mcp.audit import safe_summary
from ai_governance.version import __version__


@dataclass(frozen=True)
class MCPInvocationAuditRecord:
    invocation_id: str
    request_id: str
    correlation_id: str
    tool_name: str
    tool_version: str
    organization_id: str
    project_id: str | None
    actor_id: str | None
    actor_type: str | None
    client_id: str | None
    status: str
    authorization_decision: str
    request_hash: str
    argument_summary: dict[str, Any]
    response_classification: str | None
    response_hash: str | None
    error_category: str | None
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: float | None = None


class MCPInvocationAuditStore(Protocol):
    def save(self, record: MCPInvocationAuditRecord) -> None: ...

    def list_records(self) -> list[MCPInvocationAuditRecord]: ...


class InMemoryMCPInvocationAuditStore:
    def __init__(self) -> None:
        self._records: dict[str, MCPInvocationAuditRecord] = {}

    def save(self, record: MCPInvocationAuditRecord) -> None:
        self._records[record.invocation_id] = record

    def list_records(self) -> list[MCPInvocationAuditRecord]:
        return sorted(
            self._records.values(), key=lambda row: (row.started_at, row.invocation_id)
        )


class SQLiteMCPInvocationAuditStore:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def save(self, record: MCPInvocationAuditRecord) -> None:
        with self._database.connect() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO mcp_invocation_audit (
                invocation_id, request_id, correlation_id, tool_name, tool_version,
                organization_id, project_id, actor_id, actor_type, client_id, status,
                authorization_decision, request_hash, argument_summary_json,
                response_classification, response_hash, error_category, started_at,
                completed_at, duration_ms) VALUES (
                :invocation_id, :request_id, :correlation_id, :tool_name, :tool_version,
                :organization_id, :project_id, :actor_id, :actor_type, :client_id, :status,
                :authorization_decision, :request_hash, :argument_summary_json,
                :response_classification, :response_hash, :error_category, :started_at,
                :completed_at, :duration_ms)""",
                _sqlite_row(record),
            )
            connection.commit()

    def list_records(self) -> list[MCPInvocationAuditRecord]:
        with self._database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM mcp_invocation_audit ORDER BY started_at, invocation_id"
            ).fetchall()
        return [_from_row(row) for row in rows]


class PostgresMCPInvocationAuditStore:
    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def save(self, record: MCPInvocationAuditRecord) -> None:
        from psycopg.types.json import Jsonb

        row = _postgres_row(record)
        row["argument_summary_json"] = Jsonb(record.argument_summary)
        with self._database.connect() as connection:
            connection.execute(
                """INSERT INTO mcp_invocation_audit (
                invocation_id, request_id, correlation_id, tool_name, tool_version,
                organization_id, project_id, actor_id, actor_type, client_id, status,
                authorization_decision, request_hash, argument_summary_json,
                response_classification, response_hash, error_category, started_at,
                completed_at, duration_ms) VALUES (
                %(invocation_id)s, %(request_id)s, %(correlation_id)s, %(tool_name)s, %(tool_version)s,
                %(organization_id)s, %(project_id)s, %(actor_id)s, %(actor_type)s, %(client_id)s, %(status)s,
                %(authorization_decision)s, %(request_hash)s, %(argument_summary_json)s,
                %(response_classification)s, %(response_hash)s, %(error_category)s, %(started_at)s,
                %(completed_at)s, %(duration_ms)s)
                ON CONFLICT(invocation_id) DO UPDATE SET status=EXCLUDED.status,
                authorization_decision=EXCLUDED.authorization_decision,
                response_classification=EXCLUDED.response_classification,
                response_hash=EXCLUDED.response_hash, error_category=EXCLUDED.error_category,
                completed_at=EXCLUDED.completed_at, duration_ms=EXCLUDED.duration_ms""",
                row,
            )
            connection.commit()

    def list_records(self) -> list[MCPInvocationAuditRecord]:
        with self._database.connect() as connection:
            rows = connection.execute(
                "SELECT invocation_id, request_id, correlation_id, tool_name, tool_version, organization_id, project_id, actor_id, actor_type, client_id, status, authorization_decision, request_hash, argument_summary_json::text AS argument_summary_json, response_classification, response_hash, error_category, started_at::text AS started_at, completed_at::text AS completed_at, duration_ms FROM mcp_invocation_audit ORDER BY started_at, invocation_id"
            ).fetchall()
        return [_from_row(row) for row in rows]


class MCPInvocationAuditLog:
    """Append-only invocation evidence; persistence failures never affect calls."""

    def __init__(self, store: MCPInvocationAuditStore | None = None) -> None:
        self._store = store or InMemoryMCPInvocationAuditStore()

    @classmethod
    def in_memory(cls) -> MCPInvocationAuditLog:
        return cls(InMemoryMCPInvocationAuditStore())

    @classmethod
    def sqlite(cls, database_path: str | Path) -> MCPInvocationAuditLog:
        database = SQLiteDatabase(Path(database_path))
        database.database_path.parent.mkdir(parents=True, exist_ok=True)
        database.initialize()
        return cls(SQLiteMCPInvocationAuditStore(database))

    @classmethod
    def postgres(cls, dsn: str) -> MCPInvocationAuditLog:
        database = PostgresDatabase(dsn)
        database.initialize()
        return cls(PostgresMCPInvocationAuditStore(database))

    def received(
        self,
        *,
        invocation_id: str,
        request_id: str,
        correlation_id: str,
        tool_name: str,
        organization_id: str,
        project_id: str | None,
        actor_id: str | None,
        actor_type: str | None,
        client_id: str | None,
        authorization_decision: str,
        payload: Mapping[str, Any],
    ) -> MCPInvocationAuditRecord:
        record = MCPInvocationAuditRecord(
            invocation_id=invocation_id,
            request_id=request_id,
            correlation_id=correlation_id,
            tool_name=tool_name,
            tool_version=__version__,
            organization_id=organization_id,
            project_id=project_id,
            actor_id=actor_id,
            actor_type=actor_type,
            client_id=client_id,
            status="RECEIVED",
            authorization_decision=authorization_decision,
            request_hash=_hash(payload),
            argument_summary=safe_summary(dict(payload)),
            response_classification=None,
            response_hash=None,
            error_category=None,
            started_at=datetime.now(UTC),
        )
        self._store.save(record)
        return record

    def complete(
        self,
        record: MCPInvocationAuditRecord,
        *,
        status: str,
        authorization_decision: str,
        response: Any = None,
        error_category: str | None = None,
    ) -> MCPInvocationAuditRecord:
        completed_at = datetime.now(UTC)
        result = replace(
            record,
            status=status,
            authorization_decision=authorization_decision,
            response_classification=_response_classification(response),
            response_hash=_hash(response) if response is not None else None,
            error_category=error_category,
            completed_at=completed_at,
            duration_ms=(completed_at - record.started_at).total_seconds() * 1000,
        )
        self._store.save(result)
        return result

    def all_records(self) -> list[MCPInvocationAuditRecord]:
        return self._store.list_records()


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, default=str, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _response_classification(value: Any) -> str:
    if value is None:
        return "none"
    if isinstance(value, Mapping):
        return "object"
    if isinstance(value, list):
        return "array"
    return type(value).__name__


def _sqlite_row(record: MCPInvocationAuditRecord) -> dict[str, Any]:
    return {
        **record.__dict__,
        "argument_summary_json": json.dumps(record.argument_summary, sort_keys=True),
        "started_at": record.started_at.isoformat(),
        "completed_at": record.completed_at.isoformat()
        if record.completed_at
        else None,
    }


def _postgres_row(record: MCPInvocationAuditRecord) -> dict[str, Any]:
    return {**record.__dict__, "argument_summary_json": record.argument_summary}


def _from_row(row: Mapping[str, Any]) -> MCPInvocationAuditRecord:
    return MCPInvocationAuditRecord(
        invocation_id=str(row["invocation_id"]),
        request_id=str(row["request_id"]),
        correlation_id=str(row["correlation_id"]),
        tool_name=str(row["tool_name"]),
        tool_version=str(row["tool_version"]),
        organization_id=str(row["organization_id"]),
        project_id=row["project_id"],
        actor_id=row["actor_id"],
        actor_type=row["actor_type"],
        client_id=row["client_id"],
        status=str(row["status"]),
        authorization_decision=str(row["authorization_decision"]),
        request_hash=str(row["request_hash"]),
        argument_summary=json.loads(row["argument_summary_json"]),
        response_classification=row["response_classification"],
        response_hash=row["response_hash"],
        error_category=row["error_category"],
        started_at=_datetime(row["started_at"]),
        completed_at=_datetime(row["completed_at"]) if row["completed_at"] else None,
        duration_ms=row["duration_ms"],
    )


def _datetime(value: Any) -> datetime:
    return (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(str(value)).astimezone(UTC)
    )
