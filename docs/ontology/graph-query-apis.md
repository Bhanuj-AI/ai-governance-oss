# Graph Query APIs

## Overview

Graph query APIs expose read-only access to the Kavach Governance Ontology.
They do not synchronize, reconcile, mutate, or repair graph state. All query
results are returned through storage-independent read models so REST and MCP
callers never depend on Neo4j records.

## Read Models

The query layer returns:

- `GraphEntity`
- `GraphRelationship`
- `GraphNode`
- `GraphEdge`
- `GraphSubgraph`
- `GraphPath`
- `GraphQueryPage`
- `GraphQueryFilters`

`GraphEntity` and `GraphRelationship` mirror stable ontology fields such as
entity IDs, entity types, lifecycle, owner, ontology version, timestamps,
attributes, metadata, relationship endpoints, and relationship metadata.

## Query Service

`OntologyGraphQueryService` validates entity types, relationship types, depth,
limit, direction, and cursor inputs before calling a read-only repository.

Default bounds:

- depth: `1`
- max depth: `5`
- limit: `100`
- max limit: `500`
- path limit: `10`

Missing entities return empty subgraph/path responses for traversal APIs.
Direct entity or relationship lookup returns `404` through REST when absent.

## REST Endpoints

```http
GET /api/v1/ontology/entities/{entity_type}/{entity_id}
GET /api/v1/ontology/relationships/{relationship_id}
GET /api/v1/ontology/entities/{entity_type}/{entity_id}/relationships
GET /api/v1/ontology/entities/{entity_type}/{entity_id}/neighbourhood
GET /api/v1/ontology/entities/{entity_type}/{entity_id}/upstream
GET /api/v1/ontology/entities/{entity_type}/{entity_id}/downstream
GET /api/v1/ontology/path
```

Supported query parameters include:

- `direction`
- `relationship_type`
- `entity_type`
- `depth`
- `limit`
- `cursor`
- `source_type`
- `source_id`
- `target_type`
- `target_id`
- `max_depth`

Relationship lists return `GraphQueryPage` with `items`, `limit`, and
`next_cursor`. Traversal endpoints return bounded `GraphSubgraph` responses.
Path queries return a list of `GraphPath` results.

## MCP Tools

MCP exposes the same read-only surface through REST-backed tools:

- `ontology_graph.get_entity`
- `ontology_graph.get_relationship`
- `ontology_graph.get_relationships`
- `ontology_graph.neighbourhood`
- `ontology_graph.upstream`
- `ontology_graph.downstream`
- `ontology_graph.find_paths`

MCP tools never call Neo4j directly.

## Repository Adapters

`InMemoryOntologyGraphQueryRepository` supports tests and local workflows over
the existing in-memory graph repository.

`Neo4jOntologyGraphQueryRepository` keeps Cypher and driver records behind the
adapter. Inputs are validated before dynamic relationship type or depth syntax
is introduced, values are parameterized, and traversals are bounded by service
limits.
