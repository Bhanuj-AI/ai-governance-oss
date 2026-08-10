from datetime import UTC, datetime

import pytest

from ai_governance.ontology import (
    EntityType,
    EventType,
    InvalidOntologyEntityError,
    InvalidOntologyRelationshipError,
    OntologyEntity,
    OntologyEvent,
    OntologyRelationship,
    RelationshipType,
)


def test_entity_model_validates_and_copies_attributes() -> None:
    immutable = {"name": "support prompt"}
    mutable = {"status": "ACTIVE"}
    entity = OntologyEntity(
        entity_id="prompt-v1",
        entity_type=EntityType.PROMPT_VERSION,
        owner="governance-admin",
        lifecycle="ACTIVE",
        created_at=datetime(2026, 6, 29, tzinfo=UTC),
        immutable_attributes=immutable,
        mutable_attributes=mutable,
        metadata={"source": "unit-test"},
    )

    immutable["name"] = "changed"
    mutable["status"] = "ARCHIVED"

    assert entity.entity_type == "PromptVersion"
    assert entity.immutable_attributes == {"name": "support prompt"}
    assert entity.mutable_attributes == {"status": "ACTIVE"}


def test_entity_rejects_unknown_entity_type() -> None:
    with pytest.raises(InvalidOntologyEntityError):
        OntologyEntity(
            entity_id="entity-1",
            entity_type="UnknownEntity",
            owner="owner",
            lifecycle="ACTIVE",
        )


def test_relationship_model_validates_relationship_type() -> None:
    relationship = OntologyRelationship(
        relationship_id="rel-1",
        relationship_type=RelationshipType.USES,
        source_entity_id="candidate-1",
        source_entity_type=EntityType.CANDIDATE,
        target_entity_id="prompt-v1",
        target_entity_type=EntityType.PROMPT_VERSION,
        created_by="tester",
    )

    assert relationship.relationship_type == "USES"
    assert relationship.source_entity_type == "Candidate"
    assert relationship.target_entity_type == "PromptVersion"


def test_relationship_rejects_unknown_type() -> None:
    with pytest.raises(InvalidOntologyRelationshipError):
        OntologyRelationship(
            relationship_id="rel-1",
            relationship_type="NOT_REAL",
            source_entity_id="candidate-1",
            source_entity_type="Candidate",
            target_entity_id="prompt-v1",
            target_entity_type="PromptVersion",
            created_by="tester",
        )


def test_event_model_stores_semantic_event_record() -> None:
    event = OntologyEvent(
        event_id="event-1",
        event_type=EventType.CREATED,
        entity_id="candidate-1",
        entity_type=EntityType.CANDIDATE,
        actor="tester",
        context={"reason": "unit-test"},
    )

    assert event.event_type == "Created"
    assert event.entity_type == "Candidate"
    assert event.context == {"reason": "unit-test"}
