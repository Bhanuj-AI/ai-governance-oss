"""
MCP audit wiring for the AI Governance Control Plane platform.
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

    from ai_governance.mcp.audit import MCPExecutionAuditLog

    backend = os.getenv("AI_GOVERNANCE_MCP_AUDIT_REPOSITORY", "sqlite").strip().lower()
    if backend == "postgres":
        dsn = os.getenv("AI_GOVERNANCE_MCP_AUDIT_POSTGRES_DSN", "").strip()
        if not dsn:
            raise ValueError(
                "AI_GOVERNANCE_MCP_AUDIT_POSTGRES_DSN is required when "
                "AI_GOVERNANCE_MCP_AUDIT_REPOSITORY=postgres"
            )
        return MCPExecutionAuditLog.postgres(dsn)
    if backend != "sqlite":
        raise ValueError("AI_GOVERNANCE_MCP_AUDIT_REPOSITORY must be sqlite or postgres")
    database_path = os.getenv(
        "AI_GOVERNANCE_MCP_AUDIT_DATABASE_PATH",
        ".ai-governance/mcp_execution_audit.db",
    )
    return MCPExecutionAuditLog.sqlite(database_path)


@lru_cache(maxsize=1)
def get_mcp_invocation_audit_log() -> Any:
    """Create the distinct durable audit log for every MCP invocation."""
    from ai_governance.mcp.invocation_audit import MCPInvocationAuditLog

    backend = os.getenv("AI_GOVERNANCE_MCP_AUDIT_REPOSITORY", "sqlite").strip().lower()
    if backend == "postgres":
        dsn = os.getenv("AI_GOVERNANCE_MCP_AUDIT_POSTGRES_DSN", "").strip()
        if not dsn:
            raise ValueError(
                "AI_GOVERNANCE_MCP_AUDIT_POSTGRES_DSN is required when AI_GOVERNANCE_MCP_AUDIT_REPOSITORY=postgres"
            )
        return MCPInvocationAuditLog.postgres(dsn)
    if backend != "sqlite":
        raise ValueError("AI_GOVERNANCE_MCP_AUDIT_REPOSITORY must be sqlite or postgres")
    return MCPInvocationAuditLog.sqlite(
        os.getenv("AI_GOVERNANCE_MCP_AUDIT_DATABASE_PATH", ".ai-governance/mcp_execution_audit.db")
    )
