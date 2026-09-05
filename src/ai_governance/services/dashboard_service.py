from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal
from urllib.request import urlopen

from ai_governance.decisions import GovernanceDecision
from ai_governance.domain.agent_execution import AgentExecutionStatus
from ai_governance.domain.causal_audit import CausalAuditStatus
from ai_governance.domain.jobs import Job, JobStatus, JobType
from ai_governance.domain.replay import ReplayStatus
from ai_governance.ontology.synchronization import OntologySyncEventStatus
from ai_governance.repositories.agent_execution_repository import (
    AgentExecutionListFilters,
)
from ai_governance.repositories.causal_audit_repository import CausalAuditListFilters
from ai_governance.repositories.replay_repository import ReplayListFilters
from ai_governance.tenancy.domain import TenantContext

PlatformHealthStatus = Literal[
    "Healthy",
    "Warning",
    "Unavailable",
    "Unknown",
    "IN MEMORY",
]


@dataclass(frozen=True)
class DashboardMetric:
    label: str
    value: int
    description: str | None = None


@dataclass(frozen=True)
class PlatformHealthComponent:
    component: str
    status: PlatformHealthStatus
    detail: str | None = None


@dataclass(frozen=True)
class DashboardMetricSection:
    key: str
    label: str
    metrics: tuple[DashboardMetric, ...]


@dataclass(frozen=True)
class DashboardAttentionSignal:
    label: str
    value: int
    detail: str


@dataclass(frozen=True)
class RecentActivityItem:
    timestamp: datetime
    resource: str
    action: str
    status: str


@dataclass(frozen=True)
class DashboardSummary:
    governance_statistics: tuple[DashboardMetric, ...]
    ontology_projection_statistics: tuple[DashboardMetric, ...]
    platform_statistics: tuple[DashboardMetric, ...]
    platform_health: tuple[PlatformHealthComponent, ...]
    recent_activity: tuple[RecentActivityItem, ...]
    operational_sections: tuple[DashboardMetricSection, ...] = ()
    attention_signals: tuple[DashboardAttentionSignal, ...] = ()
    health_checked_at: datetime | None = None


