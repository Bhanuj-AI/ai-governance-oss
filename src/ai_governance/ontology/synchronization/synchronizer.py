from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, Generic, Protocol, TypeVar

from ai_governance.ontology import (
    EntityType,
    OntologyEntity,
    OntologyService,
    RelationshipType,
)

LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


class OntologySynchronizer(Protocol[T]):
    """
    Common contract implemented by all ontology synchronizers.

    Synchronizers project authoritative domain objects into ontology entities
    and relationships. They do not own business data and never communicate
    directly with graph database drivers.
    """

    def synchronize(self, entity: T) -> SynchronizationResult:
        """
        Project one domain object into the ontology.
        """

    def delete(self, entity: T) -> SynchronizationResult:
        """
        Archive one ontology projection without deleting graph history.
        """

    def resynchronize(self, entity_id: str) -> SynchronizationResult:
        """
        Reload one domain object from the source repository and synchronize it.
        """


@dataclass(frozen=True)
class SynchronizationStats:
    """
    Observable counters for one synchronization operation.
    """

    entities_synchronized: int = 0
    relationships_synchronized: int = 0
    failures: int = 0
    retries: int = 0
    duration_ms: float = 0.0


@dataclass(frozen=True)
class SynchronizationResult:
    """
    Structured result returned by synchronization and reconciliation work.
    """

    synchronized_entity_ids: tuple[str, ...] = ()
    synchronized_relationship_ids: tuple[str, ...] = ()
    archived_entity_ids: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    stats: SynchronizationStats = field(default_factory=SynchronizationStats)

    @property
    def succeeded(self) -> bool:
        """
        Return whether the synchronization completed without errors.
        """

        return not self.errors


@dataclass(frozen=True)
class ReconciliationIssue:
    """
    Missing or repaired ontology projection discovered during reconciliation.
    """

    entity_id: str
    entity_type: str
    message: str
    repaired: bool


@dataclass(frozen=True)
class ReconciliationResult:
    """
    Result of replaying domain repositories into the ontology projection.
    """

    issues: tuple[ReconciliationIssue, ...]
    synchronized: tuple[SynchronizationResult, ...]
    stats: SynchronizationStats


