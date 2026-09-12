"""Operational commands for the ontology graph."""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage the AI Governance Control Plane ontology graph"
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser(
        "initialize-schema", help="Create Neo4j constraints and indexes"
    )
    subcommands.add_parser(
        "initialize-deployment-schema",
        help="Create only the Neo4j constraints and indexes required at deployment",
    )
    subcommands.add_parser(
        "initialize-search-index",
        help="Create and verify the Neo4j ontology entity search index only",
    )
    arguments = parser.parse_args()

    if arguments.command == "initialize-schema":
        from ai_governance.ontology.neo4j_repository import Neo4jOntologyGraphRepository

        repository = Neo4jOntologyGraphRepository.from_environment()
        try:
            repository.initialize_schema()
            repository.ensure_entity_search_index()
        finally:
            repository.close()

    if arguments.command == "initialize-search-index":
        from ai_governance.ontology.neo4j_repository import Neo4jOntologyGraphRepository

        repository = Neo4jOntologyGraphRepository.from_environment()
        try:
            repository.ensure_entity_search_index()
        finally:
            repository.close()

    if arguments.command == "initialize-deployment-schema":
        from ai_governance.ontology.neo4j_repository import Neo4jOntologyGraphRepository

        repository = Neo4jOntologyGraphRepository.from_environment()
        try:
            repository.initialize_deployment_schema()
            repository.ensure_entity_search_index()
        finally:
            repository.close()


if __name__ == "__main__":
    main()