class DashboardReadService:
    """
    Builds the Studio home dashboard read model from backend-owned state.
    """

    def __init__(
        self,
        *,
        decision_repository: Any,
        job_repository: Any,
        ontology_sync_event_repository: Any,
        ontology_graph_repository: Any,
        replay_repository: Any | None = None,
        causal_audit_repository: Any | None = None,
        agent_execution_repository: Any | None = None,
        provider_registry: Any | None = None,
        clock: Any | None = None,
    ) -> None:
        self._decision_repository = decision_repository
        self._job_repository = job_repository
        self._ontology_sync_event_repository = ontology_sync_event_repository
        self._ontology_graph_repository = ontology_graph_repository
        self._replay_repository = replay_repository
        self._causal_audit_repository = causal_audit_repository
        self._agent_execution_repository = agent_execution_repository
        self._provider_registry = provider_registry
        self._clock = clock or (lambda: datetime.now(UTC))

    def get_summary(self, context: TenantContext | None = None) -> DashboardSummary:
        decisions = tuple(self._decision_repository.list(limit=500))
        jobs = tuple(self._job_repository.list_jobs(limit=500))
        sync_events = tuple(self._ontology_sync_event_repository.list_events(limit=500))
        decision_activity_timestamps = {
            decision.decision_id: _decision_activity_timestamp(
                self._decision_repository,
                decision,
            )
            for decision in decisions
        }

        policy_ids = {
            policy.policy_id for decision in decisions for policy in decision.policies
        }
        governed_resources = {
            (decision.target.target_type.value, decision.target.target_id)
            for decision in decisions
        }
        job_counts = Counter(job.status for job in jobs)
        sync_counts = Counter(event.status for event in sync_events)
        graph_status, graph_detail, graph_nodes, graph_relationships = (
            _ontology_graph_health(self._ontology_graph_repository)
        )
        replays = _list_replays(self._replay_repository, context)
        causal_audits = _list_causal_audits(self._causal_audit_repository, context)
        agent_executions = _list_agent_executions(
            self._agent_execution_repository, context
        )
        provider_count = _provider_count(self._provider_registry)
        replay_counts = Counter(replay.status for replay in replays)
        causal_audit_counts = Counter(audit.status for audit in causal_audits)
        execution_counts = Counter(execution.status for execution in agent_executions)
        failed_evaluations = sum(
            1 for job in jobs if job.status is JobStatus.FAILED and job.job_type == "EVALUATION"
        )
        now = self._clock()

        governance_statistics = (
            DashboardMetric(
                label="Governance Decisions",
                value=len(decisions),
                description="Persisted governance outcomes",
            ),
            DashboardMetric(
                label="Active Policies",
                value=len(policy_ids),
                description="Policies referenced by current decisions",
            ),
            DashboardMetric(
                label="Governed Resources",
                value=len(governed_resources),
                description="Resources with governance decisions",
            ),
            DashboardMetric(
                label="Projects",
                value=1,
                description="Current organization project scope",
            ),
        )
        platform_statistics = (
            DashboardMetric(
                label="Decisions Today",
                value=_count_decisions_on(
                    tuple(decision_activity_timestamps.values()),
                    self._clock().astimezone(UTC).date(),
                ),
            ),
            DashboardMetric(
                label="Policy Evaluations",
                value=sum(len(decision.policies) for decision in decisions),
            ),
            DashboardMetric(
                label="Running Jobs",
                value=job_counts[JobStatus.RUNNING],
            ),
            DashboardMetric(
                label="Completed Jobs",
                value=job_counts[JobStatus.SUCCEEDED],
            ),
        )

        return DashboardSummary(
            governance_statistics=governance_statistics,
            ontology_projection_statistics=(
                DashboardMetric(
                    label="Graph Nodes",
                    value=graph_nodes,
                    description="Live ontology entities in the graph store.",
                ),
                DashboardMetric(
                    label="Graph Relationships",
                    value=graph_relationships,
                    description="Live ontology edges in the graph store.",
                ),
                DashboardMetric(
                    label="Sync Queue",
                    value=(
                        sync_counts[OntologySyncEventStatus.PENDING]
                        + sync_counts[OntologySyncEventStatus.PROCESSING]
                    ),
                    description="Ontology events awaiting projection.",
                ),
                DashboardMetric(
                    label="Dead-Letter Events",
                    value=sync_counts[OntologySyncEventStatus.DEAD_LETTER],
                    description="Events requiring operator review.",
                ),
            ),
            platform_statistics=platform_statistics,
            platform_health=_platform_health(
                sync_events,
                graph_health=(graph_status, graph_detail),
                database_health=_database_health(self._job_repository),
                worker_health=_worker_health(
                    self._job_repository.list_worker_heartbeats(),
                    now=self._clock(),
                ),
                agent_runtime_health=_agent_runtime_health(
                    agent_executions,
                    repository_available=self._agent_execution_repository is not None,
                ),
            ),
            recent_activity=_recent_activity(
                decisions,
                decision_activity_timestamps,
                jobs,
                sync_events,
                replays,
                causal_audits,
                agent_executions,
            ),
            operational_sections=(
                DashboardMetricSection(
                    key="governance",
                    label="Governance & Assurance",
                    metrics=(
                        *governance_statistics[:3],
                        DashboardMetric(
                            label="Policy Evaluations",
                            value=sum(len(decision.policies) for decision in decisions),
                            description="Policy checks across current governance decisions.",
                        ),
                    ),
                ),
                DashboardMetricSection(
                    key="evaluation-replay",
                    label="Evaluation & Replay",
                    metrics=(
                        DashboardMetric(
                            label="Evaluations",
                            value=sum(1 for job in jobs if job.job_type == "EVALUATION"),
                            description="Evaluation jobs submitted.",
                        ),
                        DashboardMetric(
                            label="Replay Executions",
                            value=len(replays),
                            description="Replay runs in the selected project.",
                        ),
                        DashboardMetric(
                            label="Running / Queued Replays",
                            value=sum(replay_counts[status] for status in (ReplayStatus.QUEUED, ReplayStatus.RUNNING, ReplayStatus.EVALUATING, ReplayStatus.COMPARING)),
                            description="Replay work currently in progress.",
                        ),
                        DashboardMetric(
                            label="Evaluation Providers",
                            value=provider_count,
                            description="Ready" if provider_count else "Not configured",
                        ),
                    ),
                ),
                DashboardMetricSection(
                    key="agent-runtime",
                    label="Agent Runtime",
                    metrics=(
                        DashboardMetric(
                            label="Runtime Executions",
                            value=len(agent_executions),
                            description="Observed runtime execution records.",
                        ),
                        DashboardMetric(
                            label="Active Agents / Workflows",
                            value=len({execution.agent_id for execution in agent_executions}),
                            description="Agents with observed execution evidence.",
                        ),
                        DashboardMetric(
                            label="Failed Executions",
                            value=execution_counts[AgentExecutionStatus.FAILED],
                            description="Runtime executions requiring review.",
                        ),
                        DashboardMetric(
                            label="Causal Audits",
                            value=causal_audit_counts[CausalAuditStatus.SUCCEEDED],
                            description="Completed causal audits.",
                        ),
                    ),
                ),
            ),
            attention_signals=tuple(
                signal
                for signal in (
                    DashboardAttentionSignal("Failed Jobs", job_counts[JobStatus.FAILED], "Jobs requiring operator review."),
                    DashboardAttentionSignal("Failed Evaluations", failed_evaluations, "Evaluation jobs that did not complete."),
                    DashboardAttentionSignal("Replay Failures", replay_counts[ReplayStatus.FAILED], "Replay runs that did not complete."),
                    DashboardAttentionSignal("Causal Audit Failures", causal_audit_counts[CausalAuditStatus.FAILED], "Causal audits that did not complete."),
                    DashboardAttentionSignal("Ontology Backlog", sync_counts[OntologySyncEventStatus.PENDING] + sync_counts[OntologySyncEventStatus.PROCESSING], "Ontology events awaiting projection."),
                    DashboardAttentionSignal("Dead-Letter Events", sync_counts[OntologySyncEventStatus.DEAD_LETTER], "Ontology events requiring review or retry."),
                    DashboardAttentionSignal("Failed Runtime Executions", execution_counts[AgentExecutionStatus.FAILED], "Agent executions that did not complete."),
                )
                if signal.value > 0
            ),
            health_checked_at=now,
        )


