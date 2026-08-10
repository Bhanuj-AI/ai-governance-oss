from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status as http_status

from ai_governance.api.dependencies import get_audit_read_service, get_mcp_invocation_audit_log
from ai_governance.api.mappers.audit_mapper import AuditApiMapper
from ai_governance.api.models import (
    AuditDetailResponse,
    AuditPageResponse,
    ErrorResponse,
    InvocationAuditListItemResponse,
    InvocationAuditPageResponse,
)
from ai_governance.api.dependencies.tenancy import get_compatible_tenant_context
from ai_governance.api.dependencies.settings_control import get_configuration_service
from ai_governance.settings_control.operational import duration_seconds, setting_context

router = APIRouter(
    prefix="/api/v1/audit",
    tags=["MCP Audit"],
)


@router.get(
    "",
    response_model=AuditPageResponse,
    status_code=http_status.HTTP_200_OK,
    responses={
        http_status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="List Studio MCP audit records",
    description="Return the Studio MCP audit page read model with summary, filters, and records.",
)
def list_audit_records(
    audit_read_service: Annotated[
        object,
        Depends(get_audit_read_service),
    ],
    search: str | None = None,
    status: str | None = None,
    tool_name: str | None = None,
    actor_id: str | None = None,
    resource_type: str | None = None,
    operation_type: str | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
    job_id: str | None = None,
    dry_run: bool | None = None,
    interrupted: bool | None = None,
    limit: int = Query(default=25, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    interrupted_after_seconds: int | None = Query(default=None, ge=1),
    context=Depends(get_compatible_tenant_context),
    configuration_service=Depends(get_configuration_service),
) -> AuditPageResponse:
    scope = setting_context(context)
    interrupted_after_seconds = interrupted_after_seconds or int(
        duration_seconds(configuration_service.get("audit.interrupted_timeout", scope))
    )
    retention_seconds = duration_seconds(
        configuration_service.get("audit.retention", scope)
    )
    return AuditApiMapper.to_page_response(
        audit_read_service.list_audits(
            search=search,
            status=status,
            tool_name=tool_name,
            actor_id=actor_id,
            resource_type=resource_type,
            operation_type=operation_type,
            request_id=request_id,
            correlation_id=correlation_id,
            job_id=job_id,
            dry_run=dry_run,
            interrupted=interrupted,
            limit=limit,
            offset=offset,
            interrupted_after_seconds=interrupted_after_seconds,
            organization_id=context.organization_id,
            project_id=context.project_id,
            retention_seconds=retention_seconds,
        )
    )


@router.get(
    "/invocations",
    response_model=InvocationAuditPageResponse,
    status_code=http_status.HTTP_200_OK,
    summary="List all MCP invocation audit records",
    description="Return privacy-safe evidence for all MCP tool calls, including reads.",
)
def list_invocation_audit_records(
    invocation_audit_log: Annotated[object, Depends(get_mcp_invocation_audit_log)],
    limit: int = Query(default=25, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    context=Depends(get_compatible_tenant_context),
) -> InvocationAuditPageResponse:
    records = [
        record
        for record in invocation_audit_log.all_records()
        if record.organization_id == context.organization_id
        and (record.project_id is None or record.project_id == context.project_id)
    ]
    records.sort(
        key=lambda record: (record.started_at, record.invocation_id), reverse=True
    )
    return InvocationAuditPageResponse(
        records=[
            InvocationAuditListItemResponse(
                invocation_id=record.invocation_id,
                request_id=record.request_id,
                correlation_id=record.correlation_id,
                tool_name=record.tool_name,
                tool_version=record.tool_version,
                actor_id=record.actor_id,
                client_id=record.client_id,
                status=record.status,
                authorization_decision=record.authorization_decision,
                request_hash=record.request_hash,
                response_classification=record.response_classification,
                response_hash=record.response_hash,
                error_category=record.error_category,
                started_at=record.started_at,
                completed_at=record.completed_at,
                duration_ms=record.duration_ms,
            )
            for record in records[offset : offset + limit]
        ],
        total=len(records),
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{audit_id}",
    response_model=AuditDetailResponse,
    status_code=http_status.HTTP_200_OK,
    responses={
        http_status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        http_status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
    summary="Get Studio MCP audit detail",
    description="Return one MCP audit record with related job and correlation context.",
)
def get_audit_detail(
    audit_id: str,
    audit_read_service: Annotated[
        object,
        Depends(get_audit_read_service),
    ],
    interrupted_after_seconds: int | None = Query(default=None, ge=1),
    context=Depends(get_compatible_tenant_context),
    configuration_service=Depends(get_configuration_service),
) -> AuditDetailResponse:
    scope = setting_context(context)
    interrupted_after_seconds = interrupted_after_seconds or int(
        duration_seconds(configuration_service.get("audit.interrupted_timeout", scope))
    )
    return AuditApiMapper.to_detail_response(
        audit_read_service.get_audit_detail(
            audit_id,
            interrupted_after_seconds=interrupted_after_seconds,
            organization_id=context.organization_id,
            project_id=context.project_id,
            retention_seconds=duration_seconds(
                configuration_service.get("audit.retention", scope)
            ),
        )
    )
