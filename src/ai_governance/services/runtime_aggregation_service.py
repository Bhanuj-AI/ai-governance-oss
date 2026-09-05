"""Runtime aggregation service for deterministic findings.

Reads authoritative execution/event data from PostgreSQL and computes
metrics for detector consumption. Never copies raw payloads — only
operational aggregates.

All queries are bounded by time range, tenant/project scope, and event
type indexes. The service never scans unbounded data.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from ai_governance.domain.agent_execution import EventType
from ai_governance.repositories.agent_execution_repository import (
    AgentExecutionListFilters,
)


class RuntimeAggregationService:
    """Compute operational metrics from agent execution events.

    This service reads from the agent execution repositories and
    produces metric dictionaries that detectors consume. It is
    deliberately stateless and read-only.

    All queries use:
    - Tenant/project scoping (organization_id, project_id)
    - Time-range filters (created_after, created_before)
    - Event-type filters where applicable
    - Bounded limits (max 10,000 executions per window)
    """

    def __init__(
        self,
        execution_repository: Any,
        event_repository: Any,
    ) -> None:
        self._execution_repo = execution_repository
        self._event_repo = event_repository

    def get_tool_metrics(
        self,
        organization_id: str,
        project_id: str | None,
        tool_id: str,
        baseline_start: datetime,
        baseline_end: datetime,
        observed_start: datetime,
        observed_end: datetime,
        evidence_received_before: datetime | None = None,
    ) -> tuple[dict[str, float], dict[str, float]]:
        """Compute tool call metrics for baseline and observed windows."""
        baseline = self._compute_tool_metrics(
            organization_id, project_id, tool_id, baseline_start, baseline_end, evidence_received_before
        )
        observed = self._compute_tool_metrics(
            organization_id, project_id, tool_id, observed_start, observed_end, evidence_received_before
        )
        return baseline, observed

    def get_observed_tool_ids(
        self,
        organization_id: str,
        project_id: str | None,
    ) -> tuple[str, ...]:
        """Return stable tool identities present in tenant-scoped runtime evidence.

        Tool identities are operational metadata on persisted ``TOOL_CALL``
        events.  This intentionally uses the same identity fields as tool
        metric calculation so every returned subject can be measured.
        """
        tool_ids: set[str] = set()
        executions = self._execution_repo.list(
            AgentExecutionListFilters(limit=10_000),
            organization_id,
            project_id,
        )
        for execution in executions:
            events = self._event_repo.list_by_execution(
                execution.execution_id,
                organization_id,
                project_id,
            )
            for event in events:
                if event.late_for_runtime_findings or event.event_type is not EventType.TOOL_CALL:
                    continue
                tool_id = _tool_identity(event.attributes)
                if tool_id is not None:
                    tool_ids.add(tool_id)
        return tuple(sorted(tool_ids))

    def get_agent_execution_metrics(
        self,
        organization_id: str,
        project_id: str | None,
        agent_id: str,
        baseline_start: datetime,
        baseline_end: datetime,
        observed_start: datetime,
        observed_end: datetime,
    ) -> tuple[dict[str, float], dict[str, float]]:
        """Compute agent execution metrics for baseline and observed windows."""
        baseline = self._compute_agent_execution_metrics(
            organization_id, project_id, agent_id, baseline_start, baseline_end
        )
        observed = self._compute_agent_execution_metrics(
            organization_id, project_id, agent_id, observed_start, observed_end
        )
        return baseline, observed

    def get_evaluation_metrics(
        self,
        organization_id: str,
        project_id: str | None,
        baseline_start: datetime,
        baseline_end: datetime,
        observed_start: datetime,
        observed_end: datetime,
        evidence_received_before: datetime | None = None,
    ) -> tuple[dict[str, float], dict[str, float]]:
        """Compute evaluation failure metrics for baseline and observed windows."""
        baseline = self._compute_evaluation_metrics(
            organization_id, project_id, baseline_start, baseline_end, evidence_received_before
        )
        observed = self._compute_evaluation_metrics(
            organization_id, project_id, observed_start, observed_end, evidence_received_before
        )
        return baseline, observed

    def get_policy_denial_metrics(
        self,
        organization_id: str,
        project_id: str | None,
        baseline_start: datetime,
        baseline_end: datetime,
        observed_start: datetime,
        observed_end: datetime,
        evidence_received_before: datetime | None = None,
    ) -> tuple[dict[str, float], dict[str, float]]:
        """Compute governance decision denial metrics."""
        baseline = self._compute_policy_denial_metrics(
            organization_id, project_id, baseline_start, baseline_end, evidence_received_before
        )
        observed = self._compute_policy_denial_metrics(
            organization_id, project_id, observed_start, observed_end, evidence_received_before
        )
        return baseline, observed

    def get_latency_metrics(
        self,
        organization_id: str,
        project_id: str | None,
        baseline_start: datetime,
        baseline_end: datetime,
        observed_start: datetime,
        observed_end: datetime,
        agent_id: str | None = None,
    ) -> tuple[dict[str, float], dict[str, float]]:
        """Compute duration metrics for all executions or one observed agent."""
        baseline = self._compute_latency_metrics(
            organization_id, project_id, baseline_start, baseline_end, agent_id
        )
        observed = self._compute_latency_metrics(
            organization_id, project_id, observed_start, observed_end, agent_id
        )
        return baseline, observed

    def get_error_metrics(
        self,
        organization_id: str,
        project_id: str | None,
        baseline_start: datetime,
        baseline_end: datetime,
        observed_start: datetime,
        observed_end: datetime,
        evidence_received_before: datetime | None = None,
    ) -> tuple[dict[str, float], dict[str, float]]:
        """Compute repeated error category metrics."""
        baseline = self._compute_error_metrics(
            organization_id, project_id, baseline_start, baseline_end, evidence_received_before
        )
        observed = self._compute_error_metrics(
            organization_id, project_id, observed_start, observed_end, evidence_received_before
        )
        return baseline, observed

    # -- Internal metric computation ------------------------------------------

    def _compute_tool_metrics(
        self,
        organization_id: str,
        project_id: str | None,
        tool_id: str,
        start: datetime,
        end: datetime,
        evidence_received_before: datetime | None = None,
    ) -> dict[str, float]:
        """Compute tool call metrics within a time window.

        Queries executions by time range (index-backed on created_at),
        then filters events by type and tool identity.
        """
        total_calls = 0
        failures = 0

        executions = self._execution_repo.list(
            type("Filters", (), {
                "agent_id": None,
                "status": None,
                "runtime_provider": None,
                "created_after": start,
                "created_before": end,
                "limit": 10000,
            })(),
            organization_id,
            project_id,
        )

        for execution in executions:
            events = self._event_repo.list_by_execution(
                execution.execution_id,
                organization_id,
                project_id,
            )
            for event in events:
                if event.late_for_runtime_findings or (
                    evidence_received_before and event.received_at > evidence_received_before
                ):
                    continue
                if event.event_type is EventType.TOOL_CALL:
                    attrs = dict(event.attributes) if hasattr(event.attributes, "items") else event.attributes
                    if _tool_identity(attrs) == tool_id:
                        total_calls += 1
                        if attrs.get("status") == "failed" or attrs.get("error"):
                            failures += 1

        return {
            "total_calls": float(total_calls),
            "failures": float(failures),
        }

    def _compute_agent_execution_metrics(
        self,
        organization_id: str,
        project_id: str | None,
        agent_id: str,
        start: datetime,
        end: datetime,
    ) -> dict[str, float]:
        """Compute agent execution metrics within a time window.

        Queries executions by time range and filters by agent_id.
        """
        executions = self._execution_repo.list(
            type("Filters", (), {
                "agent_id": None,
                "status": None,
                "runtime_provider": None,
                "created_after": start,
                "created_before": end,
                "limit": 10000,
            })(),
            organization_id,
            project_id,
        )

        total = 0
        failures = 0
        for execution in executions:
            if execution.agent_id == agent_id:
                total += 1
                if execution.status.value in ("FAILED", "CANCELLED"):
                    failures += 1

        return {
            "total_executions": float(total),
            "failures": float(failures),
        }

    def _compute_evaluation_metrics(
        self,
        organization_id: str,
        project_id: str | None,
        start: datetime,
        end: datetime,
        evidence_received_before: datetime | None = None,
    ) -> dict[str, float]:
        """Compute evaluation failure metrics within a time window."""
        executions = self._execution_repo.list(
            type("Filters", (), {
                "agent_id": None,
                "status": None,
                "runtime_provider": None,
                "created_after": start,
                "created_before": end,
                "limit": 10000,
            })(),
            organization_id,
            project_id,
        )

        total = 0
        failures = 0
        for execution in executions:
            events = self._event_repo.list_by_execution(
                execution.execution_id,
                organization_id,
                project_id,
            )
            for event in events:
                if event.late_for_runtime_findings or (
                    evidence_received_before and event.received_at > evidence_received_before
                ):
                    continue
                if event.event_type.value == "EVALUATION":
                    attrs = dict(event.attributes) if hasattr(event.attributes, "items") else event.attributes
                    total += 1
                    if attrs.get("status") == "failed":
                        failures += 1

        return {
            "total_evaluations": float(total),
            "failures": float(failures),
        }

    def _compute_policy_denial_metrics(
        self,
        organization_id: str,
        project_id: str | None,
        start: datetime,
        end: datetime,
        evidence_received_before: datetime | None = None,
    ) -> dict[str, float]:
        """Compute governance decision denial metrics."""
        executions = self._execution_repo.list(
            type("Filters", (), {
                "agent_id": None,
                "status": None,
                "runtime_provider": None,
                "created_after": start,
                "created_before": end,
                "limit": 10000,
            })(),
            organization_id,
            project_id,
        )

        total = 0
        denials = 0
        for execution in executions:
            events = self._event_repo.list_by_execution(
                execution.execution_id,
                organization_id,
                project_id,
            )
            for event in events:
                if event.late_for_runtime_findings or (
                    evidence_received_before and event.received_at > evidence_received_before
                ):
                    continue
                if event.event_type.value == "GOVERNANCE_DECISION":
                    attrs = dict(event.attributes) if hasattr(event.attributes, "items") else event.attributes
                    total += 1
                    if attrs.get("decision_outcome") == "denied":
                        denials += 1

        return {
            "total_decisions": float(total),
            "denials": float(denials),
        }

    def _compute_latency_metrics(
        self,
        organization_id: str,
        project_id: str | None,
        start: datetime,
        end: datetime,
        agent_id: str | None = None,
    ) -> dict[str, float]:
        """Compute execution duration metrics (median, P95).

        Queries executions by time range, computes duration from
        started_at/completed_at. Bounded to 10,000 executions.
        """
        executions = self._execution_repo.list(
            type("Filters", (), {
                "agent_id": None,
                "status": None,
                "runtime_provider": None,
                "created_after": start,
                "created_before": end,
                "limit": 10000,
            })(),
            organization_id,
            project_id,
        )

        durations: list[float] = []
        for execution in executions:
            if agent_id is not None and execution.agent_id != agent_id:
                continue
            if execution.started_at and execution.completed_at:
                duration = (execution.completed_at - execution.started_at).total_seconds()
                durations.append(duration)

        if not durations:
            return {"median_duration_seconds": 0.0, "p95_duration_seconds": 0.0, "total_executions": 0.0}

        durations.sort()
        n = len(durations)
        median = durations[n // 2]
        p95_idx = int(n * 0.95)
        p95 = durations[min(p95_idx, n - 1)]

        return {
            "median_duration_seconds": median,
            "p95_duration_seconds": p95,
            "total_executions": float(n),
        }

    def _compute_error_metrics(
        self,
        organization_id: str,
        project_id: str | None,
        start: datetime,
        end: datetime,
        evidence_received_before: datetime | None = None,
    ) -> dict[str, float]:
        """Compute repeated error category metrics.

        Queries executions by time range, then counts ERROR events
        grouped by error_category/error_code.
        """
        executions = self._execution_repo.list(
            type("Filters", (), {
                "agent_id": None,
                "status": None,
                "runtime_provider": None,
                "created_after": start,
                "created_before": end,
                "limit": 10000,
            })(),
            organization_id,
            project_id,
        )

        error_counts: dict[str, int] = defaultdict(int)
        for execution in executions:
            events = self._event_repo.list_by_execution(
                execution.execution_id,
                organization_id,
                project_id,
            )
            for event in events:
                if event.late_for_runtime_findings or (
                    evidence_received_before and event.received_at > evidence_received_before
                ):
                    continue
                if event.event_type.value == "ERROR":
                    attrs = dict(event.attributes) if hasattr(event.attributes, "items") else event.attributes
                    error_category = attrs.get(
                        "error_category",
                        attrs.get("error_code", "unknown"),
                    )
                    error_counts[str(error_category)] += 1

        if not error_counts:
            return {"max_errors": 0.0, "total_executions": float(len(executions))}

        max_count = max(error_counts.values())
        return {
            "max_errors": float(max_count),
            "total_executions": float(len(executions)),
            **{f"error_{k}": float(v) for k, v in error_counts.items()},
        }


def _tool_identity(attributes: Any) -> str | None:
    """Read the canonical, non-empty tool identity from event metadata."""
    mapping = dict(attributes) if hasattr(attributes, "items") else attributes
    if not isinstance(mapping, dict):
        return None
    for key in ("tool_identity", "tool_id", "tool"):
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None