def _count_decisions_on(
    timestamps: tuple[datetime, ...],
    day: date,
) -> int:
    return sum(1 for timestamp in timestamps if timestamp.astimezone(UTC).date() == day)


def _platform_health(
    sync_events: tuple[Any, ...],
    *,
    database_health: tuple[PlatformHealthStatus, str],
    worker_health: tuple[PlatformHealthStatus, str],
    graph_health: tuple[PlatformHealthStatus, str],
    agent_runtime_health: tuple[PlatformHealthStatus, str],
) -> tuple[PlatformHealthComponent, ...]:
    sync_counts = Counter(event.status for event in sync_events)
    if sync_counts[OntologySyncEventStatus.DEAD_LETTER]:
        dead_letters = sync_counts[OntologySyncEventStatus.DEAD_LETTER]
        sync_status: PlatformHealthStatus = "Warning"
        sync_detail = (
            f"{dead_letters} event{'s' if dead_letters != 1 else ''} "
            f"{'require' if dead_letters != 1 else 'requires'} review or retry."
        )
    elif sync_counts[OntologySyncEventStatus.FAILED]:
        sync_status = "Warning"
        sync_detail = "Ontology synchronization has failed events."
    elif (
        sync_counts[OntologySyncEventStatus.PENDING]
        or sync_counts[OntologySyncEventStatus.PROCESSING]
    ):
        sync_status = "Warning"
        sync_detail = "Ontology synchronization has queued work."
    else:
        sync_status = "Healthy"
        sync_detail = "No synchronization backlog detected."
    mcp_status, mcp_detail = _mcp_health()
    database_status, database_detail = database_health
    worker_status, worker_detail = worker_health
    graph_status, graph_detail = graph_health
    agent_runtime_status, agent_runtime_detail = agent_runtime_health

    return (
        PlatformHealthComponent(
            component="REST API",
            status="Healthy",
            detail="Serving dashboard read models.",
        ),
        PlatformHealthComponent(
            component="MCP Server",
            status=mcp_status,
            detail=mcp_detail,
        ),
        PlatformHealthComponent(
            component="Database",
            status=database_status,
            detail=database_detail,
        ),
        PlatformHealthComponent(
            component="Neo4j Graph Store",
            status=graph_status,
            detail=graph_detail,
        ),
        PlatformHealthComponent(
            component="Ontology Synchronizer",
            status=sync_status,
            detail=sync_detail,
        ),
        PlatformHealthComponent(
            component="Job Workers",
            status=worker_status,
            detail=worker_detail,
        ),
        PlatformHealthComponent(
            component="Agents Runtime",
            status=agent_runtime_status,
            detail=agent_runtime_detail,
        ),
    )


