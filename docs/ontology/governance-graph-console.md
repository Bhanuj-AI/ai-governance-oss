# AI Governance Control Plane Studio Ontology Graph

![AI Governance Control Plane logo](../../assets/AI Governance Control Plane%20Deisgn.png)

AI Governance Control Plane Studio is a Next.js application in `console/`. Its ontology graph area
supports read-only exploration of ontology graph data exposed by the Python
Control Plane.

The Studio frontend is intentionally thin:

- REST DTOs are the frontend contract.
- Graph traversal, ontology validation, Neo4j access, lineage, and governance
  semantics stay in the Python backend.
- React Flow renders backend-provided nodes and relationships.
- Frontend filters are passed to graph query APIs instead of deriving hidden
  ontology semantics in the browser.

## Local Development

```bash
cd console
pnpm install
pnpm dev
```

Studio reads the API base URL from:

```text
NEXT_PUBLIC_AI_GOVERNANCE_API_BASE_URL=http://localhost:8000
```

See [Configuration](../reference/CONFIGURATION.md) for all API, Studio, graph,
demo seed, and MCP environment variables.

The default is `http://localhost:8000` when the environment variable is not set.
The AI Governance Control Plane API allows browser requests from `http://localhost:3000` and
`http://127.0.0.1:3000` by default. For a different Studio origin, set
`AI_GOVERNANCE_CORS_ALLOW_ORIGINS` on the API process.

Graph canvas colors can be adjusted with public Studio environment variables:

```text
NEXT_PUBLIC_GRAPH_INPUT_COLOR=#eceae4
NEXT_PUBLIC_GRAPH_OUTPUT_COLOR=#a2e1db
NEXT_PUBLIC_GRAPH_ROOT_COLOR=#e1f7e7
```

Restart `pnpm dev` after changing `NEXT_PUBLIC_*` values.

## Quality Gates

```bash
cd console
pnpm lint
pnpm typecheck
pnpm build
```

## Docker

From the repository root:

```bash
./ai_governance.sh
```

This starts:

- `ai-governance-platform` on `http://localhost:8000`
- `ai-governance-studio` on `http://localhost:3000`
- `neo4j` on `bolt://localhost:7687`
- `seaweedfs` with S3 on `http://localhost:8333` and a Filer UI on
  `http://localhost:8888`

Studio calls the Python REST API only; it does not connect to Neo4j.

## Demo Seed Data

The default Docker stack uses SQLite for durable application records and Neo4j
for ontology projection. On startup it seeds a small demo graph, the
`policy-release-gate` Policy Engine record, and multiple persisted governance
decisions.
To reseed manually, run:

```bash
curl -X POST http://localhost:8000/api/v1/ontology/demo/seed
```

Then open `/graph` and load:

```text
Entity Type: Candidate
Entity ID: candidate-1
Depth: 2
```

![AI Governance Control Plane Ontology](../../assets/AI Governance Control Plane%20Ontology%20Graph.png)

Or open `/decisions` and choose the seeded decision and load:

![AI Governance Control Plane Decisions Index](../../assets/Governance%20Decisions.png)

The seed is idempotent. It creates four candidate evidence graphs, evaluates a
demo release-gate policy, persists approved, proposed-for-review, rejected, and
blocked decisions, and projects matching `GovernanceDecision` ontology nodes
for lineage inspection.

## Assets

The `/assets` area is the registry-centric Studio surface. **Prompt Catalog**
and **Model Catalog** describe observed runtime identities and configuration;
AI Governance Control Plane does not author prompts or define model runtime behavior. **Dataset
Registry** and **Evaluation Providers** are managed AI Governance Control Plane assets. This keeps
the OSS console out of model serving and dataset labeling.

Asset detail routes are version-aware and use a consistent operator workflow:

- **Overview** — registered metadata and versioned configuration.
- **Versions** — immutable versions within the logical asset family.
- **References** — direct ontology relationships for the selected version.
- **Lineage** — a bounded governed neighbourhood, not operational analytics.
- **Audit History** — matching ontology synchronization events.

