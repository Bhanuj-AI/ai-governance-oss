# Neo4j Operations Guide

This guide explains how to run, observe, test, and troubleshoot AI Governance Control Plane's
Neo4j-backed ontology projection. It is intended for local operators and
platform engineers. For the ontology contract, see
[Governance Ontology](../architecture/GOVERNANCE_ONTOLOGY.md); for the
synchronizer design, see [Ontology Synchronization](./ontology-synchronization.md).

## What Neo4j Stores

Neo4j is a read-optimised semantic projection, not the system of record.
AI Governance Control Plane's domain repositories remain authoritative for policies, evaluations,
jobs, governance decisions, replay data, and MCP audit records.

```text
Domain repositories -> durable sync events -> synchronization worker -> Neo4j
```

The worker reconciles the expected projection from the authoritative domain
state. It is safe to replay an event or run reconciliation again: entity IDs
and relationship IDs are stable, and unchanged semantic projections are
skipped.

Deletion is non-destructive. Graph entities and relationships are retained with
`is_deleted`/archival metadata and excluded from live queries and traversals.

## Start the Local Stack

Start Keycloak first if you use the default authenticated local stack, then
start AI Governance Control Plane:

```bash
./scripts/keycloak/start-keycloak.sh
./ai_governance.sh
```

`./ai_governance.sh` uses Docker Compose. Compose waits for Neo4j, runs the one-shot
`ai-governance-neo4j-schema` initializer, starts the Platform, then starts Studio and
the ontology synchronization worker.

For a focused graph startup:

```bash
docker compose up -d neo4j
uv run python -m ai_governance.ontology.cli initialize-schema
```

The default local endpoints are:

| Service | Address |
| --- | --- |
| Neo4j Bolt | `bolt://localhost:7687` |
| Neo4j Browser | `http://localhost:7474` |
| Platform API | `http://localhost:8000` |
| Studio | `http://localhost:3000` |

## Required Configuration

Configure the Platform and synchronization worker with the same graph
connection settings:

```text
AI_GOVERNANCE_ONTOLOGY_REPOSITORY=neo4j
AI_GOVERNANCE_GRAPH_URI=bolt://neo4j:7687
AI_GOVERNANCE_GRAPH_USER=neo4j
AI_GOVERNANCE_GRAPH_PASSWORD=<secure-password>
AI_GOVERNANCE_GRAPH_DATABASE=neo4j
```

In Docker Compose, Platform, the synchronization worker, MCP, and MCP-over-HTTP
also share the durable audit store:

```text
AI_GOVERNANCE_MCP_AUDIT_DATABASE_PATH=/var/lib/ai-governance/mcp_execution_audit.db
```

This shared path is important: MCP writes audit records there, the Platform
serves them to Studio, the demo seed writes representative audit rows there,
and the synchronizer can project them into the ontology. Do not point one of
these services to a host-relative audit database while the others use the
volume path.

## Schema Initialization

The schema initializer is idempotent and creates the entity uniqueness
constraint plus indexes used by live reads. Run it whenever a new Neo4j
database is provisioned:

```bash
uv run python -m ai_governance.ontology.cli initialize-schema
```

The command is safe to run repeatedly. It does not seed business data and does
not delete graph data.

Check the schema in Neo4j Browser:

```cypher
SHOW INDEXES YIELD name, type
RETURN name, type
ORDER BY name;
```

Expected names include `ontology_entity_unique`, `ontology_entity_type`,
`ontology_entity_version`, and `ontology_entity_tenant`.

## Demo Seed and First Verification

Local startup automatically seeds stable demo data unless
`AI_GOVERNANCE_AUTO_SEED_DEMO_DATA=false`. The seed is upsert-safe: restarting the
stack refreshes the same records rather than adding duplicates.

To request the seed manually:

```bash
curl -X POST http://localhost:8000/api/v1/ontology/demo/seed
```

The seed provides policies, experiments, evaluations, jobs, governance
decisions, and MCP audit records. The synchronization worker projects these
records asynchronously.

Use Neo4j Browser to inspect the live graph:

```cypher
MATCH (n:OntologyEntity)
WHERE coalesce(n.is_deleted, false) = false
RETURN n.entity_type AS type, count(*) AS live_nodes
ORDER BY type;
```