def _database_health(repository: Any) -> tuple[PlatformHealthStatus, str]:
    """Probe the configured persistence backend used by the dashboard."""
    repository_module = type(repository).__module__
    if repository_module.startswith("ai_governance.repositories.in_memory"):
        return "IN MEMORY", "Using an in-memory persistence backend."

    # PostgreSQL and SQLite repositories both expose ``_database.connect()``.
    # Identify the concrete repository before using SQLite-specific details;
    # otherwise PostgreSQL is incorrectly labelled as SQLite and its missing
    # ``database_path`` is rendered as ``None`` in the Studio dashboard.
    if repository_module.startswith("ai_governance.repositories.postgres"):
        # ``get_summary()`` has already completed a repository read before this
        # health summary is built, so the configured PostgreSQL repository is
        # known to be usable for this request.
        return "Healthy", "PostgreSQL persistence is responding."

    database = getattr(repository, "_database", None)
    if repository_module.startswith("ai_governance.repositories.sqlite") and (
        database is not None and hasattr(database, "connect")
    ):
        try:
            with database.connect() as connection:
                connection.execute("SELECT 1").fetchone()
            path = getattr(database, "database_path", None)
            detail = "SQLite persistence is responding."
            if path is not None:
                detail = f"SQLite persistence is responding ({path})."
            return "Healthy", detail
        except Exception:  # noqa: BLE001 - health probes treat every backend failure as unavailable.
            return "Unavailable", "SQLite persistence is not responding."

    return "Unknown", "Persistence backend health is not reported."


def _ontology_graph_health(
    repository: Any,
) -> tuple[PlatformHealthStatus, str, int, int]:
    """Probe the graph store and return its live projection size."""
    module = type(repository).__module__
    if module == "ai_governance.ontology.repositories":
        nodes = sum(
            1 for entity in repository._entities.values() if not entity.is_deleted
        )
        relationships = sum(
            1
            for relationship in repository._relationships.values()
            if not relationship.is_deleted
        )
        return "IN MEMORY", "In-memory graph projection.", nodes, relationships

    session_factory = getattr(repository, "_session", None)
    if session_factory is None:
        return "Unknown", "Graph backend health is not reported.", 0, 0
    try:
        with session_factory() as session:
            node_count = session.run(
                "MATCH (n:OntologyEntity) "
                "WHERE coalesce(n.is_deleted, false) = false "
                "RETURN count(n) AS count"
            ).single()["count"]
            relationship_count = session.run(
                "MATCH ()-[r]->() "
                "WHERE coalesce(r.is_deleted, false) = false "
                "RETURN count(r) AS count"
            ).single()["count"]
        return (
            "Healthy",
            f"Neo4j is responding ({node_count} live nodes, {relationship_count} live relationships).",
            int(node_count),
            int(relationship_count),
        )
    except Exception:  # noqa: BLE001 - health probes treat every backend failure as unavailable.
        return "Unavailable", "Neo4j graph store is not responding.", 0, 0


