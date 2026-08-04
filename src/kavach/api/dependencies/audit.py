"""
Audit read-model wiring for the Kavach platform.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends

from kavach.api.dependencies.mcp import get_mcp_audit_log
from kavach.api.dependencies.repositories import get_job_repository


def get_audit_read_service(
    audit_log: Any = Depends(get_mcp_audit_log),
    job_repository: Any = Depends(get_job_repository),
) -> Any:
    """
    Create the Studio audit read service.
    """

    from kavach.services.audit_service import AuditReadService

    return AuditReadService(
        audit_log=audit_log,
        job_repository=job_repository,
    )
