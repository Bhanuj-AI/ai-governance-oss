from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from kavach.mcp.audit import MCPExecutionAuditLog, MCPExecutionAuditRecord
from kavach.repositories.job_repository import JobRepository


class AuditRecordNotFoundError(Exception):
    """
    Raised when an audit record cannot be found by ID.
    """

    def __init__(
        self,
        audit_id: str,
    ) -> None:
        super().__init__(f"Audit record '{audit_id}' was not found.")
        self.audit_id = audit_id


@dataclass(frozen=True)
class AuditMetric:
    label: str
    value: int
    description: str | None = None


@dataclass(frozen=True)
class AuditFilterOptions:
    statuses: tuple[str, ...]
    tool_names: tuple[str, ...]
    actor_ids: tuple[str, ...]
    resource_types: tuple[str, ...]
    operation_types: tuple[str, ...]


@dataclass(frozen=True)
class AuditLinkedJob:
    job_id: str
    job_type: str
    status: str
    submitted_by: str
    updated_at: datetime


@dataclass(frozen=True)
class AuditListItem:
    audit_id: str
    request_id: str
    correlation_id: str
    tool_name: str
    operation_type: str
    resource_type: str
    resource_id: str | None
    actor_id: str
    status: str
    dry_run: bool
    started_at: datetime
    completed_at: datetime | None
    duration_ms: float | None
    interrupted: bool
    interrupted_reason: str | None
    reason: str
    job_id: str | None
    job_status: str | None
    result_reference: str | None
    error_code: str | None


@dataclass(frozen=True)
class AuditPage:
    summary: tuple[AuditMetric, ...]
    filters: AuditFilterOptions
    records: tuple[AuditListItem, ...]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class AuditDetail:
    audit_id: str
    request_id: str
    correlation_id: str
    tool_name: str
    tool_version: str
    actor_id: str
    actor_type: str
    agent_name: str | None
    agent_session_id: str | None
    client_name: str | None
    client_version: str | None
    idempotency_key: str
    operation_type: str
    resource_type: str
    resource_id: str | None
    request_hash: str
    request_summary: dict[str, Any]
    resolved_versions: dict[str, Any]
    reason: str
    dry_run: bool
    status: str
    job_id: str | None
    result_reference: str | None
    error_code: str | None
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None
    duration_ms: float | None
    metadata: dict[str, Any]
    interrupted: bool
    interrupted_reason: str | None
    linked_job: AuditLinkedJob | None
    related_records: tuple[AuditListItem, ...]