def _worker_health(
    workers: list[Any],
    *,
    now: datetime,
) -> tuple[PlatformHealthStatus, str]:
    """Assess workers from the heartbeat of their currently leased jobs.

    Workers do not yet have a standalone registry. A worker becomes observable
    when it leases a job, so an idle worker is intentionally reported as unknown
    rather than incorrectly marked healthy.
    """
    active_workers = [worker for worker in workers if worker.worker_type != "demo"]
    if not active_workers:
        return "Unknown", "No active job workers have registered a heartbeat."

    stale_after_seconds = max(
        1,
        int(os.getenv("AI_GOVERNANCE_WORKER_HEARTBEAT_STALE_SECONDS", "120")),
    )
    stale_workers = [
        worker
        for worker in active_workers
        if (now - worker.heartbeat_at).total_seconds() > stale_after_seconds
    ]
    if stale_workers:
        return (
            "Warning",
            f"{len(stale_workers)} of {len(active_workers)} active worker(s) have stale heartbeats.",
        )
    return (
        "Healthy",
        f"{len(active_workers)} active worker(s) reporting within {stale_after_seconds}s.",
    )


def _mcp_health() -> tuple[PlatformHealthStatus, str]:
    url = os.getenv("AI_GOVERNANCE_MCP_URL")
    if not url:
        return "Unknown", "MCP runtime health is not configured."
    try:
        with urlopen(f"{url.rstrip('/')}/openapi.json", timeout=0.5) as response:
            if 200 <= response.status < 300:
                return "Healthy", "MCP Server is responding."
    except Exception:  # noqa: BLE001 - a failed external probe means the service is unavailable.
        return "Unavailable", "MCP Server is not responding."
    return "Unavailable", "MCP Server is not responding."


def _list_replays(repository: Any | None, context: TenantContext | None) -> tuple[Any, ...]:
    if repository is None or context is None or context.project_id is None:
        return ()
    return tuple(
        repository.list(
            ReplayListFilters(limit=500),
            context.organization_id,
            context.project_id,
        )
    )


def _list_causal_audits(
    repository: Any | None, context: TenantContext | None
) -> tuple[Any, ...]:
    if repository is None or context is None:
        return ()
    return tuple(
        repository.list(
            CausalAuditListFilters(limit=500),
            context.organization_id,
            context.project_id,
        )
    )


def _list_agent_executions(
    repository: Any | None, context: TenantContext | None
) -> tuple[Any, ...]:
    if repository is None or context is None:
        return ()
    return tuple(
        repository.list(
            AgentExecutionListFilters(limit=500),
            context.organization_id,
            context.project_id,
        )
    )


def _provider_count(registry: Any | None) -> int:
    if registry is None:
        return 0
    return len(registry.list())


def _agent_runtime_health(
    executions: tuple[Any, ...], *, repository_available: bool
) -> tuple[PlatformHealthStatus, str]:
    if not repository_available:
        return "Unknown", "Runtime health is not configured."
    return (
        "Healthy",
        "Runtime ingestion and execution services are responding."
        if executions
        else "Runtime execution storage is responding; no executions observed yet.",
    )


