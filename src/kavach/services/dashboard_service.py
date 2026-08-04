from __future__ import annotations

import os
from urllib.request import urlopen

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal

from kavach.decisions import GovernanceDecision
from kavach.domain.jobs import Job, JobStatus
from kavach.ontology.synchronization import OntologySyncEventStatus

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
        clock: Any | None = None,
    ) -> None:
        self._decision_repository = decision_repository
        self._job_repository = job_repository
        self._ontology_sync_event_repository = ontology_sync_event_repository
        self._ontology_graph_repository = ontology_graph_repository
        self._clock = clock or (lambda: datetime.now(UTC))

    def get_summary(self) -> DashboardSummary:
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
            ),
            recent_activity=_recent_activity(
                decisions,
                decision_activity_timestamps,
                jobs,
                sync_events,
            ),
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
    )


def _database_health(repository: Any) -> tuple[PlatformHealthStatus, str]:
    """Probe the configured persistence backend used by the dashboard."""
    repository_module = type(repository).__module__
    if repository_module.startswith("kavach.repositories.in_memory"):
        return "IN MEMORY", "Using an in-memory persistence backend."

    # PostgreSQL and SQLite repositories both expose ``_database.connect()``.
    # Identify the concrete repository before using SQLite-specific details;
    # otherwise PostgreSQL is incorrectly labelled as SQLite and its missing
    # ``database_path`` is rendered as ``None`` in the Studio dashboard.
    if repository_module.startswith("kavach.repositories.postgres"):
        # ``get_summary()`` has already completed a repository read before this
        # health summary is built, so the configured PostgreSQL repository is
        # known to be usable for this request.
        return "Healthy", "PostgreSQL persistence is responding."

    database = getattr(repository, "_database", None)
    if repository_module.startswith("kavach.repositories.sqlite") and (
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
        except Exception:
            return "Unavailable", "SQLite persistence is not responding."

    return "Unknown", "Persistence backend health is not reported."


def _ontology_graph_health(
    repository: Any,
) -> tuple[PlatformHealthStatus, str, int, int]:
    """Probe the graph store and return its live projection size."""
    module = type(repository).__module__
    if module == "kavach.ontology.repositories":
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
    except Exception:
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
        int(os.getenv("KAVACH_WORKER_HEARTBEAT_STALE_SECONDS", "120")),
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
    url = os.getenv("KAVACH_MCP_URL")
    if not url:
        return "Unknown", "MCP runtime health is not configured."
    try:
        with urlopen(f"{url.rstrip('/')}/openapi.json", timeout=0.5) as response:
            if 200 <= response.status < 300:
                return "Healthy", "MCP Server is responding."
    except Exception:
        pass
    return "Unavailable", "MCP Server is not responding."


def _recent_activity(
    decisions: tuple[GovernanceDecision, ...],
    decision_activity_timestamps: dict[str, datetime],
    jobs: tuple[Job, ...],
    sync_events: tuple[Any, ...],
) -> tuple[RecentActivityItem, ...]:
    items = [
        RecentActivityItem(
            timestamp=decision_activity_timestamps[decision.decision_id],
            resource=(
                f"{decision.target.target_type.value}/{decision.target.target_id}"
            ),
            action=f"Decision {decision.decision_type.value}",
            status=decision.status.value,
        )
        for decision in decisions
    ]
    items.extend(
        RecentActivityItem(
            timestamp=job.updated_at,
            resource=f"Job/{job.job_id}",
            action=job.job_type.value,
            status=job.status.value,
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
            resource=(
                f"{event.entity_type}/{event.entity_id or event.scope_identifier}"
            ),
            action=event.event_type,
            status=event.status.value,
        )
        for event in visible_sync_events
    )
    return tuple(
        sorted(
            items,
            key=lambda item: (item.timestamp, item.resource, item.action),
            reverse=True,
        )[:12]
    )


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
