"""
MCP audit wiring for the Kavach platform.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any


@lru_cache(maxsize=1)
def get_mcp_audit_log() -> Any:
    """
    Create the MCP execution audit log used by REST audit read endpoints.
    """

    from kavach.mcp.audit import MCPExecutionAuditLog

    backend = os.getenv("KAVACH_MCP_AUDIT_REPOSITORY", "sqlite").strip().lower()
    if backend == "postgres":
        dsn = os.getenv("KAVACH_MCP_AUDIT_POSTGRES_DSN", "").strip()
        if not dsn:
            raise ValueError(
                "KAVACH_MCP_AUDIT_POSTGRES_DSN is required when "
                "KAVACH_MCP_AUDIT_REPOSITORY=postgres"
            )
        return MCPExecutionAuditLog.postgres(dsn)
    if backend != "sqlite":
        raise ValueError("KAVACH_MCP_AUDIT_REPOSITORY must be sqlite or postgres")
    database_path = os.getenv(
        "KAVACH_MCP_AUDIT_DATABASE_PATH",
        ".kavach/mcp_execution_audit.db",
    )
    return MCPExecutionAuditLog.sqlite(database_path)


@lru_cache(maxsize=1)
def get_mcp_invocation_audit_log() -> Any:
    """Create the distinct durable audit log for every MCP invocation."""
    from kavach.mcp.invocation_audit import MCPInvocationAuditLog

    backend = os.getenv("KAVACH_MCP_AUDIT_REPOSITORY", "sqlite").strip().lower()
    if backend == "postgres":
        dsn = os.getenv("KAVACH_MCP_AUDIT_POSTGRES_DSN", "").strip()
        if not dsn:
            raise ValueError(
                "KAVACH_MCP_AUDIT_POSTGRES_DSN is required when KAVACH_MCP_AUDIT_REPOSITORY=postgres"
            )
        return MCPInvocationAuditLog.postgres(dsn)
    if backend != "sqlite":
        raise ValueError("KAVACH_MCP_AUDIT_REPOSITORY must be sqlite or postgres")
    return MCPInvocationAuditLog.sqlite(
        os.getenv("KAVACH_MCP_AUDIT_DATABASE_PATH", ".kavach/mcp_execution_audit.db")
    )
