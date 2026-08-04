from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class MCPAuditResponse(BaseModel):
    """
    REST response shape for one MCP execution audit row.
    """

    audit_id: str
    request_id: str
    correlation_id: str
    tool_name: str
    tool_version: str
    actor_id: str
    actor_type: str
    agent_name: str | None = None
    agent_session_id: str | None = None
    client_name: str | None = None
    client_version: str | None = None
    idempotency_key: str
    operation_type: str
    resource_type: str
    resource_id: str | None = None
    request_hash: str
    request_summary: dict[str, Any]
    resolved_versions: dict[str, Any]
    reason: str
    dry_run: bool
    status: str
    job_id: str | None = None
    result_reference: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: float | None = None
    metadata: dict[str, Any]
    interrupted: bool
    interrupted_reason: str | None = None


class MCPAuditListResponse(BaseModel):
    """
    REST response shape for MCP execution audit lists.
    """

    records: list[MCPAuditResponse]
