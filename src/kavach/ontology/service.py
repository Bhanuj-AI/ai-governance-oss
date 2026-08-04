from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from kavach.ontology.enums import ONTOLOGY_VERSION
from kavach.ontology.exceptions import (
    DuplicateOntologyRelationshipError,
    OntologyEntityNotFoundError,
)
from kavach.ontology.models import OntologyEntity, OntologyRelationship
from kavach.ontology.repositories import OntologyGraphRepository
from kavach.ontology.validation import RelationshipValidator


class OntologyService:
    """
    Application service for ontology graph writes and traversals.

    The service owns ontology relationship validation and should be the write
    boundary used by future sync jobs, APIs, MCP tools, or UI workflows. It
    remains storage-independent by depending only on `OntologyGraphRepository`.
    """

    def __init__(
        self,
        repository: OntologyGraphRepository,
        validator: RelationshipValidator | None = None,
    ) -> None:
        self._repository = repository
        self._validator = validator or RelationshipValidator()

    def save_entity(self, entity: OntologyEntity) -> OntologyEntity:
        """
        Create or update an ontology entity.
        """

        return self._repository.save_entity(entity)

    def create_entity(
        self,
        *,
        entity_id: str,
        entity_type: str,
        owner: str,
        lifecycle: str,
        created_at: datetime | None = None,
        ontology_version: str = ONTOLOGY_VERSION,
        immutable_attributes: Mapping[str, Any] | None = None,
        mutable_attributes: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> OntologyEntity:
        """
        Build and persist an ontology entity from primitive service arguments.
        """

        entity_kwargs: dict[str, Any] = {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "owner": owner,
            "lifecycle": lifecycle,
            "ontology_version": ontology_version,
            "immutable_attributes": immutable_attributes or {},
            "mutable_attributes": mutable_attributes or {},
            "metadata": metadata or {},
            "organization_id": organization_id,
            "project_id": project_id,
        }
        if created_at is not None:
            entity_kwargs["created_at"] = created_at

        return self.save_entity(OntologyEntity(**entity_kwargs))

    def get_entity(
        self,
        entity_type: str,
        entity_id: str,
    ) -> OntologyEntity | None:
        """
        Return one ontology entity by type and ID.
        """

        return self._repository.get_entity(entity_type, entity_id)

    def delete_entity(self, entity_type: str, entity_id: str) -> None:
        """
        Delete one ontology entity through the repository abstraction.
        """

        self._repository.delete_entity(entity_type, entity_id)

    def save_relationship(
        self,
        relationship: OntologyRelationship,
    ) -> OntologyRelationship:
        """
        Validate and persist an ontology relationship.
        """

        self._validator.validate(relationship)
        self._require_entity(
            relationship.source_entity_type,
            relationship.source_entity_id,
            relationship.organization_id,
            relationship.project_id,
        )
        self._require_entity(
            relationship.target_entity_type,
            relationship.target_entity_id,
            relationship.organization_id,
            relationship.project_id,
        )
        self._reject_duplicate_relationship(relationship)
        self._reject_cardinality_conflict(relationship)
        return self._repository.save_relationship(relationship)

    def create_relationship(
        self,
        *,
        source_type: str,
        source_id: str,
        relationship_type: str,
        target_type: str,
        target_id: str,
        created_by: str = "system",
        relationship_id: str | None = None,
        created_at: datetime | None = None,
        ontology_version: str = ONTOLOGY_VERSION,
        metadata: Mapping[str, Any] | None = None,
        organization_id: str = "org_default",
        project_id: str = "project_default",
    ) -> OntologyRelationship:
        """
        Build, validate, and persist a directed ontology relationship.
        """

        relationship_kwargs: dict[str, Any] = {
            "relationship_type": relationship_type,
            "source_entity_id": source_id,
            "source_entity_type": source_type,
            "target_entity_id": target_id,
            "target_entity_type": target_type,
            "created_by": created_by,
            "ontology_version": ontology_version,
            "metadata": metadata or {},
            "organization_id": organization_id,
            "project_id": project_id,
        }
        if relationship_id is not None:
            relationship_kwargs["relationship_id"] = relationship_id
        if created_at is not None:
            relationship_kwargs["created_at"] = created_at

        return self.save_relationship(OntologyRelationship(**relationship_kwargs))

    def get_relationship(
        self,
        relationship_id: str,
    ) -> OntologyRelationship | None:
        """
        Return one ontology relationship by ID.
        """

        return self._repository.get_relationship(relationship_id)

    def delete_relationship(self, relationship_id: str) -> None:
        """
        Delete one ontology relationship by ID.
        """

        self._repository.delete_relationship(relationship_id)

    def find_upstream(
        self,
        entity_type: str,
        entity_id: str,
        depth: int = 1,
    ) -> list[OntologyEntity]:
        """
        Resolve upstream lineage for an entity.
        """

        return self._repository.find_upstream(entity_type, entity_id, depth)

    def find_downstream(
        self,
        entity_type: str,
        entity_id: str,
        depth: int = 1,
    ) -> list[OntologyEntity]:
        """
        Resolve downstream impact for an entity.
        """

        return self._repository.find_downstream(entity_type, entity_id, depth)

    def find_neighbors(
        self,
        entity_type: str,
        entity_id: str,
        depth: int = 1,
    ) -> list[OntologyEntity]:
        """
        Resolve neighborhood traversal for an entity.
        """

        return self._repository.find_neighbors(entity_type, entity_id, depth)

    def find_relationships(
        self,
        entity_type: str,
        entity_id: str,
        direction: str | None = None,
        relationship_type: str | None = None,
    ) -> list[OntologyRelationship]:
        """
        Return relationships connected to an entity with optional filters.
        """

        return self._repository.find_relationships(
            entity_type,
            entity_id,
            direction=direction,
            relationship_type=relationship_type,
        )

    def _require_entity(
        self, entity_type: str, entity_id: str, organization_id: str, project_id: str
    ) -> None:
        entity = self._repository.get_entity(
            entity_type, entity_id, organization_id, project_id
        )
        if entity is None or entity.is_deleted:
            raise OntologyEntityNotFoundError(
                f"Ontology entity not found: {entity_type}/{entity_id}."
            )

    def _reject_duplicate_relationship(
        self,
        relationship: OntologyRelationship,
    ) -> None:
        existing = self._repository.find_relationships(
            relationship.source_entity_type,
            relationship.source_entity_id,
            direction="outgoing",
            relationship_type=relationship.relationship_type,
            organization_id=relationship.organization_id,
            project_id=relationship.project_id,
        )
        for item in existing:
            if item.relationship_id == relationship.relationship_id:
                continue
            if (
                item.target_entity_type == relationship.target_entity_type
                and item.target_entity_id == relationship.target_entity_id
            ):
                raise DuplicateOntologyRelationshipError(
                    "Duplicate ontology relationship: "
                    f"{relationship.source_entity_type}/"
                    f"{relationship.source_entity_id} "
                    f"{relationship.relationship_type} "
                    f"{relationship.target_entity_type}/"
                    f"{relationship.target_entity_id}."
                )

    def _reject_cardinality_conflict(
        self,
        relationship: OntologyRelationship,
    ) -> None:
        endpoint_rule = self._validator.endpoint_rule_for(relationship)
        if endpoint_rule.unique_per_source:
            outgoing = self._repository.find_relationships(
                relationship.source_entity_type,
                relationship.source_entity_id,
                direction="outgoing",
                relationship_type=relationship.relationship_type,
                organization_id=relationship.organization_id,
                project_id=relationship.project_id,
            )
            for item in outgoing:
                if item.relationship_id != relationship.relationship_id:
                    raise DuplicateOntologyRelationshipError(
                        f"{relationship.relationship_type} allows only one "
                        "target for this source."
                    )

        if endpoint_rule.unique_per_target:
            incoming = self._repository.find_relationships(
                relationship.target_entity_type,
                relationship.target_entity_id,
                direction="incoming",
                relationship_type=relationship.relationship_type,
                organization_id=relationship.organization_id,
                project_id=relationship.project_id,
            )
            for item in incoming:
                if item.relationship_id != relationship.relationship_id:
                    raise DuplicateOntologyRelationshipError(
                        f"{relationship.relationship_type} allows only one "
                        "source for this target."
                    )

        if endpoint_rule.unique_per_source_target_type:
            outgoing = self._repository.find_relationships(
                relationship.source_entity_type,
                relationship.source_entity_id,
                direction="outgoing",
                relationship_type=relationship.relationship_type,
                organization_id=relationship.organization_id,
                project_id=relationship.project_id,
            )
            for item in outgoing:
                if item.relationship_id == relationship.relationship_id:
                    continue
                if item.target_entity_type == relationship.target_entity_type:
                    raise DuplicateOntologyRelationshipError(
                        f"{relationship.relationship_type} allows only one "
                        f"{relationship.target_entity_type} target for this "
                        "source."
                    )