class AuditReadService:
    """
    Studio-facing audit read model over MCP execution audit storage.
    """

    def __init__(
        self,
        audit_log: MCPExecutionAuditLog,
        job_repository: JobRepository,
    ) -> None:
        self._audit_log = audit_log
        self._job_repository = job_repository

    def list_audits(
        self,
        *,
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
        limit: int = 25,
        offset: int = 0,
        interrupted_after_seconds: int = 3600,
        organization_id: str | None = None,
        project_id: str | None = None,
        retention_seconds: float | None = None,
    ) -> AuditPage:
        records = self._sorted_records(self._audit_log.all_records())
        filtered = [
            record
            for record in records
            if (organization_id is None or record.organization_id == organization_id)
            and (project_id is None or record.project_id == project_id)
            and (
                retention_seconds is None
                or record.started_at.timestamp()
                >= datetime.now(UTC).timestamp() - retention_seconds
            )
            and self._matches_filters(
                record,
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
                interrupted_after_seconds=interrupted_after_seconds,
            )
        ]

        page = filtered[offset : offset + limit]
        return AuditPage(
            summary=self._summary(
                filtered,
                interrupted_after_seconds=interrupted_after_seconds,
            ),
            filters=self._filter_options(records),
            records=tuple(
                self._list_item(
                    record,
                    interrupted_after_seconds=interrupted_after_seconds,
                )
                for record in page
            ),
            total=len(filtered),
            limit=limit,
            offset=offset,
        )

    def get_audit_detail(
        self,
        audit_id: str,
        *,
        interrupted_after_seconds: int = 3600,
        organization_id: str | None = None,
        project_id: str | None = None,
        retention_seconds: float | None = None,
    ) -> AuditDetail:
        record = self._audit_log.get(audit_id, organization_id, project_id)
        if record is None:
            raise AuditRecordNotFoundError(audit_id)
        if (
            retention_seconds is not None
            and record.started_at.timestamp()
            < datetime.now(UTC).timestamp() - retention_seconds
        ):
            raise AuditRecordNotFoundError(audit_id)

        linked_job = self._linked_job(record.job_id)
        related_records = tuple(
            self._list_item(
                related,
                interrupted_after_seconds=interrupted_after_seconds,
            )
            for related in self._sorted_records(
                [
                    candidate
                    for candidate in self._audit_log.all_records()
                    if candidate.audit_id != audit_id
                    and candidate.correlation_id == record.correlation_id
                    and (
                        organization_id is None
                        or candidate.organization_id == organization_id
                    )
                    and (project_id is None or candidate.project_id == project_id)
                ]
            )[:10]
        )
        interrupted = self._is_interrupted(
            record,
            interrupted_after_seconds=interrupted_after_seconds,
        )
        return AuditDetail(
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
            request_summary=dict(record.request_summary),
            resolved_versions=dict(record.resolved_versions),
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
            metadata=dict(record.metadata),
            interrupted=interrupted,
            interrupted_reason=_interrupted_reason(interrupted),
            linked_job=linked_job,
            related_records=related_records,
        )

    def _matches_filters(
        self,
        record: MCPExecutionAuditRecord,
        *,
        search: str | None,
        status: str | None,
        tool_name: str | None,
        actor_id: str | None,
        resource_type: str | None,
        operation_type: str | None,
        request_id: str | None,
        correlation_id: str | None,
        job_id: str | None,
        dry_run: bool | None,
        interrupted: bool | None,
        interrupted_after_seconds: int,
    ) -> bool:
        if status is not None and record.status != status:
            return False
        if tool_name is not None and record.tool_name != tool_name:
            return False
        if actor_id is not None and record.actor_id != actor_id:
            return False
        if resource_type is not None and record.resource_type != resource_type:
            return False
        if operation_type is not None and record.operation_type != operation_type:
            return False
        if request_id is not None and record.request_id != request_id:
            return False
        if correlation_id is not None and record.correlation_id != correlation_id:
            return False
        if job_id is not None and record.job_id != job_id:
            return False
        if dry_run is not None and record.dry_run != dry_run:
            return False

        is_interrupted = self._is_interrupted(
            record,
            interrupted_after_seconds=interrupted_after_seconds,
        )
        if interrupted is not None and is_interrupted != interrupted:
            return False

        if not search:
            return True

        query = search.strip().lower()
        if not query:
            return True

        haystack = (
            record.audit_id,
            record.request_id,
            record.correlation_id,
            record.tool_name,
            record.actor_id,
            record.operation_type,
            record.resource_type,
            record.resource_id or "",
            record.job_id or "",
            record.result_reference or "",
            record.reason,
            record.status,
            record.error_code or "",
            record.error_message or "",
        )
        return any(query in value.lower() for value in haystack)

    def _summary(
        self,
        records: list[MCPExecutionAuditRecord],
        *,
        interrupted_after_seconds: int,
    ) -> tuple[AuditMetric, ...]:
        interrupted_count = sum(
            1
            for record in records
            if self._is_interrupted(
                record,
                interrupted_after_seconds=interrupted_after_seconds,
            )
        )
        active_started = sum(
            1
            for record in records
            if record.status == "STARTED"
            and not self._is_interrupted(
                record,
                interrupted_after_seconds=interrupted_after_seconds,
            )
        )
        return (
            AuditMetric(
                label="Started",
                value=active_started,
                description="Audit records currently in progress.",
            ),
            AuditMetric(
                label="Interrupted",
                value=interrupted_count,
                description="Stale STARTED records beyond the interruption threshold.",
            ),
            AuditMetric(
                label="Succeeded",
                value=sum(1 for record in records if record.status == "SUCCEEDED"),
                description="Completed write operations.",
            ),
            AuditMetric(
                label="Failed",
                value=sum(1 for record in records if record.status == "FAILED"),
                description="Completed audit records with an error outcome.",
            ),
            AuditMetric(
                label="Dry Run",
                value=sum(1 for record in records if record.status == "DRY_RUN"),
                description="Validated requests that did not execute.",
            ),
        )

    def _filter_options(
        self,
        records: list[MCPExecutionAuditRecord],
    ) -> AuditFilterOptions:
        return AuditFilterOptions(
            statuses=tuple(
                sorted({record.status for record in records}, key=_status_sort_key)
            ),
            tool_names=tuple(sorted({record.tool_name for record in records})),
            actor_ids=tuple(sorted({record.actor_id for record in records})),
            resource_types=tuple(sorted({record.resource_type for record in records})),
            operation_types=tuple(
                sorted({record.operation_type for record in records})
            ),
        )

    def _list_item(
        self,
        record: MCPExecutionAuditRecord,
        *,
        interrupted_after_seconds: int,
    ) -> AuditListItem:
        interrupted = self._is_interrupted(
            record,
            interrupted_after_seconds=interrupted_after_seconds,
        )
        linked_job = self._linked_job(record.job_id)
        return AuditListItem(
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
            interrupted=interrupted,
            interrupted_reason=_interrupted_reason(interrupted),
            reason=record.reason,
            job_id=record.job_id,
            job_status=linked_job.status if linked_job is not None else None,
            result_reference=record.result_reference,
            error_code=record.error_code,
        )

    def _linked_job(
        self,
        job_id: str | None,
    ) -> AuditLinkedJob | None:
        if job_id is None:
            return None

        job = self._job_repository.find_by_id(job_id)
        if job is None:
            return None

        return AuditLinkedJob(
            job_id=job.job_id,
            job_type=job.job_type.value,
            status=job.status.value,
            submitted_by=job.submitted_by,
            updated_at=job.updated_at,
        )

    def _is_interrupted(
        self,
        record: MCPExecutionAuditRecord,
        *,
        interrupted_after_seconds: int,
    ) -> bool:
        return self._audit_log.is_interrupted(
            record,
            older_than_seconds=interrupted_after_seconds,
        )

    @staticmethod
    def _sorted_records(
        records: list[MCPExecutionAuditRecord],
    ) -> list[MCPExecutionAuditRecord]:
        return sorted(
            records,
            key=lambda record: (record.started_at, record.audit_id),
            reverse=True,
        )


def _interrupted_reason(interrupted: bool) -> str | None:
    if not interrupted:
        return None
    return "STARTED audit exceeded interruption threshold."


def _status_sort_key(status: str) -> tuple[int, str]:
    order = {
        "STARTED": 0,
        "SUCCEEDED": 1,
        "FAILED": 2,
        "DRY_RUN": 3,
    }
    return (order.get(status, 99), status)
