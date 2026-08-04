from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from kavach.ontology import OntologyEntity, OntologyService
from kavach.ontology.synchronization.projection import (
    ProjectionBuilder,
    ProjectionFingerprint,
)
from kavach.ontology.synchronization.snapshot import (
    GraphProjectionSnapshot,
    GraphProjectionSnapshotLoader,
)
from kavach.ontology.synchronization.synchronizer import (
    ReconciliationIssue,
    ReconciliationResult,
    RepositorySynchronizer,
    SynchronizationResult,
    SynchronizationStats,
    merge_stats,
)

T = TypeVar("T")

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProjectionDiff:
    """
    Difference between expected domain projection and current graph projection.

    `missing` means the primary graph entity is absent. `semantic_drift` means
    the current graph state and expected domain projection have different
    semantic fingerprints. `metadata_drift` means the graph semantics match but
    the primary entity is missing persisted reconciliation hashes.
    """

    entity_type: str
    entity_id: str
    projection_source: str
    expected: ProjectionFingerprint
    current: ProjectionFingerprint | None
    stored_projection_hash: str | None
    stored_relationship_set_hash: str | None

    @property
    def missing(self) -> bool:
        """
        Return whether the primary ontology entity is absent from the graph.
        """

        return self.current is None

    @property
    def semantic_drift(self) -> bool:
        """
        Return whether entity or relationship semantics differ.
        """

        return self.current != self.expected

    @property
    def metadata_drift(self) -> bool:
        """
        Return whether persisted reconciliation metadata is stale or missing.
        """

        return (
            self.stored_projection_hash != self.expected.projection_hash
            or self.stored_relationship_set_hash != self.expected.relationship_set_hash
        )

    @property
    def needs_repair(self) -> bool:
        """
        Return whether reconciliation must write graph state or metadata.
        """

        return self.missing or self.semantic_drift or self.metadata_drift


@dataclass(frozen=True)
class DiffReconciliationEntry:
    """
    Per-domain-object reconciliation decision.

    `action` is one of:

    - `skipped`: stored hashes and semantic graph state match the domain object
    - `metadata_updated`: graph semantics match but persisted hashes were absent
      or stale
    - `repaired`: semantic drift was repaired through the synchronizer
    - `failed`: synchronization failed and the result contains errors
    """

    entity_type: str
    entity_id: str
    projection_source: str
    action: str
    diff: ProjectionDiff | None
    result: SynchronizationResult | None


@dataclass(frozen=True)
class DiffReconciliationMetrics:
    """
    Operator-facing metrics for one reconciliation execution.

    These metrics are intentionally transport-neutral. REST, MCP, CLI, logs, or
    scheduled jobs can expose the same structure without depending on graph
    storage internals or reinterpreting low-level sync counters.
    """

    entities_scanned: int
    entities_skipped: int
    entities_repaired: int
    relationship_repairs: int
    repair_failures: int
    execution_duration_ms: float
    skip_ratio: float

    def to_dict(self) -> dict[str, float | int]:
        """
        Return a JSON-friendly representation of the metrics.
        """

        return {
            "entities_scanned": self.entities_scanned,
            "entities_skipped": self.entities_skipped,
            "entities_repaired": self.entities_repaired,
            "relationship_repairs": self.relationship_repairs,
            "repair_failures": self.repair_failures,
            "execution_duration_ms": self.execution_duration_ms,
            "skip_ratio": self.skip_ratio,
        }


