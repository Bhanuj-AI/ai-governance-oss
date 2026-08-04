from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette import status as http_status

from kavach.api.dependencies import get_mcp_audit_log
from kavach.api.mappers import MCPAuditApiMapper
from kavach.api.models import (
    ErrorResponse,
    MCPAuditListResponse,
    MCPAuditResponse,
)
from kavach.mcp.audit import MCPExecutionAuditLog
from kavach.api.dependencies.tenancy import get_compatible_tenant_context

router = APIRouter(
    prefix="/api/v1/mcp/audit",
    tags=["MCP Audit"],
)


@router.get(
    "",
    response_model=MCPAuditListResponse,
    status_code=http_status.HTTP_200_OK,
    responses={
        http_status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="List MCP audit records",
    description="List MCP execution audit records with optional filters.",
)
def list_mcp_audit_records(
    audit_log: Annotated[
        MCPExecutionAuditLog,
        Depends(get_mcp_audit_log),
    ],
    request_id: str | None = None,
    correlation_id: str | None = None,
    tool_name: str | None = None,
    status: str | None = None,
    actor_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    interrupted_after_seconds: int = Query(default=3600, ge=1),
    context=Depends(get_compatible_tenant_context),
) -> MCPAuditListResponse:
    """
    Return MCP audit records filtered by request, correlation, tool, status, or actor.
    """

    records = audit_log.list_records(
        request_id=request_id,
        correlation_id=correlation_id,
        tool_name=tool_name,
        status=status,
        actor_id=actor_id,
        organization_id=context.organization_id,
        project_id=context.project_id,
        limit=limit,
    )
    return MCPAuditApiMapper.to_list_response(
        records,
        interrupted_after_seconds=interrupted_after_seconds,
    )


@router.get(
    "/by-request/{request_id}",
    response_model=MCPAuditListResponse,
    status_code=http_status.HTTP_200_OK,
    responses={
        http_status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Find MCP audit records by request",
    description="Return MCP execution audit records for a request ID.",
)
def find_mcp_audit_by_request(
    request_id: str,
    audit_log: Annotated[
        MCPExecutionAuditLog,
        Depends(get_mcp_audit_log),
    ],
    interrupted_after_seconds: int = Query(default=3600, ge=1),
    context=Depends(get_compatible_tenant_context),
) -> MCPAuditListResponse:
    """
    Return MCP audit records for a specific request ID.
    """

    return MCPAuditApiMapper.to_list_response(
        [
            record
            for record in audit_log.find_by_request(request_id)
            if record.organization_id == context.organization_id
            and record.project_id == context.project_id
        ],
        interrupted_after_seconds=interrupted_after_seconds,
    )


@router.get(
    "/by-correlation/{correlation_id}",
    response_model=MCPAuditListResponse,
    status_code=http_status.HTTP_200_OK,
    responses={
        http_status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Find MCP audit records by correlation",
    description="Return MCP execution audit records for a correlation ID.",
)
def find_mcp_audit_by_correlation(
    correlation_id: str,
    audit_log: Annotated[
        MCPExecutionAuditLog,
        Depends(get_mcp_audit_log),
    ],
    interrupted_after_seconds: int = Query(default=3600, ge=1),
    context=Depends(get_compatible_tenant_context),
) -> MCPAuditListResponse:
    """
    Return MCP audit records for a specific correlation ID.
    """

    return MCPAuditApiMapper.to_list_response(
        [
            record
            for record in audit_log.find_by_correlation(correlation_id)
            if record.organization_id == context.organization_id
            and record.project_id == context.project_id
        ],
        interrupted_after_seconds=interrupted_after_seconds,
    )


@router.get(
    "/{audit_id}",
    response_model=MCPAuditResponse,
    status_code=http_status.HTTP_200_OK,
    responses={
        http_status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        http_status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Get MCP audit record",
    description="Return one MCP execution audit record by audit ID.",
)
def get_mcp_audit_record(
    audit_id: str,
    audit_log: Annotated[
        MCPExecutionAuditLog,
        Depends(get_mcp_audit_log),
    ],
    interrupted_after_seconds: int = Query(default=3600, ge=1),
    context=Depends(get_compatible_tenant_context),
) -> MCPAuditResponse:
    """
    Return an MCP audit record by audit ID.
    """

    record = audit_log.get(audit_id, context.organization_id, context.project_id)
    if record is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"MCP audit record '{audit_id}' was not found.",
        )

    return MCPAuditApiMapper.to_response(
        record,
        interrupted_after_seconds=interrupted_after_seconds,
    )
