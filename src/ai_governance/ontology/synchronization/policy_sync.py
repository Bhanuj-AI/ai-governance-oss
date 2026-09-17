"""Ontology projection for versioned policy administration records."""

from __future__ import annotations

from ai_governance.decisions.policy_administration import (
    PolicyDefinition,
    PolicyVersion,
)
from ai_governance.ontology import EntityType, OntologyService, RelationshipType
from ai_governance.ontology.synchronization.synchronizer import (
    BaseOntologySynchronizer,
    SynchronizationResult,
    SynchronizationStats,
    sync_actor,
    sync_relationship,
)
from ai_governance.repositories.policy_administration_repository import (
    PolicyAdministrationRepository,
)


class PolicyOntologySynchronizer(BaseOntologySynchronizer[PolicyDefinition]):
    """Project a policy definition and its current lifecycle into the ontology."""

    def __init__(
        self,
        ontology_service: OntologyService,
        policy_repository: PolicyAdministrationRepository | None = None,
    ) -> None:
        super().__init__(
            ontology_service,
            source_name="policy_administration",
            loader=(
                policy_repository.get_definition
                if policy_repository is not None
                else None
            ),
        )
        self._policy_repository = policy_repository

    def _synchronize(self, entity: PolicyDefinition) -> SynchronizationResult:
        active_version = self._active_version(entity.policy_id)
        latest_version = self._latest_version(entity.policy_id)
        lifecycle = (
            active_version.status.value
            if active_version is not None
            else latest_version.status.value
            if latest_version is not None
            else "DRAFT"
        )
        actor_id = sync_actor(self._ontology_service, entity.created_by)

        self._ontology_service.create_entity(
            entity_id=entity.policy_id,
            entity_type=EntityType.POLICY,
            owner=entity.owner,
            lifecycle=lifecycle,
            created_at=entity.created_at,
            immutable_attributes={
                "policy_id": entity.policy_id,
                "name": entity.name,
                "description": entity.description,
                "category": entity.category.value,
                "owner": entity.owner,
                "created_by": entity.created_by,
                "organization_id": entity.organization_id,
                "project_id": entity.project_id,
            },
            mutable_attributes={
                "status": lifecycle,
                "active_version": (
                    active_version.version if active_version is not None else None
                ),
                "target_types": (
                    [target.value for target in active_version.target_types]
                    if active_version is not None
                    else []
                ),
                "rule_count": len(active_version.rules)
                if active_version is not None
                else 0,
            },
            metadata={"synchronized_from": "policy_administration"},
        )

        relationship_ids = (
            sync_relationship(
                self._ontology_service,
                source_type=EntityType.POLICY,
                source_id=entity.policy_id,
                relationship_type=RelationshipType.CREATED_BY,
                target_type=EntityType.ACTOR,
                target_id=actor_id,
                created_by=entity.created_by,
            ),
            sync_relationship(
                self._ontology_service,
                source_type=EntityType.POLICY,
                source_id=entity.policy_id,
                relationship_type=RelationshipType.OWNED_BY,
                target_type=EntityType.ACTOR,
                target_id=actor_id,
                created_by=entity.created_by,
            ),
        )
        return SynchronizationResult(
            synchronized_entity_ids=(entity.policy_id, actor_id),
            synchronized_relationship_ids=relationship_ids,
            stats=SynchronizationStats(
                entities_synchronized=2,
                relationships_synchronized=len(relationship_ids),
            ),
        )

    def _archive_target(self, entity: PolicyDefinition) -> tuple[str, str]:
        return EntityType.POLICY.value, entity.policy_id

    def _active_version(self, policy_id: str) -> PolicyVersion | None:
        if self._policy_repository is None:
            return None
        return self._policy_repository.get_active_version(policy_id)

    def _latest_version(self, policy_id: str) -> PolicyVersion | None:
        if self._policy_repository is None:
            return None
        versions = self._policy_repository.list_versions(policy_id)
        return max(
            versions,
            key=lambda version: (version.created_at, version.version),
            default=None,
        )