Dataset registry metadata is distinct from dataset bytes. The local seeded
dataset is stored in SeaweedFS through an S3-compatible URI and can be browsed
in the Filer UI at `http://localhost:8888`. See the
[end-to-end local tutorial](../tutorials/end-to-end-local.md) for the complete
walk-through.

Operators can use **Register dataset** in the Dataset Registry to upload UTF-8
CSV, JSONL, or NDJSON. Studio sends the file to the REST control plane, which
validates it, stores immutable bytes in the configured object store, and
registers a DRAFT dataset version with its checksum and record count.

Prompt and model catalog records expose a per-version provenance badge. Generic
producer integrations can submit **OBSERVED** execution evidence through the
REST API; source system/reference metadata and protected prompt-content hashes
are projected into the ontology alongside the version. This is a neutral OSS
contract—external catalog connectors remain outside the core distribution.

## Policy Engine

The `/policies` area is the Studio authoring surface for governance policy
definitions and policy versions. It uses backend-owned policy administration
contracts and does not evaluate conditions in React.

Routes:

```text
/policies
/policies/new
/policies/[policyId]
/policies/[policyId]/versions/[version]
/policies/[policyId]/versions/[version]/edit
/policies/[policyId]/versions/[version]/simulate
```

The page family supports:

- searchable and filterable policy inventory with explicit submitted queries
  and 10-policy pagination
- policy definition creation with initial draft version
- definition detail separated from active, draft, and historical versions
- read-only version inspection
- draft-only rule and condition editing
- explicit activation and archival actions
- backend simulation with matched conditions, unmatched conditions, and trace
  output

### Policy API Dependencies

```http
GET /api/v1/policy-schema
GET /api/v1/policies
POST /api/v1/policies
GET /api/v1/policies/{policy_id}
POST /api/v1/policies/{policy_id}/versions
GET /api/v1/policies/{policy_id}/versions/{version}
PUT /api/v1/policies/{policy_id}/versions/{version}/draft
POST /api/v1/policies/{policy_id}/versions/{version}/activate
POST /api/v1/policies/{policy_id}/versions/{version}/archive
POST /api/v1/policies/{policy_id}/versions/{version}/simulate
```

All target types, fields, operators, effects, statuses, categories, severities,
and allowed values are loaded from `GET /api/v1/policy-schema`.

## Jobs

The `/jobs` area is the Studio operations surface for asynchronous governance
work. It renders backend job control-plane state and does not implement worker
leasing, scheduling, or execution logic in React.

Local/dev demo seeding populates the Jobs page with ten representative jobs
across queued, running, succeeded, failed, and cancelled states.

The page supports:

- submitted `status` and `job_type` filters
- status summary lanes for queued, running, succeeded, failed, and cancelled jobs
- paginated run inventory
- selected run detail with attempts, inputs, timestamps, result reference, and
  failure reason
- job submission through backend idempotency contracts
- cancel and retry lifecycle actions when permitted by the REST API

### Job API Dependencies

```http
GET /api/v1/jobs
POST /api/v1/jobs
GET /api/v1/jobs/{job_id}
POST /api/v1/jobs/{job_id}/cancel
POST /api/v1/jobs/{job_id}/retry
GET /api/v1/jobs/{job_id}/result
```

## MCP Audit

The `/audit` area is the Studio inspection surface for MCP execution audit
records. It is backed by a dedicated REST read model instead of requiring the
browser to fan out across low-level MCP audit endpoints.

Local/dev demo seeding populates the audit store with representative MCP write
audit records across succeeded, failed, dry-run, and interrupted states.

### Audit API Dependencies

```http
GET /api/v1/audit
GET /api/v1/audit/{audit_id}
GET /api/v1/mcp/audit
GET /api/v1/mcp/audit/{audit_id}
GET /api/v1/mcp/audit/by-request/{request_id}
GET /api/v1/mcp/audit/by-correlation/{correlation_id}
```