class BaseOntologySynchronizer(Generic[T]):
    """
    Base class for deterministic ontology synchronizers.

    Subclasses implement `_synchronize` and optionally `_load`. This base class
    records timing and structured failures while keeping graph writes routed
    through `OntologyService`.
    """

    def __init__(
        self,
        ontology_service: OntologyService,
        *,
        source_name: str,
        loader: Callable[[str], T | None] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._ontology_service = ontology_service
        self._source_name = source_name
        self._loader = loader
        self._logger = logger or LOGGER

    def synchronize(self, entity: T) -> SynchronizationResult:
        """
        Synchronize one domain object and return observable counters.
        """

        started = time.perf_counter()
        try:
            result = self._synchronize(entity)
        except Exception as exc:
            duration_ms = _duration_ms(started)
            self._logger.exception(
                "Ontology synchronization failed for %s.",
                self._source_name,
            )
            return SynchronizationResult(
                errors=(str(exc),),
                stats=SynchronizationStats(
                    failures=1,
                    duration_ms=duration_ms,
                ),
            )

        duration_ms = _duration_ms(started)
        return _with_duration(result, duration_ms)

    def delete(self, entity: T) -> SynchronizationResult:
        """
        Archive one projected entity while preserving graph relationships.
        """

        started = time.perf_counter()
        try:
            entity_type, entity_id = self._archive_target(entity)
            existing = self._ontology_service.get_entity(entity_type, entity_id)
            if existing is None:
                return SynchronizationResult(
                    errors=(f"Ontology entity not found: {entity_type}/{entity_id}.",),
                    stats=SynchronizationStats(
                        failures=1,
                        duration_ms=_duration_ms(started),
                    ),
                )
            archived = replace(
                existing,
                lifecycle="ARCHIVED",
                mutable_attributes={
                    **existing.mutable_attributes,
                    "archived_at": datetime.now(UTC).isoformat(),
                },
                is_deleted=True,
                deleted_at=datetime.now(UTC),
            )
            self._ontology_service.save_entity(archived)
            return SynchronizationResult(
                archived_entity_ids=(entity_id,),
                stats=SynchronizationStats(
                    entities_synchronized=1,
                    duration_ms=_duration_ms(started),
                ),
            )
        except Exception as exc:
            self._logger.exception(
                "Ontology delete synchronization failed for %s.",
                self._source_name,
            )
            return SynchronizationResult(
                errors=(str(exc),),
                stats=SynchronizationStats(
                    failures=1,
                    duration_ms=_duration_ms(started),
                ),
            )

    def resynchronize(self, entity_id: str) -> SynchronizationResult:
        """
        Reload one domain object and synchronize it.
        """

        if self._loader is None:
            return SynchronizationResult(
                errors=(f"No loader configured for {self._source_name}.",),
                stats=SynchronizationStats(failures=1),
            )
        entity = self._loader(entity_id)
        if entity is None:
            return SynchronizationResult(
                errors=(
                    f"Domain entity not found for {self._source_name}: {entity_id}.",
                ),
                stats=SynchronizationStats(failures=1),
            )
        return self.synchronize(entity)

    def _synchronize(self, entity: T) -> SynchronizationResult:
        raise NotImplementedError

    def _archive_target(self, entity: T) -> tuple[str, str]:
        raise NotImplementedError


class OntologyReconciler:
    """
    Replays domain repositories into the ontology projection.

    Reconciliation is safe to run repeatedly. It detects missing primary
    ontology entities before synchronization and lets synchronizers repair the
    graph deterministically.
    """

    def __init__(
        self,
        ontology_service: OntologyService,
        synchronizers: Sequence[RepositorySynchronizer[Any]],
    ) -> None:
        self._ontology_service = ontology_service
        self._synchronizers = tuple(synchronizers)

    def reconcile(self) -> ReconciliationResult:
        """
        Replay all configured repository synchronizers.
        """

        started = time.perf_counter()
        issues: list[ReconciliationIssue] = []
        results: list[SynchronizationResult] = []

        for synchronizer in self._synchronizers:
            for entity in synchronizer.entities():
                entity_type, entity_id = synchronizer.primary_entity(entity)
                missing = (
                    self._ontology_service.get_entity(entity_type, entity_id) is None
                )
                result = synchronizer.synchronize(entity)
                results.append(result)
                if missing:
                    issues.append(
                        ReconciliationIssue(
                            entity_id=entity_id,
                            entity_type=entity_type,
                            message="Missing ontology entity projection.",
                            repaired=result.succeeded,
                        )
                    )

        stats = merge_stats(
            [result.stats for result in results],
            duration_ms=_duration_ms(started),
        )
        return ReconciliationResult(
            issues=tuple(issues),
            synchronized=tuple(results),
            stats=stats,
        )


@dataclass(frozen=True)
class RepositorySynchronizer(Generic[T]):
    """
    Adapter that pairs a synchronizer with a repository listing function.
    """

    synchronizer: OntologySynchronizer[T]
    list_entities: Callable[[], Iterable[T]]
    primary_entity_resolver: Callable[[T], tuple[str, str]]

    def entities(self) -> Iterable[T]:
        return self.list_entities()

    def synchronize(self, entity: T) -> SynchronizationResult:
        return self.synchronizer.synchronize(entity)

    def primary_entity(self, entity: T) -> tuple[str, str]:
        return self.primary_entity_resolver(entity)


def merge_results(results: Iterable[SynchronizationResult]) -> SynchronizationResult:
    """
    Merge several synchronization results into one aggregate result.
    """

    result_list = list(results)
    return SynchronizationResult(
        synchronized_entity_ids=tuple(
            item for result in result_list for item in result.synchronized_entity_ids
        ),
        synchronized_relationship_ids=tuple(
            item
            for result in result_list
            for item in result.synchronized_relationship_ids
        ),
        archived_entity_ids=tuple(
            item for result in result_list for item in result.archived_entity_ids
        ),
        errors=tuple(error for result in result_list for error in result.errors),
        stats=merge_stats([result.stats for result in result_list]),
    )


def merge_stats(
    stats: Iterable[SynchronizationStats],
    *,
    duration_ms: float | None = None,
) -> SynchronizationStats:
    """
    Merge synchronization counters.
    """

    stats_list = list(stats)
    return SynchronizationStats(
        entities_synchronized=sum(item.entities_synchronized for item in stats_list),
        relationships_synchronized=sum(
            item.relationships_synchronized for item in stats_list
        ),
        failures=sum(item.failures for item in stats_list),
        retries=sum(item.retries for item in stats_list),
        duration_ms=(
            duration_ms
            if duration_ms is not None
            else sum(item.duration_ms for item in stats_list)
        ),
    )


def stable_relationship_id(
    source_type: str | EntityType,
    source_id: str,
    relationship_type: str | RelationshipType,
    target_type: str | EntityType,
    target_id: str,
) -> str:
    """
    Return a deterministic relationship ID for idempotent synchronization.
    """

    parts = [
        _enum_value(source_type),
        source_id,
        _enum_value(relationship_type),
        _enum_value(target_type),
        target_id,
    ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return f"ontology-rel-{digest[:32]}"


def logical_prompt_id(name: str) -> str:
    return f"prompt:{name}"


def logical_model_id(provider: str, model_name: str) -> str:
    return f"model:{provider}:{model_name}"


def logical_dataset_id(name: str) -> str:
    return f"dataset:{name}"


def provider_entity_id(provider: str, version: str | None = None) -> str:
    if version:
        return f"provider:{provider}:{version}"
    return f"provider:{provider}"


def metric_entity_id(evaluation_id: str, metric_name: str) -> str:
    return f"metric:{evaluation_id}:{metric_name}"


def artifact_entity_id(evaluation_id: str, index: int) -> str:
    return f"artifact:{evaluation_id}:{index}"


def actor_entity_id(actor: str) -> str:
    return f"actor:{actor}"


def sync_actor(
    ontology_service: OntologyService,
    actor: str,
    *,
    actor_type: str = "user",
) -> str:
    """
    Ensure an Actor ontology entity exists and return its entity ID.
    """

    entity_id = actor_entity_id(actor)
    ontology_service.create_entity(
        entity_id=entity_id,
        entity_type=EntityType.ACTOR,
        owner=actor,
        lifecycle="ACTIVE",
        immutable_attributes={
            "actor_id": actor,
            "actor_type": actor_type,
        },
        metadata={"synchronized_from": "ontology_sync"},
    )
    return entity_id


def sync_relationship(
    ontology_service: OntologyService,
    *,
    source_type: str | EntityType,
    source_id: str,
    relationship_type: str | RelationshipType,
    target_type: str | EntityType,
    target_id: str,
    created_by: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    """
    Create a relationship with a deterministic ID and return that ID.
    """

    source_type_value = _enum_value(source_type)
    relationship_type_value = _enum_value(relationship_type)
    target_type_value = _enum_value(target_type)
    # Demo seeds and older graph projections may already contain the same
    # semantic edge with a non-deterministic ID. Reuse that live edge instead
    # of attempting a duplicate write; future projections converge on it.
    for existing in ontology_service.find_relationships(
        source_type_value,
        source_id,
        direction="outgoing",
        relationship_type=relationship_type_value,
    ):
        if (
            existing.target_entity_type == target_type_value
            and existing.target_entity_id == target_id
        ):
            record_existing = getattr(
                ontology_service,
                "record_existing_relationship",
                None,
            )
            if callable(record_existing):
                record_existing(existing)
            return existing.relationship_id

    relationship_id = stable_relationship_id(
        source_type_value,
        source_id,
        relationship_type_value,
        target_type_value,
        target_id,
    )
    ontology_service.create_relationship(
        relationship_id=relationship_id,
        source_type=source_type_value,
        source_id=source_id,
        relationship_type=relationship_type_value,
        target_type=target_type_value,
        target_id=target_id,
        created_by=created_by,
        metadata=metadata or {"synchronized_from": "ontology_sync"},
    )
    return relationship_id


def archive_entity(
    ontology_service: OntologyService,
    *,
    entity_type: str | EntityType,
    entity_id: str,
    archived_by: str,
) -> OntologyEntity | None:
    """
    Mark an ontology entity as archived without deleting relationships.
    """

    existing = ontology_service.get_entity(_enum_value(entity_type), entity_id)
    if existing is None:
        return None
    archived = OntologyEntity(
        entity_id=existing.entity_id,
        entity_type=existing.entity_type,
        owner=existing.owner,
        lifecycle="ARCHIVED",
        created_at=existing.created_at,
        ontology_version=existing.ontology_version,
        immutable_attributes=existing.immutable_attributes,
        mutable_attributes={
            **existing.mutable_attributes,
            "archived_by": archived_by,
            "archived_at": datetime.now(UTC).isoformat(),
        },
        metadata=existing.metadata,
    )
    ontology_service.save_entity(archived)
    return archived


def _duration_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000


def _with_duration(
    result: SynchronizationResult,
    duration_ms: float,
) -> SynchronizationResult:
    return SynchronizationResult(
        synchronized_entity_ids=result.synchronized_entity_ids,
        synchronized_relationship_ids=result.synchronized_relationship_ids,
        archived_entity_ids=result.archived_entity_ids,
        errors=result.errors,
        stats=SynchronizationStats(
            entities_synchronized=result.stats.entities_synchronized,
            relationships_synchronized=(result.stats.relationships_synchronized),
            failures=result.stats.failures,
            retries=result.stats.retries,
            duration_ms=duration_ms,
        ),
    )


def _enum_value(value: str | EntityType | RelationshipType) -> str:
    if isinstance(value, EntityType | RelationshipType):
        return value.value
    return value
