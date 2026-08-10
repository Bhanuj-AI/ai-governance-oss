from __future__ import annotations

from ai_governance.domain.prompts import Prompt
from ai_governance.ontology import EntityType, OntologyService, RelationshipType
from ai_governance.ontology.synchronization.synchronizer import (
    BaseOntologySynchronizer,
    SynchronizationResult,
    SynchronizationStats,
    logical_prompt_id,
    sync_actor,
    sync_relationship,
)
from ai_governance.repositories.prompt_repository import PromptRepository


class PromptOntologySynchronizer(BaseOntologySynchronizer[Prompt]):
    """
    Synchronizes prompt registry records into Prompt and PromptVersion nodes.

    The prompt registry remains authoritative. This synchronizer projects the
    logical prompt family, concrete version, actor provenance, lifecycle, and
    version lineage into the ontology graph.
    """

    def __init__(
        self,
        ontology_service: OntologyService,
        prompt_repository: PromptRepository | None = None,
    ) -> None:
        super().__init__(
            ontology_service,
            source_name="prompt_registry",
            loader=(
                prompt_repository.find_by_id if prompt_repository is not None else None
            ),
        )
        self._prompt_repository = prompt_repository

    def _synchronize(self, entity: Prompt) -> SynchronizationResult:
        logical_id = logical_prompt_id(entity.name)
        actor_id = sync_actor(self._ontology_service, entity.created_by)

        self._ontology_service.create_entity(
            entity_id=logical_id,
            entity_type=EntityType.PROMPT,
            owner=entity.created_by,
            lifecycle=entity.status.value,
            created_at=entity.created_at,
            immutable_attributes={"name": entity.name},
            mutable_attributes={"status": entity.status.value},
            metadata={
                "synchronized_from": "prompt_registry",
                "provenance": entity.provenance.value,
                "source_system": entity.source_system,
                "source_reference": entity.source_reference,
            },
        )
        self._ontology_service.create_entity(
            entity_id=entity.prompt_id,
            entity_type=EntityType.PROMPT_VERSION,
            owner=entity.created_by,
            lifecycle=entity.status.value,
            created_at=entity.created_at,
            immutable_attributes={
                "prompt_id": entity.prompt_id,
                "name": entity.name,
                "version": entity.version,
                "template": entity.template,
                "variables": list(entity.variables),
                "created_by": entity.created_by,
                "content_hash": entity.content_hash,
                "content_available": entity.content_available,
            },
            mutable_attributes={"status": entity.status.value},
            metadata={
                "synchronized_from": "prompt_registry",
                "provenance": entity.provenance.value,
                "source_system": entity.source_system,
                "source_reference": entity.source_reference,
            },
        )

        relationship_ids = [
            sync_relationship(
                self._ontology_service,
                source_type=EntityType.PROMPT,
                source_id=logical_id,
                relationship_type=RelationshipType.HAS_VERSION,
                target_type=EntityType.PROMPT_VERSION,
                target_id=entity.prompt_id,
                created_by=entity.created_by,
            ),
            sync_relationship(
                self._ontology_service,
                source_type=EntityType.PROMPT_VERSION,
                source_id=entity.prompt_id,
                relationship_type=RelationshipType.VERSION_OF,
                target_type=EntityType.PROMPT,
                target_id=logical_id,
                created_by=entity.created_by,
            ),
            sync_relationship(
                self._ontology_service,
                source_type=EntityType.PROMPT_VERSION,
                source_id=entity.prompt_id,
                relationship_type=RelationshipType.CREATED_BY,
                target_type=EntityType.ACTOR,
                target_id=actor_id,
                created_by=entity.created_by,
            ),
            sync_relationship(
                self._ontology_service,
                source_type=EntityType.PROMPT_VERSION,
                source_id=entity.prompt_id,
                relationship_type=RelationshipType.OWNED_BY,
                target_type=EntityType.ACTOR,
                target_id=actor_id,
                created_by=entity.created_by,
            ),
        ]
        supersedes_id = self._sync_supersedes(entity)
        if supersedes_id is not None:
            relationship_ids.append(supersedes_id)

        return SynchronizationResult(
            synchronized_entity_ids=(logical_id, entity.prompt_id, actor_id),
            synchronized_relationship_ids=tuple(relationship_ids),
            stats=SynchronizationStats(
                entities_synchronized=3,
                relationships_synchronized=len(relationship_ids),
            ),
        )

    def _archive_target(self, entity: Prompt) -> tuple[str, str]:
        return EntityType.PROMPT_VERSION.value, entity.prompt_id

    def _sync_supersedes(self, entity: Prompt) -> str | None:
        if self._prompt_repository is None:
            return None
        versions = sorted(
            self._prompt_repository.find_by_name(entity.name),
            key=lambda item: (item.created_at, item.version, item.prompt_id),
        )
        previous: Prompt | None = None
        for prompt in versions:
            if prompt.prompt_id == entity.prompt_id:
                break
            previous = prompt
        if previous is None:
            return None
        return sync_relationship(
            self._ontology_service,
            source_type=EntityType.PROMPT_VERSION,
            source_id=entity.prompt_id,
            relationship_type=RelationshipType.SUPERSEDES,
            target_type=EntityType.PROMPT_VERSION,
            target_id=previous.prompt_id,
            created_by=entity.created_by,
        )