The Studio audit read model returns:

- summary metrics for started, interrupted, succeeded, failed, and dry-run records
- available filter values for status, tool, actor, resource type, and operation
- paginated audit inventory with search and derived interruption state
- audit detail with request metadata, linked job context, and correlation-related records

## Graph Explorer

The `/graph` page supports:

- entity type and entity ID lookup
- bounded depth, capped at the backend limit of `5`
- relationship type filters
- optional node type filters for neighbourhood queries
- incoming, outgoing, and bidirectional traversal modes
- node and edge selection details
- manual node rearrangement with reset back to generated layout
- URL-driven loads via `entityType`, `entityId`, and `depth` query parameters

When an Assets detail page opens the ontology, it sends the exact selected
version's ontology type and ID in those query parameters. Graph Explorer
hydrates its toolbar from the request and queries the backend immediately;
the browser never creates a synthetic lineage graph.

The generated layout keeps the selected root central and places upstream and
downstream nodes on opposite sides. It intentionally bounds dense columns so
wide seeded neighbourhoods remain inspectable. **Reset layout** restores this
generated arrangement after manual repositioning.

![AI Governance Control Plane Ontology Highlighted Selection](../../assets/AI Governance Control Plane%20Ontology%20Graph%20-%20Highlighted.png)

Node IDs are ontology entity IDs. Edge IDs are ontology relationship IDs.

## Decision Visual Inspection

The `/decisions/{decisionId}` page provides an end-to-end read-only inspection
view for one persisted governance decision. It is designed for operators who
already have a decision ID from an API response, MCP tool result, audit trail,
or investigation workflow.

![AI Governance Control Plane Decisions Index](../../assets/Governance%20Decisions.png)

Use `/decisions` to list persisted governance decisions and click through to
the visual detail page. The list page uses `GET /api/v1/decisions`, displays
results newest-first, paginates the local result set, and includes a decision
ID lookup form that opens `/decisions/{decisionId}` directly.

### Decision Summary
- decision summary and target metadata
- outcome status, confidence, latest job/audit status, and metric scores
- policy evaluation outcomes from the persisted reasoning read model

  ![AI Governance Control Plane Decisions Index](../../assets/Governance%20Decisions%20-%20BLOCKED.png)

### Decision Evidence Graph
- deterministic reasoning explanation timeline
- evidence graph rendered with React Flow

  ![AI Governance Control Plane Decisions Index](../../assets/Governance%20Decisions%20-%20BLOCKED%20-%20Evidence%20Graph.png)

### Decision Lineage
- ontology lineage graph rendered separately from the evidence graph
- audit records and request/correlation metadata

    ![AI Governance Control Plane Decisions Index](../../assets/Governance%20Decisions%20-%20BLOCKED%20-%20Decision%20Lineage.png)

Studio intentionally does not reconstruct policy or evidence semantics in
the browser. It consumes backend read models and renders them directly.

### API Dependencies

```http
GET /api/v1/decisions
GET /api/v1/decisions/{decision_id}/detail
GET /api/v1/decisions/{decision_id}/evidence
GET /api/v1/decisions/{decision_id}/explanation
GET /api/v1/decisions/{decision_id}/lineage?depth=2
```

The detail endpoint supplies the source-of-truth decision summary, evidence
summary, policy outcomes, and audit records. The evidence, explanation, and
lineage sections load independently so a partial backend failure is isolated to
the affected section. A `404` on the detail endpoint is shown as a not-found
state for the whole page.

### Visual QA Notes

- Evidence and lineage graphs are separate canvases with independent empty,
  loading, and error states.
- Evidence graph node IDs are keyed by `entity_type` plus `entity_id`, so
  same-ID entities of different ontology types remain distinct in the canvas.
- Lineage uses the backend ontology subgraph response and does not derive
  lineage relationships in the frontend.
- Long IDs are truncated in fixed-size fields to prevent layout shifts.
