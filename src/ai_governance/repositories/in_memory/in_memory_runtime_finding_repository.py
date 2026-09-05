"""In-memory runtime finding repository for unit tests."""

from __future__ import annotations

from ai_governance.domain.runtime_findings.finding import (
    FindingStatus,
    ReconciliationWindow,
    RuntimeFinding,
)
from ai_governance.repositories.runtime_finding_repository import (
    RuntimeFindingCursor,
    RuntimeFindingListFilters,
    RuntimeFindingPage,
    RuntimeFindingRepository,
)


class InMemoryRuntimeFindingRepository(RuntimeFindingRepository):
    """In-memory finding store for deterministic unit tests."""

    def __init__(self) -> None:
        self._findings: dict[str, RuntimeFinding] = {}

    def save(self, finding: RuntimeFinding) -> RuntimeFinding:
        self._findings[finding.finding_id] = finding
        return finding

    def get(
        self,
        finding_id: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> RuntimeFinding | None:
        for finding in self._findings.values():
            if (
                finding.finding_id == finding_id
                and finding.organization_id == organization_id
                and (project_id is None or finding.project_id == project_id)
            ):
                return finding
        return None

    def list(
        self,
        filters: RuntimeFindingListFilters,
        organization_id: str,
        project_id: str | None = None,
    ) -> list[RuntimeFinding]:
        results = []
        for finding in self._findings.values():
            if finding.organization_id != organization_id:
                continue
            if project_id is not None and finding.project_id != project_id:
                continue
            if filters.finding_type is not None and finding.finding_type != filters.finding_type:
                continue
            if filters.subject_type is not None and finding.subject_type != filters.subject_type:
                continue
            if filters.subject_id is not None and finding.subject_id != filters.subject_id:
                continue
            if filters.severity is not None and finding.severity != filters.severity:
                continue
            if filters.status is not None and finding.status != filters.status:
                continue
            if filters.created_after is not None and finding.created_at < filters.created_after:
                continue
            if filters.created_before is not None and finding.created_at > filters.created_before:
                continue
            results.append(finding)
        results.sort(key=lambda f: f.created_at, reverse=True)
        return results[: filters.limit]

    def find_by_dedup_key(
        self,
        dedup_key: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> RuntimeFinding | None:
        for finding in self._findings.values():
            if finding.deduplication_key() == dedup_key:
                return finding
        return None

    def list_by_status(
        self,
        status: FindingStatus,
        organization_id: str,
        project_id: str | None = None,
        limit: int = 100,
    ) -> list[RuntimeFinding]:
        results = []
        for finding in self._findings.values():
            if finding.organization_id != organization_id:
                continue
            if project_id is not None and finding.project_id != project_id:
                continue
            if finding.status == status:
                results.append(finding)
        return results[:limit]

    def page_by_status(
        self,
        status: FindingStatus,
        organization_id: str,
        project_id: str | None = None,
        cursor: RuntimeFindingCursor | None = None,
        limit: int = 100,
    ) -> RuntimeFindingPage:
        results = [
            finding for finding in self._findings.values()
            if finding.organization_id == organization_id
            and (project_id is None or finding.project_id == project_id)
            and finding.status == status
        ]
        results.sort(key=lambda finding: (finding.created_at, finding.finding_id), reverse=True)
        if cursor is not None:
            results = [
                finding for finding in results
                if (finding.created_at, finding.finding_id) < (cursor.created_at, cursor.finding_id)
            ]
        items = tuple(results[:limit])
        next_cursor = (
            RuntimeFindingCursor(items[-1].created_at, items[-1].finding_id)
            if len(results) > limit and items else None
        )
        return RuntimeFindingPage(items=items, next_cursor=next_cursor)

    def finalized_windows_covering(
        self,
        occurred_at,
        organization_id: str,
        project_id: str | None = None,
    ) -> tuple[ReconciliationWindow, ...]:
        windows: list[ReconciliationWindow] = []
        for finding in self._findings.values():
            if finding.organization_id != organization_id:
                continue
            if finding.project_id != project_id:
                continue
            candidates = list(finding.healthy_reconciliation_windows)
            if finding.last_reconciliation is not None:
                candidates.append(finding.last_reconciliation.window)
            windows.extend(
                window for window in candidates
                if window.covers(occurred_at)
            )
        return tuple(dict.fromkeys(windows))

    def count_by_subject(
        self,
        subject_type: str,
        subject_id: str,
        organization_id: str,
        project_id: str | None = None,
    ) -> int:
        count = 0
        for finding in self._findings.values():
            if (
                finding.organization_id == organization_id
                and finding.subject_type == subject_type
                and finding.subject_id == subject_id
                and (project_id is None or finding.project_id == project_id)
            ):
                count += 1
        return count
