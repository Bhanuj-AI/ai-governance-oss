"""Operational commands for the ontology graph."""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the AI Governance Control Plane ontology graph")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("initialize-schema", help="Create Neo4j constraints and indexes")
    arguments = parser.parse_args()

    if arguments.command == "initialize-schema":
        from ai_governance.ontology.neo4j_repository import Neo4jOntologyGraphRepository

        repository = Neo4jOntologyGraphRepository.from_environment()
        try:
            repository.initialize_schema()
        finally:
            repository.close()
