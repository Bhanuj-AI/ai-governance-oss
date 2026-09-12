from __future__ import annotations

import pytest

from ai_governance.ontology.exceptions import OntologyRepositoryError
from ai_governance.ontology.neo4j_repository import Neo4jOntologyGraphRepository
from ai_governance.ontology.schema import (
    ENTITY_SEARCH_INDEX_PROPERTIES,
    initialize_ontology_schema,
)


class _Result:
    def __init__(self, record: dict[str, object] | None = None) -> None:
        self._record = record
        self.consumed = False

    def consume(self) -> None:
        self.consumed = True

    def single(self) -> dict[str, object] | None:
        return self._record


class _Session:
    def __init__(self, index_records: list[dict[str, object]]) -> None:
        self.index_records = index_records
        self.queries: list[str] = []

    def __enter__(self) -> _Session:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def run(self, query: str, **_: object) -> _Result:
        self.queries.append(query)
        if "SHOW INDEXES" in query:
            return _Result(self.index_records.pop(0))
        return _Result()


class _Driver:
    def __init__(self, session: _Session) -> None:
        self._session = session

    def session(self, **_: object) -> _Session:
        return self._session

    def close(self) -> None:
        return None


def _index_record(*, state: str = "ONLINE") -> dict[str, object]:
    return {
        "type": "FULLTEXT",
        "state": state,
        "labelsOrTypes": ["OntologyEntity"],
        "properties": list(ENTITY_SEARCH_INDEX_PROPERTIES),
    }


def test_entity_search_index_migration_creates_only_the_index_and_waits_online(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session([_index_record(state="POPULATING"), _index_record()])
    repository = Neo4jOntologyGraphRepository(
        "bolt://unused",
        "neo4j",
        "unused",
        driver=_Driver(session),
    )
    monkeypatch.setattr(
        "ai_governance.ontology.neo4j_repository.time.sleep", lambda _: None
    )

    repository.ensure_entity_search_index(timeout_seconds=1)

    assert (
        "CREATE FULLTEXT INDEX ontology_entity_search IF NOT EXISTS"
        in session.queries[0]
    )
    assert sum("SHOW INDEXES" in query for query in session.queries) == 2
    assert all(
        forbidden not in "\n".join(session.queries).upper()
        for forbidden in (" MATCH ", " SET ", " DELETE ", " MERGE ")
    )


def test_entity_search_index_migration_fails_for_an_incompatible_existing_index() -> (
    None
):
    session = _Session(
        [
            {
                **_index_record(),
                "properties": ["search_text"],
            }
        ]
    )
    repository = Neo4jOntologyGraphRepository(
        "bolt://unused",
        "neo4j",
        "unused",
        driver=_Driver(session),
    )

    with pytest.raises(OntologyRepositoryError, match="incompatible"):
        repository.ensure_entity_search_index(timeout_seconds=1)


def test_normal_schema_helper_runs_the_search_index_migration_when_supported() -> None:
    calls: list[str] = []

    class _Repository:
        def initialize_schema(self) -> None:
            calls.append("schema")

        def ensure_entity_search_index(self) -> None:
            calls.append("search-index")

    initialize_ontology_schema(_Repository())

    assert calls == ["schema", "search-index"]