def _recent_activity(
    decisions: tuple[GovernanceDecision, ...],
    decision_activity_timestamps: dict[str, datetime],
    jobs: tuple[Job, ...],
    sync_events: tuple[Any, ...],
    replays: tuple[Any, ...] = (),
    causal_audits: tuple[Any, ...] = (),
    agent_executions: tuple[Any, ...] = (),
) -> tuple[RecentActivityItem, ...]:
    items = [
        RecentActivityItem(
            timestamp=decision_activity_timestamps[decision.decision_id],
            resource="Governance decision",
            action=f"{_humanize(decision.decision_type.value)} decision",
            status=_humanize(decision.status.value),
        )
        for decision in decisions
    ]
    items.extend(
        RecentActivityItem(
            timestamp=job.updated_at,
            resource=_job_resource(job.job_type),
            action=_job_action(job.job_type, job.status),
            status=_humanize(job.status.value),
        )
        for job in jobs
    )
    visible_sync_events = [
        event
        for event in sync_events
        if not _is_governance_decision_projection_event(event)
    ]
    items.extend(
        RecentActivityItem(
            timestamp=event.updated_at,
            resource="Ontology",
            action=_humanize(event.event_type),
            status=_humanize(event.status.value),
        )
        for event in visible_sync_events
    )
    items.extend(
        RecentActivityItem(
            timestamp=replay.updated_at,
            resource="Replay",
            action=f"Replay {_humanize(replay.status.value).lower()}",
            status=_humanize(replay.status.value),
        )
        for replay in replays
    )
    items.extend(
        RecentActivityItem(
            timestamp=audit.updated_at,
            resource="Causal Audit",
            action=f"Causal audit {_humanize(audit.status.value).lower()}",
            status=_humanize(audit.status.value),
        )
        for audit in causal_audits
    )
    items.extend(
        RecentActivityItem(
            timestamp=execution.updated_at,
            resource="Agent Runtime",
            action=f"{execution.agent_name} execution {_humanize(execution.status.value).lower()}",
            status=_humanize(execution.status.value),
        )
        for execution in agent_executions
    )
    return tuple(
        sorted(
            items,
            key=lambda item: (item.timestamp, item.resource, item.action),
            reverse=True,
        )[:12]
    )


def _job_resource(job_type: JobType) -> str:
    return {
        JobType.EVALUATION: "Evaluation",
        JobType.REPLAY: "Replay",
        JobType.REPLAY_EXECUTION: "Replay",
        JobType.REPLAY_EVALUATION: "Replay",
        JobType.CAUSAL_AUDIT: "Causal Audit",
    }.get(job_type, "Jobs")


def _job_action(job_type: JobType, status: JobStatus) -> str:
    subject = {
        JobType.EVALUATION: "Evaluation",
        JobType.REPLAY: "Replay",
        JobType.REPLAY_EXECUTION: "Replay execution",
        JobType.REPLAY_EVALUATION: "Replay evaluation",
        JobType.CAUSAL_AUDIT: "Causal audit",
    }.get(job_type, _humanize(job_type.value))
    return f"{subject} {_humanize(status.value).lower()}"


def _humanize(value: str) -> str:
    return value.replace("_", " ").title()


def _decision_activity_timestamp(
    decision_repository: Any,
    decision: GovernanceDecision,
) -> datetime:
    audit_records = tuple(
        decision_repository.find_audit_by_decision(
            decision.decision_id,
            limit=100,
        )
    )
    if not audit_records:
        return decision.provenance.created_at

    created_records = [
        record
        for record in audit_records
        if getattr(record.action, "value", record.action) == "CREATED"
    ]
    records = created_records or list(audit_records)
    return max(record.created_at for record in records)


def _is_governance_decision_projection_event(event: Any) -> bool:
    event_type = str(getattr(event, "event_type", ""))
    entity_type = str(getattr(event, "entity_type", ""))
    return entity_type == "GovernanceDecision" or event_type.startswith(
        "GovernanceDecision"
    )
