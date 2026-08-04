# Smoke Scripts

These scripts are reference flows for manually testing Kavach without external
services. They use FastAPI `TestClient`, seeded data, and MCP in-process calls.

Run from the repository root with `uv run python`.

## MCP Audit Flow

```bash
uv run python scripts/smoke_mcp_audit_flow.py
```

Optional persistent audit DB:

```bash
uv run python scripts/smoke_mcp_audit_flow.py --audit-db /tmp/kavach-mcp-audit-smoke.db
```

Covers:

- durable audit seed data
- REST audit list/get/by-request/by-correlation
- MCP audit read tool
- dry-run write audit creation
- sensitive summary redaction
- interrupted `STARTED` detection

## MCP Controlled Write Flow

```bash
uv run python scripts/smoke_mcp_write_flow.py
```

Optional persistent audit DB:

```bash
uv run python scripts/smoke_mcp_write_flow.py --audit-db /tmp/kavach-mcp-write-smoke.db
```

Covers:

- `evaluation.submit_async`
- `experiment.create`
- `job.status`
- `job.cancel`
- `mcp_audit.find_by_correlation`
- REST job submission through MCP
- MCP write audit creation

## MCP Read Tool Flow

```bash
uv run python scripts/smoke_mcp_read_flow.py
```

Covers:

- seeded synchronous evaluation
- seeded experiment
- `provider.list`
- `evaluation.latest`
- `evaluation.history`
- `evaluation.metrics`
- `experiment.list`
- `experiment.get`

## MCP JSON-RPC Flow

```bash
uv run python scripts/smoke_mcp_jsonrpc_flow.py
```

Covers:

- `initialize`
- `tools/list`
- `tools/call`
- JSON-RPC response shape used by stdio-style MCP clients

## Governance Insights Flow

```bash
uv run python scripts/smoke_governance_insights_flow.py
```

Covers:

- experiment insight API
- candidate insight API
- comparative insight API
- investigation by correlation, job, and audit
- drift explanation API
- evaluation drift explanation API
- experiment and investigation report APIs
- matching MCP governance tools for insights, investigation, and reports

## REST Control Plane Flow

```bash
uv run python scripts/smoke_rest_control_plane_flow.py
```

Covers:

- health/readiness/API metadata
- provider discovery
- synchronous evaluation submission
- governance compare/drift
- experiment creation
- job submission/list/cancel

## Job Worker Flow

```bash
uv run python scripts/smoke_job_worker_flow.py
```

Covers:

- job submission service
- queued job acquisition
- worker success path
- worker failure path
- final repository lifecycle state

## SQLite Persistence Flow

```bash
uv run python scripts/smoke_sqlite_persistence_flow.py
```

Optional persistent database:

```bash
uv run python scripts/smoke_sqlite_persistence_flow.py --database /tmp/kavach-sqlite-smoke.db
```

Covers:

- SQLite schema initialization
- SQLite job repository persistence
- durable MCP audit persistence
- reopening the DB through fresh repository/log instances
- sensitive audit summary redaction

## Ontology Reconciliation Flow

```bash
uv run python scripts/smoke_ontology_reconciliation_flow.py
```

Covers:

- no-write projection building
- deterministic projection and relationship fingerprints
- first-run ontology repair
- second-run skip when hashes match
- targeted relationship drift repair
- scoped semantic drift repair
- reconciliation report metrics for scanned, skipped, repaired, failures,
  duration, and skip ratio
- persisted reconciliation metadata

## Ontology Event Sync Flow

```bash
uv run python scripts/smoke_ontology_event_sync_flow.py
```

Covers:

- durable event publication into the ontology sync event store
- background worker processing through diff-based reconciliation
- completed event report metrics
- duplicate event idempotency and skip metrics

## Ontology Graph Query Flow

```bash
uv run python scripts/smoke_ontology_graph_query_flow.py
```

Covers:

- ontology entity lookup
- relationship pagination
- downstream traversal
- path discovery with relationship filters
- MCP graph query tool forwarding through REST
