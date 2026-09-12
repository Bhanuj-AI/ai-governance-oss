from __future__ import annotations

from ai_governance.ontology import RelationshipType
from ai_governance.ontology.schema import ONTOLOGY_RELATIONSHIP_UNIQUENESS_CYPHER


def test_relationship_uniqueness_constraints_are_scoped_to_canonical_types() -> None:
    assert len(ONTOLOGY_RELATIONSHIP_UNIQUENESS_CYPHER) == len(RelationshipType)

    for relationship_type in RelationshipType:
        statement = next(
            statement
            for statement in ONTOLOGY_RELATIONSHIP_UNIQUENESS_CYPHER
            if f"r:{relationship_type.value}" in statement
        )
        assert (
            f"ontology_relationship_unique_{relationship_type.value.lower()}"
            in statement
        )
        assert (
            "(r.organization_id, r.project_id, r.relationship_id) IS UNIQUE"
            in statement
        )
