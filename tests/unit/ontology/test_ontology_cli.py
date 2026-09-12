from __future__ import annotations

import runpy
import sys
from types import SimpleNamespace


def test_search_index_cli_command_invokes_the_index_only_migration(
    monkeypatch,
) -> None:
    calls: list[str] = []

    class _Repository:
        @classmethod
        def from_environment(cls):
            return cls()

        def ensure_entity_search_index(self) -> None:
            calls.append("search-index")

        def close(self) -> None:
            calls.append("close")

    module = SimpleNamespace(Neo4jOntologyGraphRepository=_Repository)
    monkeypatch.setitem(
        sys.modules,
        "ai_governance.ontology.neo4j_repository",
        module,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["ai_governance.ontology.cli", "initialize-search-index"],
    )

    runpy.run_module("ai_governance.ontology.cli", run_name="__main__")

    assert calls == ["search-index", "close"]


def test_deployment_schema_cli_command_avoids_graph_repair_work(
    monkeypatch,
) -> None:
    calls: list[str] = []

    class _Repository:
        @classmethod
        def from_environment(cls):
            return cls()

        def initialize_deployment_schema(self) -> None:
            calls.append("deployment-schema")

        def ensure_entity_search_index(self) -> None:
            calls.append("search-index")

        def close(self) -> None:
            calls.append("close")

    module = SimpleNamespace(Neo4jOntologyGraphRepository=_Repository)
    monkeypatch.setitem(
        sys.modules,
        "ai_governance.ontology.neo4j_repository",
        module,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["ai_governance.ontology.cli", "initialize-deployment-schema"],
    )

    runpy.run_module("ai_governance.ontology.cli", run_name="__main__")

    assert calls == ["deployment-schema", "search-index", "close"]
