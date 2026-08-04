# Ontology Foundation

## Overview

The ontology foundation makes the accepted `kavach.governance` ontology
version `1.0.0` executable without synchronizing existing Kavach domain objects
into a graph.

![Kavach Ontology Graph](../../assets/Kavach%20Ontology%20Graph.png)

The foundation includes:

- storage-independent ontology models
- relationship validation for ontology v1 relationships
- an ontology graph repository protocol
- an in-memory repository for unit tests
- a Neo4j Community Edition repository adapter
- graph schema initialization
- an ontology service for validated writes and traversal

Existing prompt, model, dataset, experiment, evaluation, job, and MCP services
do not depend on this package. Future synchronization epics can project those
domain objects into the graph through `OntologyService`.

The synchronization layer is documented in
[Ontology Synchronization](./ontology-synchronization.md).

## Package Layout

```text
src/kavach/ontology/
  __init__.py
  enums.py
  exceptions.py
  models.py
  neo4j_repository.py
  repositories.py
  schema.py
  service.py
  validation.py
```

## Domain Models

`OntologyEntity` represents a first-class ontology node. It stores the stable
entity identity, entity type, ontology version, owner, lifecycle, creation
timestamp, immutable attributes, mutable attributes, and metadata.

`OntologyRelationship` represents a directed ontology edge. It stores source
and target entity IDs and types, relationship type, ontology version, creation
metadata, and relationship metadata.

`OntologyEvent` represents semantic temporal facts such as `Created`,
`EvaluationCompleted`, or `DriftDetected`. Events are records, not graph
relationships, because high-volume event logs should not redefine the decision
topology.

## Relationship Validation

`RelationshipValidator` is the central registry for relationship rules. It
rejects:

- unknown relationship types
- unsupported source entity types
- unsupported target entity types
- invalid relationship direction
- self-relationships unless a rule explicitly allows them

`OntologyService` adds repository-aware checks for missing endpoints,
duplicate edges, and obvious cardinality constraints such as one candidate
using only one `PromptVersion` for the `USES` relationship.

Example valid relationship:

```python
service.create_relationship(
    source_type="Candidate",
    source_id="candidate-1",
    relationship_type="USES",
    target_type="PromptVersion",
    target_id="prompt-v1",
    created_by="governance-admin",
)
```

Example invalid relationship:

```text
Candidate -[:HAS_VERSION]-> PromptVersion
```

`HAS_VERSION` is valid from a logical asset to its versioned asset, such as
`Prompt -[:HAS_VERSION]-> PromptVersion`.

## Neo4j Local Development

Start Neo4j Community Edition:

```bash
docker compose up -d neo4j
```

Configure the repository:

```bash
export KAVACH_GRAPH_URI=bolt://localhost:7687
export KAVACH_GRAPH_USER=neo4j
export KAVACH_GRAPH_PASSWORD=kavach-local-password
export KAVACH_GRAPH_DATABASE=neo4j
```

The Neo4j adapter imports the Neo4j Python driver only when the adapter is
constructed. Unit tests and non-graph Kavach code do not require Neo4j.

The Neo4j driver is a Kavach dependency. Refresh the environment before running
the integration tests if it is unavailable:

```bash
uv sync
```

## Schema Initialization

The Neo4j adapter creates:

```cypher
CREATE CONSTRAINT ontology_entity_unique IF NOT EXISTS
FOR (e:OntologyEntity)
REQUIRE (e.organization_id, e.project_id, e.entity_type, e.entity_id) IS UNIQUE;

CREATE INDEX ontology_entity_type IF NOT EXISTS
FOR (e:OntologyEntity)
ON (e.entity_type);

CREATE INDEX ontology_entity_version IF NOT EXISTS
FOR (e:OntologyEntity)
ON (e.ontology_version);

CREATE INDEX ontology_entity_tenant IF NOT EXISTS
FOR (e:OntologyEntity)
ON (e.organization_id, e.project_id);
```

Neo4j Community Edition 5.x supports the tenant-scoped composite uniqueness
constraint used for `(organization_id, project_id, entity_type, entity_id)`.
Older versions may require a repository migration that projects a synthetic
unique key property.

## Running Tests

Run unit tests without Neo4j:

```bash
uv run pytest tests/unit/ontology
```

Run Neo4j integration tests after starting Docker and installing the driver:

```bash
export KAVACH_RUN_NEO4J_TESTS=true
uv run pytest tests/integration/ontology
```

Integration tests are skipped unless `KAVACH_RUN_NEO4J_TESTS=true` and the
Neo4j Python driver can be imported.

## Guardrails

- Ontology writes go through `OntologyService`.
- Existing domain services do not depend on Neo4j.
- Neo4j-specific APIs stay inside `Neo4jOntologyGraphRepository`.
- Every graph relationship must conform to the ontology taxonomy.
- Graph topology represents semantic decision structure, not high-volume event
  or audit logs.
- Prompt, model, dataset, experiment, evaluation, job, replay, governance, and
  MCP audit synchronizers are implemented as a separate projection layer. See
  [Ontology Synchronization](./ontology-synchronization.md) and the
  [Neo4j Operations Guide](./neo4j-operations-guide.md).
