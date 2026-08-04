"""Ontology projection for immutable experiment leaderboard snapshots."""

from __future__ import annotations

from kavach.domain.experiments import Leaderboard
from kavach.ontology import EntityType, OntologyService, RelationshipType
from kavach.ontology.synchronization.synchronizer import (
    BaseOntologySynchronizer,
    SynchronizationResult,
    SynchronizationStats,
    sync_relationship,
)
from kavach.repositories.evaluation_run_repository import EvaluationRunRepository
from kavach.repositories.leaderboard_repository import LeaderboardRepository


class LeaderboardOntologySynchronizer(BaseOntologySynchronizer[Leaderboard]):
    """Project a leaderboard, its rank entries, and their evidence links."""

    def __init__(
        self,
        ontology_service: OntologyService,
        leaderboard_repository: LeaderboardRepository | None = None,
        evaluation_run_repository: EvaluationRunRepository | None = None,
    ) -> None:
        super().__init__(
            ontology_service,
            source_name="leaderboard_repository",
            loader=(
                leaderboard_repository.find_by_id
                if leaderboard_repository is not None
                else None
            ),
        )
        self._evaluation_runs = evaluation_run_repository

    def _synchronize(self, entity: Leaderboard) -> SynchronizationResult:
        self._ontology_service.create_entity(
            entity_id=entity.leaderboard_id,
            entity_type=EntityType.LEADERBOARD,
            owner=entity.experiment_id,
            lifecycle="GENERATED",
            created_at=entity.generated_at,
            immutable_attributes={
                "leaderboard_id": entity.leaderboard_id,
                "experiment_id": entity.experiment_id,
                "ranking_strategy": entity.ranking_strategy,
                "generated_at": entity.generated_at.isoformat(),
            },
            metadata={"synchronized_from": "leaderboard_repository"},
        )
        entity_ids = [entity.leaderboard_id]
        relationship_ids: list[str] = []
        for entry in entity.entries:
            entry_id = f"{entity.leaderboard_id}-entry-{entry.rank}"
            self._ontology_service.create_entity(
                entity_id=entry_id,
                entity_type=EntityType.LEADERBOARD_ENTRY,
                owner=entity.experiment_id,
                lifecycle="RANKED",
                created_at=entity.generated_at,
                immutable_attributes={
                    "rank": entry.rank,
                    "candidate_id": entry.candidate_id,
                    "overall_score": entry.overall_score,
                    "metrics": entry.metrics,
                    "cost": entry.cost,
                    "latency": entry.latency,
                    "reason": entry.reason,
                },
                metadata={"synchronized_from": "leaderboard_repository"},
            )
            entity_ids.append(entry_id)
            relationship_ids.extend(
                (
                    sync_relationship(
                        self._ontology_service,
                        source_type=EntityType.LEADERBOARD,
                        source_id=entity.leaderboard_id,
                        relationship_type=RelationshipType.HAS_ENTRY,
                        target_type=EntityType.LEADERBOARD_ENTRY,
                        target_id=entry_id,
                        created_by=entity.experiment_id,
                    ),
                    sync_relationship(
                        self._ontology_service,
                        source_type=EntityType.LEADERBOARD_ENTRY,
                        source_id=entry_id,
                        relationship_type=RelationshipType.RANKS,
                        target_type=EntityType.CANDIDATE,
                        target_id=entry.candidate_id,
                        created_by=entity.experiment_id,
                    ),
                    sync_relationship(
                        self._ontology_service,
                        source_type=EntityType.CANDIDATE,
                        source_id=entry.candidate_id,
                        relationship_type=RelationshipType.RANKED_BY,
                        target_type=EntityType.LEADERBOARD,
                        target_id=entity.leaderboard_id,
                        created_by=entity.experiment_id,
                    ),
                )
            )
            if entry.rank == 1:
                relationship_ids.append(
                    sync_relationship(
                        self._ontology_service,
                        source_type=EntityType.LEADERBOARD,
                        source_id=entity.leaderboard_id,
                        relationship_type=RelationshipType.RECOMMENDS,
                        target_type=EntityType.CANDIDATE,
                        target_id=entry.candidate_id,
                        created_by=entity.experiment_id,
                    )
                )

        if self._evaluation_runs is not None:
            for run in self._evaluation_runs.find_by_experiment_id(
                entity.experiment_id
            ):
                relationship_ids.append(
                    sync_relationship(
                        self._ontology_service,
                        source_type=EntityType.LEADERBOARD,
                        source_id=entity.leaderboard_id,
                        relationship_type=RelationshipType.GENERATED_FROM,
                        target_type=EntityType.EVALUATION_RUN,
                        target_id=run.run_id,
                        created_by=entity.experiment_id,
                    )
                )

        return SynchronizationResult(
            synchronized_entity_ids=tuple(entity_ids),
            synchronized_relationship_ids=tuple(relationship_ids),
            stats=SynchronizationStats(
                entities_synchronized=len(entity_ids),
                relationships_synchronized=len(relationship_ids),
            ),
        )

    def _archive_target(self, entity: Leaderboard) -> tuple[str, str]:
        return EntityType.LEADERBOARD.value, entity.leaderboard_id
