from __future__ import annotations

from kavach.api.models import MCPAuditListResponse, MCPAuditResponse
from kavach.mcp.audit import MCPExecutionAuditLog, MCPExecutionAuditRecord


class MCPAuditApiMapper:
    """
    Map MCP execution audit records into REST read models.
    """

    @staticmethod
    def to_response(
        record: MCPExecutionAuditRecord,
        *,
        interrupted_after_seconds: int,
    ) -> MCPAuditResponse:
        interrupted = MCPExecutionAuditLog.is_interrupted(
            record,
            older_than_seconds=interrupted_after_seconds,
        )
        return MCPAuditResponse(
            audit_id=record.audit_id,
            request_id=record.request_id,
            correlation_id=record.correlation_id,
            tool_name=record.tool_name,
            tool_version=record.tool_version,
            actor_id=record.actor_id,
            actor_type=record.actor_type,
            agent_name=record.agent_name,
            agent_session_id=record.agent_session_id,
            client_name=record.client_name,
            client_version=record.client_version,
            idempotency_key=record.idempotency_key,
            operation_type=record.operation_type,
            resource_type=record.resource_type,
            resource_id=record.resource_id,
            request_hash=record.request_hash,
            request_summary=record.request_summary,
            resolved_versions=record.resolved_versions,
            reason=record.reason,
            dry_run=record.dry_run,
            status=record.status,
            job_id=record.job_id,
            result_reference=record.result_reference,
            error_code=record.error_code,
            error_message=record.error_message,
            started_at=record.started_at,
            completed_at=record.completed_at,
            duration_ms=record.duration_ms,
            metadata=record.metadata,
            interrupted=interrupted,
            interrupted_reason=(
                "STARTED audit exceeded interruption threshold."
                if interrupted
                else None
            ),
        )

    @classmethod
    def to_list_response(
        cls,
        records: list[MCPExecutionAuditRecord],
        *,
        interrupted_after_seconds: int,
    ) -> MCPAuditListResponse:
        return MCPAuditListResponse(
            records=[
                cls.to_response(
                    record,
                    interrupted_after_seconds=interrupted_after_seconds,
                )
                for record in records
            ],
        )
