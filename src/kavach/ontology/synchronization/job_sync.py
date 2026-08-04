from __future__ import annotations

from typing import Any

from kavach.domain.jobs import Job
from kavach.ontology import EntityType, OntologyService, RelationshipType
from kavach.ontology.synchronization.synchronizer import (
    BaseOntologySynchronizer,
    SynchronizationResult,
    SynchronizationStats,
    sync_actor,
    sync_relationship,
)
from kavach.repositories.job_repository import JobRepository


class JobOntologySynchronizer(BaseOntologySynchronizer[Job]):
    """
    Synchronizes job control-plane records into the ontology projection.
    """

    def __init__(
        self,
        ontology_service: OntologyService,
        job_repository: JobRepository | None = None,
    ) -> None:
        super().__init__(
            ontology_service,
            source_name="job_control_plane",
            loader=job_repository.find_by_id if job_repository else None,
        )

    def _synchronize(self, entity: Job) -> SynchronizationResult:
        actor_id = sync_actor(self._ontology_service, entity.submitted_by)
        self._ontology_service.create_entity(
            entity_id=entity.job_id,
            entity_type=EntityType.JOB,
            owner=entity.submitted_by,
            lifecycle=entity.status.value,
            created_at=entity.created_at,
            immutable_attributes={
                "job_id": entity.job_id,
                "job_type": entity.job_type.value,
                "input_refs": entity.input_refs,
                "input_hash": entity.input_hash,
                "idempotency_key": entity.idempotency_key,
                "submitted_by": entity.submitted_by,
                "max_attempts": entity.max_attempts,
            },
            mutable_attributes={
                "status": entity.status.value,
                "attempt_count": entity.attempt_count,
                "result_ref": entity.result_ref,
                "failure_reason": entity.failure_reason,
                "leased_by": entity.leased_by,
                "lease_expires_at": _iso(entity.lease_expires_at),
                "heartbeat_at": _iso(entity.heartbeat_at),
                "updated_at": entity.updated_at.isoformat(),
                "started_at": _iso(entity.started_at),
                "completed_at": _iso(entity.completed_at),
            },
            metadata={"synchronized_from": "job_control_plane"},
        )

        relationship_ids = [
            sync_relationship(
                self._ontology_service,
                source_type=EntityType.JOB,
                source_id=entity.job_id,
                relationship_type=RelationshipType.CREATED_BY,
                target_type=EntityType.ACTOR,
                target_id=actor_id,
                created_by=entity.submitted_by,
            ),
            sync_relationship(
                self._ontology_service,
                source_type=EntityType.JOB,
                source_id=entity.job_id,
                relationship_type=RelationshipType.OWNED_BY,
                target_type=EntityType.ACTOR,
                target_id=actor_id,
                created_by=entity.submitted_by,
            ),
        ]

        target = _resolve_reference(entity.result_ref)
        if target is not None and self._entity_exists(target):
            target_type, target_id = target
            relationship_ids.append(
                sync_relationship(
                    self._ontology_service,
                    source_type=EntityType.JOB,
                    source_id=entity.job_id,
                    relationship_type=RelationshipType.RESULTED_IN,
                    target_type=target_type,
                    target_id=target_id,
                    created_by=entity.submitted_by,
                )
            )

        for target in _resolve_input_refs(entity.input_refs):
            if self._entity_exists(target):
                target_type, target_id = target
                relationship_ids.append(
                    sync_relationship(
                        self._ontology_service,
                        source_type=EntityType.JOB,
                        source_id=entity.job_id,
                        relationship_type=RelationshipType.GENERATED_FROM,
                        target_type=target_type,
                        target_id=target_id,
                        created_by=entity.submitted_by,
                    )
                )

        return SynchronizationResult(
            synchronized_entity_ids=(entity.job_id, actor_id),
            synchronized_relationship_ids=tuple(relationship_ids),
            stats=SynchronizationStats(
                entities_synchronized=2,
                relationships_synchronized=len(relationship_ids),
            ),
        )

    def _archive_target(self, entity: Job) -> tuple[str, str]:
        return EntityType.JOB.value, entity.job_id

    def _entity_exists(self, target: tuple[str, str]) -> bool:
        target_type, target_id = target
        return self._ontology_service.get_entity(target_type, target_id) is not None


def _resolve_input_refs(input_refs: dict[str, Any]) -> list[tuple[str, str]]:
    targets = []
    for value in input_refs.values():
        if isinstance(value, str):
            target = _resolve_reference(value)
            if target is not None:
                targets.append(target)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    target = _resolve_reference(item)
                    if target is not None:
                        targets.append(target)
    return targets


def _resolve_reference(value: str | None) -> tuple[str, str] | None:
    if not value:
        return None
    if value.startswith("evaluation:"):
        return EntityType.EVALUATION_RESULT.value, value.split(":", 1)[1]
    if value.startswith("evaluation_run:"):
        return EntityType.EVALUATION_RUN.value, value.split(":", 1)[1]
    if value.startswith("leaderboard:"):
        return EntityType.LEADERBOARD.value, value.split(":", 1)[1]
    if value.startswith("drift:"):
        return EntityType.DRIFT_ANALYSIS.value, value.split(":", 1)[1]
    if value.startswith("report:"):
        return EntityType.GOVERNANCE_REPORT.value, value.split(":", 1)[1]
    return None


def _iso(value: object) -> str | None:
    if value is None:
        return None
    return value.isoformat()  # type: ignore[attr-defined]
