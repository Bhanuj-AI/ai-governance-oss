"""
Audit read-model wiring for the AI Governance Control Plane platform.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends

from ai_governance.api.dependencies.mcp import get_mcp_audit_log
from ai_governance.api.dependencies.repositories import get_job_repository


def get_audit_read_service(
    audit_log: Any = Depends(get_mcp_audit_log),
    job_repository: Any = Depends(get_job_repository),
) -> Any:
    """
    Create the Studio audit read service.
    """

    from ai_governance.services.audit_service import AuditReadService

    return AuditReadService(
        audit_log=audit_log,
        job_repository=job_repository,
    )