@dataclass(frozen=True)
class DiffReconciliationReport:
    """
    Detailed report produced by diff-based reconciliation.

    Reports are intentionally richer than the legacy `ReconciliationResult`
    because diff reconciliation needs to explain skipped projections as well as
    repaired projections. `to_reconciliation_result()` preserves compatibility
    with older callers that only expect issues, sync results, and aggregate
    stats.
    """

    entries: tuple[DiffReconciliationEntry, ...]
    stats: SynchronizationStats

    @property
    def metrics(self) -> DiffReconciliationMetrics:
        """
        Return aggregate reconciliation metrics for operators.

        `entities_repaired` counts projections whose semantic graph state was
        repaired through a synchronizer. Metadata-only hash refreshes are
        reported separately through `metadata_updated_count`, because they do
        not represent domain-to-graph semantic drift.
        """

        entities_scanned = len(self.entries)
        entities_skipped = self.skipped_count
        repair_failures = self.failed_count
        skip_ratio = entities_skipped / entities_scanned if entities_scanned else 0.0
        relationship_repairs = sum(
            entry.result.stats.relationships_synchronized
            for entry in self.entries
            if entry.action == "repaired" and entry.result is not None
        )
        return DiffReconciliationMetrics(
            entities_scanned=entities_scanned,
            entities_skipped=entities_skipped,
            entities_repaired=self.repaired_count,
            relationship_repairs=relationship_repairs,
            repair_failures=repair_failures,
            execution_duration_ms=self.stats.duration_ms,
            skip_ratio=skip_ratio,
        )

    @property
    def repaired_count(self) -> int:
        """
        Return the number of projections repaired for semantic drift.
        """

        return sum(1 for entry in self.entries if entry.action == "repaired")

    @property
    def skipped_count(self) -> int:
        """
        Return the number of projections skipped because hashes matched.
        """

        return sum(1 for entry in self.entries if entry.action == "skipped")

    @property
    def metadata_updated_count(self) -> int:
        """
        Return the number of projections that only needed metadata refresh.
        """

        return sum(1 for entry in self.entries if entry.action == "metadata_updated")

    @property
    def failed_count(self) -> int:
        """
        Return the number of projections that failed repair.
        """

        return sum(1 for entry in self.entries if entry.action == "failed")

    def to_reconciliation_result(self) -> ReconciliationResult:
        """
        Convert the diff report to the legacy reconciliation result shape.
        """

        issues = [
            ReconciliationIssue(
                entity_id=entry.entity_id,
                entity_type=entry.entity_type,
                message=entry.action,
                repaired=(entry.action in {"repaired", "metadata_updated", "skipped"}),
            )
            for entry in self.entries
            if entry.action != "skipped"
        ]
        return ReconciliationResult(
            issues=tuple(issues),
            synchronized=tuple(
                entry.result for entry in self.entries if entry.result is not None
            ),
            stats=self.stats,
        )


@dataclass(frozen=True)
class DiffRepositorySynchronizer(Generic[T]):
    """
    Repository adapter for diff-based reconciliation.

    The adapter tells the engine how to list domain objects, identify the
    primary ontology entity for each object, group objects into scopes, and run
    the synchronizer that can repair drift. This makes full and scoped
    reconciliation filtered executions of the same algorithm.
    """

    synchronizer: object
    list_entities: Callable[[], Iterable[T]]
    primary_entity_resolver: Callable[[T], tuple[str, str]]
    projection_source: str
    scope_identifier: str
    entity_type: str
    entity_id_resolver: Callable[[T], str]
    entity_loader: Callable[[str], T | None] | None = None

    @classmethod
    def from_repository_synchronizer(
        cls,
        synchronizer: RepositorySynchronizer[T],
        *,
        projection_source: str,
        scope_identifier: str,
        entity_type: str,
        entity_id_resolver: Callable[[T], str],
    ) -> DiffRepositorySynchronizer[T]:
        """
        Upgrade a basic repository synchronizer into a diff-aware adapter.
        """

        return cls(
            synchronizer=synchronizer.synchronizer,
            list_entities=synchronizer.list_entities,
            primary_entity_resolver=synchronizer.primary_entity_resolver,
            projection_source=projection_source,
            scope_identifier=scope_identifier,
            entity_type=entity_type,
            entity_id_resolver=entity_id_resolver,
        )