```cypher
MATCH ()-[r]->()
WHERE coalesce(r.is_deleted, false) = false
RETURN type(r) AS relationship_type, count(*) AS live_relationships
ORDER BY relationship_type;
```

Studio's **Ontology** page is the supported application view. It calls the
Platform API; the browser never connects to Neo4j directly.

## Monitor and Repair Synchronization

Open Studio **Sync Events** or use the REST endpoints documented in
[REST API](../reference/REST_API.md):

```text
GET  /api/v1/ontology/synchronization/events
GET  /api/v1/ontology/synchronization/events/metrics
POST /api/v1/ontology/synchronization/events/{event_id}/retry
POST /api/v1/ontology/synchronization/events/{event_id}/cancel
```

Event lifecycle:

```text
PENDING -> PROCESSING -> COMPLETED
                     -> FAILED -> retry -> PENDING
                     -> DEAD_LETTER -> operator retry -> PENDING
```

Retry a dead-letter event only after resolving its underlying issue, such as a
missing domain record or invalid relationship contract. A retry does not
invent graph state; the worker rebuilds the expected projection from the domain
repositories and repairs only actual drift.

Useful commands:

```bash
docker compose logs -f ai-governance-ontology-sync-worker
docker compose ps ai-governance-neo4j-graph ai-governance-neo4j-schema ai-governance-ontology-sync-worker
```

## Persistence, Reset and Backup

Docker volumes retain graph and SQLite data across normal container recreation:

```bash
docker compose down
```

To deliberately remove all local data, including Neo4j and durable sync/audit
events:

```bash
docker compose down -v
docker compose up --build
```

Use the normal Neo4j backup and restore procedures for production data. Take a
consistent backup of the Neo4j database and the authoritative domain stores.
Neo4j can be rebuilt from domain data through reconciliation, but preserving it
retains operational history and avoids unnecessary rebuild time.

## Test the Integration

Fast unit tests keep the in-memory graph path and do not require Neo4j:

```bash
uv run pytest tests/unit/ontology tests/unit/ontology_sync
```

Run Neo4j integration coverage against a running graph:

```bash
export AI_GOVERNANCE_RUN_NEO4J_TESTS=true
uv run pytest tests/integration/ontology tests/integration/ontology_sync
```

Run the targeted smoke flow after schema initialization:

```bash
uv run python smoke_tests/smoke_neo4j_evaluation_result_sync.py
```

The smoke test asserts targeted event projection, Neo4j upsert behavior, and
idempotency. Integration tests additionally cover schema setup, traversal,
durable event recovery, retry from dead letter, and governance evidence
projection.

## Troubleshooting

| Symptom | Likely cause | Action |
| --- | --- | --- |
| `MissingNeo4jDriverError` | Driver dependency is unavailable in a host environment. | Run `uv sync`; ensure the `neo4j` dependency is installed. |
| Schema container fails | Neo4j is not healthy or credentials/database are incorrect. | Check `docker compose logs ai-governance-neo4j-graph ai-governance-neo4j-schema`; verify graph variables. |
| Events remain pending | Worker is unavailable or cannot lease events. | Check worker logs and confirm `AI_GOVERNANCE_ONTOLOGY_SYNC_EVENT_*` uses the shared SQLite volume. |
| Dead-letter event | Contract or source data cannot be reconciled. | Inspect the Sync Events detail, repair the source/contract, then retry explicitly. |
| Audit rows are absent in Studio | MCP and Platform use different audit database paths. | Set every Docker service to `/var/lib/ai-governance/mcp_execution_audit.db`. |
| Graph query omits a node | The entity or relationship may be soft deleted. | Inspect `is_deleted` and archival metadata; live paths intentionally exclude tombstones. |

## Operating Guardrails

- Do not write application data directly with ad-hoc Cypher.
- Do not hard-delete ontology records as part of ordinary synchronization.
- Keep relationship validation in `OntologyService`; synchronizers should never
  bypass it.
- Treat domain repositories as authoritative and Neo4j as a deterministic
  projection.
- Use explicit dead-letter retries rather than silently discarding failures.
