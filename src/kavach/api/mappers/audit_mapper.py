from __future__ import annotations

from kavach.api.models.audit import (
    AuditDetailResponse,
    AuditFilterOptionsResponse,
    AuditLinkedJobResponse,
    AuditListItemResponse,
    AuditMetricResponse,
    AuditPageResponse,
)
from kavach.services.audit_service import (
    AuditDetail,
    AuditLinkedJob,
    AuditListItem,
    AuditPage,
)


class AuditApiMapper:
    """
    Convert Studio audit read models into REST DTOs.
    """

    @classmethod
    def to_page_response(
        cls,
        page: AuditPage,
    ) -> AuditPageResponse:
        return AuditPageResponse(
            summary=[
                AuditMetricResponse(
                    label=metric.label,
                    value=metric.value,
                    description=metric.description,
                )
                for metric in page.summary
            ],
            filters=AuditFilterOptionsResponse(
                statuses=list(page.filters.statuses),
                tool_names=list(page.filters.tool_names),
                actor_ids=list(page.filters.actor_ids),
                resource_types=list(page.filters.resource_types),
                operation_types=list(page.filters.operation_types),
            ),
            records=[cls._list_item(record) for record in page.records],
            total=page.total,
            limit=page.limit,
            offset=page.offset,
        )

    @classmethod
    def to_detail_response(
        cls,
        detail: AuditDetail,
    ) -> AuditDetailResponse:
        return AuditDetailResponse(
            audit_id=detail.audit_id,
            request_id=detail.request_id,
            correlation_id=detail.correlation_id,
            tool_name=detail.tool_name,
            tool_version=detail.tool_version,
            actor_id=detail.actor_id,
            actor_type=detail.actor_type,
            agent_name=detail.agent_name,
            agent_session_id=detail.agent_session_id,
            client_name=detail.client_name,
            client_version=detail.client_version,
            idempotency_key=detail.idempotency_key,
            operation_type=detail.operation_type,
            resource_type=detail.resource_type,
            resource_id=detail.resource_id,
            request_hash=detail.request_hash,
            request_summary=dict(detail.request_summary),
            resolved_versions=dict(detail.resolved_versions),
            reason=detail.reason,
            dry_run=detail.dry_run,
            status=detail.status,
            job_id=detail.job_id,
            result_reference=detail.result_reference,
            error_code=detail.error_code,
            error_message=detail.error_message,
            started_at=detail.started_at,
            completed_at=detail.completed_at,
            duration_ms=detail.duration_ms,
            metadata=dict(detail.metadata),
            interrupted=detail.interrupted,
            interrupted_reason=detail.interrupted_reason,
            linked_job=(
                cls._linked_job(detail.linked_job)
                if detail.linked_job is not None
                else None
            ),
            related_records=[
                cls._list_item(record) for record in detail.related_records
            ],
        )

    @staticmethod
    def _list_item(
        record: AuditListItem,
    ) -> AuditListItemResponse:
        return AuditListItemResponse(
            audit_id=record.audit_id,
            request_id=record.request_id,
            correlation_id=record.correlation_id,
            tool_name=record.tool_name,
            operation_type=record.operation_type,
            resource_type=record.resource_type,
            resource_id=record.resource_id,
            actor_id=record.actor_id,
            status=record.status,
            dry_run=record.dry_run,
            started_at=record.started_at,
            completed_at=record.completed_at,
            duration_ms=record.duration_ms,
            interrupted=record.interrupted,
            interrupted_reason=record.interrupted_reason,
            reason=record.reason,
            job_id=record.job_id,
            job_status=record.job_status,
            result_reference=record.result_reference,
            error_code=record.error_code,
        )

    @staticmethod
    def _linked_job(
        job: AuditLinkedJob,
    ) -> AuditLinkedJobResponse:
        return AuditLinkedJobResponse(
            job_id=job.job_id,
            job_type=job.job_type,
            status=job.status,
            submitted_by=job.submitted_by,
            updated_at=job.updated_at,
        )