class DiffBasedOntologyReconciler:
    """
    Deterministic diff-based ontology reconciliation engine.

    The engine builds expected projections from domain repositories, compares
    semantic fingerprints against graph snapshots, skips identical projections,
    updates missing metadata for semantically identical projections, and runs
    synchronizers only for detected semantic drift.

    The engine is safe to run repeatedly. A stable graph projection produces
    `skipped` entries and zero graph writes. Missing hashes on an otherwise
    correct projection produce a lightweight `metadata_updated` entry. Only
    missing entities, changed entity semantics, or changed relationship
    semantics invoke the underlying synchronizer.
    """

    def __init__(
        self,
        ontology_service: OntologyService,
        synchronizers: Sequence[DiffRepositorySynchronizer[Any]],
        *,
        projection_builder: ProjectionBuilder | None = None,
        snapshot_loader: GraphProjectionSnapshotLoader | None = None,
    ) -> None:
        self._ontology_service = ontology_service
        self._synchronizers = tuple(synchronizers)
        self._projection_builder = projection_builder or ProjectionBuilder()
        self._snapshot_loader = snapshot_loader or GraphProjectionSnapshotLoader(
            ontology_service
        )
        self._logger = LOGGER

    def reconcile_all(self) -> DiffReconciliationReport:
        """
        Reconcile every configured repository and domain object.
        """

        return self._reconcile(self._synchronizers)

    def reconcile_entity_type(
        self,
        entity_type: str,
    ) -> DiffReconciliationReport:
        """
        Reconcile all configured repositories for one primary entity type.

        Example: `reconcile_entity_type("PromptVersion")` repairs every prompt
        version projection without touching model or dataset projections.
        """

        return self._reconcile(
            [
                synchronizer
                for synchronizer in self._synchronizers
                if synchronizer.entity_type == entity_type
            ]
        )

    def reconcile_scope(
        self,
        scope_identifier: str,
    ) -> DiffReconciliationReport:
        """
        Reconcile all configured repositories for one named scope.

        Scopes are caller-defined strings such as `prompt_registry` or
        `experiment_service`; they let operators target a subsystem without
        duplicating reconciliation logic.
        """

        return self._reconcile(
            [
                synchronizer
                for synchronizer in self._synchronizers
                if synchronizer.scope_identifier == scope_identifier
            ]
        )

    def reconcile_entity(
        self,
        entity_type: str,
        entity_id: str,
    ) -> DiffReconciliationReport:
        """
        Reconcile one primary ontology entity.

        This is the narrowest repair mode and is useful after a targeted domain
        change, e.g. `reconcile_entity("Candidate", "candidate-123")`.
        """

        return self._reconcile(
            [
                synchronizer
                for synchronizer in self._synchronizers
                if synchronizer.entity_type == entity_type
            ],
            entity_id=entity_id,
        )

    def _reconcile(
        self,
        synchronizers: Iterable[DiffRepositorySynchronizer[Any]],
        *,
        entity_id: str | None = None,
    ) -> DiffReconciliationReport:
        """
        Execute the shared diff algorithm over a filtered synchronizer set.
        """

        started = time.perf_counter()
        entries: list[DiffReconciliationEntry] = []

        for synchronizer in synchronizers:
            domain_entities = synchronizer.list_entities()
            if entity_id is not None and synchronizer.entity_loader is not None:
                loaded = synchronizer.entity_loader(entity_id)
                domain_entities = (loaded,) if loaded is not None else ()
            for domain_entity in domain_entities:
                if (
                    entity_id is not None
                    and synchronizer.entity_id_resolver(domain_entity) != entity_id
                ):
                    continue
                entries.append(self._reconcile_one(synchronizer, domain_entity))

        stats = merge_stats(
            [entry.result.stats for entry in entries if entry.result is not None],
            duration_ms=(time.perf_counter() - started) * 1000,
        )
        report = DiffReconciliationReport(
            entries=tuple(entries),
            stats=stats,
        )
        self._logger.info(
            "Ontology reconciliation completed: %s",
            report.metrics.to_dict(),
        )
        return report

    def _reconcile_one(
        self,
        synchronizer: DiffRepositorySynchronizer[Any],
        domain_entity: Any,
    ) -> DiffReconciliationEntry:
        """
        Build expected state, compare it to current graph state, and repair.
        """

        primary_entity = synchronizer.primary_entity_resolver(domain_entity)
        snapshot = self._snapshot_loader.load(*primary_entity)
        projection = self._projection_builder.build(
            synchronizer=synchronizer.synchronizer,
            entity=domain_entity,
            primary_entity=primary_entity,
            projection_source=synchronizer.projection_source,
            seed_entities=snapshot.entities,
            seed_relationships=snapshot.relationships,
        )
        expected = projection.fingerprint
        current = snapshot.fingerprint if snapshot.exists else None
        diff = ProjectionDiff(
            entity_type=primary_entity[0],
            entity_id=primary_entity[1],
            projection_source=synchronizer.projection_source,
            expected=expected,
            current=current,
            stored_projection_hash=snapshot.stored_projection_hash,
            stored_relationship_set_hash=snapshot.stored_relationship_set_hash,
        )

        if not diff.needs_repair:
            return DiffReconciliationEntry(
                entity_type=primary_entity[0],
                entity_id=primary_entity[1],
                projection_source=synchronizer.projection_source,
                action="skipped",
                diff=diff,
                result=None,
            )

        if not diff.semantic_drift and diff.metadata_drift:
            self._persist_projection_metadata(
                snapshot,
                expected,
                synchronizer.projection_source,
            )
            return DiffReconciliationEntry(
                entity_type=primary_entity[0],
                entity_id=primary_entity[1],
                projection_source=synchronizer.projection_source,
                action="metadata_updated",
                diff=diff,
                result=SynchronizationResult(
                    synchronized_entity_ids=(primary_entity[1],),
                    stats=SynchronizationStats(entities_synchronized=1),
                ),
            )

        result = synchronizer.synchronizer.synchronize(domain_entity)
        if result.succeeded:
            repaired_snapshot = self._snapshot_loader.load(*primary_entity)
            self._persist_projection_metadata(
                repaired_snapshot,
                expected,
                synchronizer.projection_source,
            )

        return DiffReconciliationEntry(
            entity_type=primary_entity[0],
            entity_id=primary_entity[1],
            projection_source=synchronizer.projection_source,
            action="repaired" if result.succeeded else "failed",
            diff=diff,
            result=result,
        )

    def _persist_projection_metadata(
        self,
        snapshot: GraphProjectionSnapshot,
        fingerprint: ProjectionFingerprint,
        projection_source: str,
    ) -> None:
        """
        Store reconciliation hashes on the primary ontology entity.

        Metadata is written only after successful synchronization, or when the
        semantic graph state already matches and only metadata is missing.
        """

        primary = self._ontology_service.get_entity(
            snapshot.primary_entity_type,
            snapshot.primary_entity_id,
        )
        if primary is None:
            return
        updated = OntologyEntity(
            entity_id=primary.entity_id,
            entity_type=primary.entity_type,
            owner=primary.owner,
            lifecycle=primary.lifecycle,
            created_at=primary.created_at,
            ontology_version=primary.ontology_version,
            immutable_attributes=primary.immutable_attributes,
            mutable_attributes=primary.mutable_attributes,
            metadata={
                **primary.metadata,
                "projection_hash": fingerprint.projection_hash,
                "relationship_set_hash": fingerprint.relationship_set_hash,
                "projection_source": projection_source,
                "projection_version": "1.0.0",
                "last_synchronized_at": datetime.now(UTC).isoformat(),
            },
        )
        self._ontology_service.save_entity(updated)
