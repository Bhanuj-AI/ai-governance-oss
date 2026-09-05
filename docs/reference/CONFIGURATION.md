# Configuration

This page summarizes the environment variables used by local development,
AI Governance Control Plane Studio, the REST API, ontology graph adapters, and MCP integrations.

For the default local stack, start Keycloak before starting the platform Compose
stack. Override these
values when running services outside Docker, changing ports, disabling demo
data, or connecting external storage and graph services.

## Local Quick Start

```bash
./servers.sh
```

`./servers.sh` validates the Compose definition and runs `docker compose up
--build -d`. The platform Compose stack starts:

- REST API on `http://localhost:8000`
- AI Governance Control Plane Studio on `http://localhost:3000`
- Neo4j on `bolt://localhost:7687`
- SeaweedFS S3 API on `http://localhost:8333`
- SeaweedFS Filer UI on `http://localhost:8888`
- SeaweedFS Master UI on `http://localhost:9333`

The local API starts with demo ontology data, the `policy-release-gate` Policy
Engine record, governance decisions, representative jobs, and MCP audit data.
Set `AI_GOVERNANCE_AUTO_SEED_DEMO_DATA=false` to disable startup demo seeding.

Compose selects SQLite for every repository that supports it and points those
repositories at `/var/lib/ai-governance/governance.db`. The `ai-governance_sqlite_data` named
volume mounts that directory into `ai-governance-platform`, so application records
survive container restarts and recreation. Neo4j data is retained separately
in the `neo4j_data` and `neo4j_logs` volumes. SeaweedFS dataset objects are
retained in the `seaweedfs_data` volume.

```bash
# Stop containers while preserving SQLite, Neo4j, and SeaweedFS data.
docker compose down

# Remove all local persistent data; the next startup creates a clean demo seed.
docker compose down -v
./servers.sh
```

Startup seeding uses stable identifiers and SQLite upserts, making repeated
local starts safe. The Compose health checks start Neo4j and SeaweedFS first,
then wait for platform `/ready` before starting Studio and workers. SeaweedFS
uses the standard S3 API locally, so the demo dataset registry record points to
an `s3://` URI rather than embedding dataset content in SQLite.

### Host-local API mode

When running the API directly with Uvicorn, Docker Compose does not load
`.env.platform` for you. Use the ignored root `.env.local` file, which contains
the same required platform settings adapted for host execution:

```bash
# Start Keycloak and PostgreSQL.
./scripts/keycloak/start-keycloak.sh

# From the repository root, start the graph dependency if graph features are used.
docker compose up -d neo4j

# Start the API with host-local SQLite and localhost service addresses.
uvicorn ai_governance.api.app:app --reload --env-file .env.local
```

The host-local file uses `AI_GOVERNANCE_AUTH_MODE=keycloak`, SQLite at
`./governance.local.db`, Neo4j at `bolt://localhost:7687`, and Keycloak at
`http://keycloak.localhost:8080/realms/ai-governance`. Start Studio separately from `console/`;
its ignored `console/.env.local` provides the browser-facing Keycloak settings.

To run the API without Keycloak for a lightweight development session, set
`AI_GOVERNANCE_AUTH_MODE=development` in `.env.local`. In that mode requests use the
development actor headers and no JWT is validated. Do not use this mode for
production or shared environments.

`.env.platform` is intended for the Docker Compose platform container. It uses
container DNS names such as `neo4j`, and its `/var/lib/ai-governance/governance.db` path is
inside the container volume. Do not use those values unchanged for a host-local
Uvicorn process.

### Local Keycloak

The default Compose stack starts Keycloak at
`http://keycloak.localhost:8080`. Start the local Keycloak and PostgreSQL stack:

```bash
./servers.sh
```

The Keycloak realm import is only applied when its PostgreSQL data volume is
new. The local startup launcher reconciles promoted service clients that are
required by current local workflows, including `synthetic-agent-runtime`, on
existing development volumes. To deliberately recreate the entire local realm, run
`docker compose down -v` from `keycloak-postgres/` and then run
`./scripts/keycloak/start-keycloak.sh`.
This removes local Keycloak users, sessions, and clients.

For a complete operator walk-through of the seeded registry and lineage data,
see the [end-to-end local tutorial](../tutorials/end-to-end-local.md).

## REST API

| Variable | Default | Purpose |
| --- | --- | --- |
| `AI_GOVERNANCE_API_HOST` | `127.0.0.1` | Host used by local API settings and dev/local detection. |
| `AI_GOVERNANCE_API_PORT` | `8000` | API port used by local API settings. |
| `AI_GOVERNANCE_API_LOG_LEVEL` | `INFO` | REST API logger level. |
| `AI_GOVERNANCE_CORS_ALLOW_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Comma-separated browser origins allowed to call the API. |
| `AI_GOVERNANCE_ENV` | `local` | Runtime environment label. `local`, `dev`, and `development` are treated as development environments for demo seeding. |
| `AI_GOVERNANCE_AUTO_SEED_DEMO_DATA` | auto | Enables or disables startup demo data seeding. Use `true` or `false` to override auto-detection. |

## Authentication

AI Governance Control Plane supports two authentication modes controlled by `AI_GOVERNANCE_AUTH_MODE`.
Development mode preserves the existing header-based identity for local
development. Keycloak mode requires JWT authentication against a running
Keycloak instance.

| Variable | Default | Purpose |
| --- | --- | --- |
| `AI_GOVERNANCE_AUTH_MODE` | `development` | Authentication mode: `development` or `keycloak`. |
| `AI_GOVERNANCE_OIDC_ISSUER` | - | Keycloak realm URL (for local development, `http://keycloak.localhost:8080/realms/ai-governance`). Required when `AI_GOVERNANCE_AUTH_MODE=keycloak`. |
| `AI_GOVERNANCE_OIDC_JWKS_REFRESH_SECONDS` | `300` | JWKS signing key cache TTL in seconds. Controls how often the platform fetches new signing keys from Keycloak. |

Development mode (`AI_GOVERNANCE_AUTH_MODE=development`):

- Actor identity comes from `X-AI-Governance-Actor-Id` header or
  `AI_GOVERNANCE_DEVELOPMENT_ACTOR_ID` environment variable.
- No JWT validation occurs.
- Existing header-based behaviour is preserved.

Keycloak mode (`AI_GOVERNANCE_AUTH_MODE=keycloak`):

- Requires `Authorization: Bearer <token>` header on every request.
- Validates JWT signature against Keycloak JWKS endpoint.
- Validates issuer matches `AI_GOVERNANCE_OIDC_ISSUER`.
- Validates token expiry (rejects expired tokens).
- Builds `AuthenticatedPrincipal` from validated claims:
  - `sub` → actor identity (immutable)
  - `principal_type` → USER, SERVICE, or SYSTEM
  - `organization_id` → optional scope hint
  - `azp` or `client_id` → client identifier
- Missing or invalid JWT returns HTTP 401.

The authentication plane is strictly separate from authorization. JWT claims
establish identity only; they never grant permissions. Every request still flows
through the existing `AuthorizationService` and RBAC model.

### Bootstrap administrator identity

The initial AI Governance Control Plane administrator is provisioned during control-plane bootstrap
(idempotent). The identity used depends on `AI_GOVERNANCE_AUTH_MODE`:

- **Development mode** — uses `AI_GOVERNANCE_DEVELOPMENT_ACTOR_ID` (fallback:
  `local-admin`) and `AI_GOVERNANCE_DEVELOPMENT_ACTOR_NAME` (fallback:
  `Local Administrator`).
- **Keycloak mode** — requires `AI_GOVERNANCE_BOOTSTRAP_ADMIN_SUB` (the immutable
  Keycloak user `sub`). Fails startup if absent. Optionally uses
  `AI_GOVERNANCE_BOOTSTRAP_ADMIN_NAME` for display purposes.

| Variable | Default | Purpose |
| --- | --- | --- |
| `AI_GOVERNANCE_BOOTSTRAP_ADMIN_SUB` | - | Keycloak user `sub` for the initial administrator. Required when `AI_GOVERNANCE_AUTH_MODE=keycloak`. Must match the JWT `sub` claim. |
| `AI_GOVERNANCE_BOOTSTRAP_ADMIN_NAME` | - | Display name for the initial administrator. Optional in keycloak mode. |

Demo seeding auto-detection is enabled only for local/dev environments on
`127.0.0.1`, `localhost`, or `0.0.0.0`, and is disabled during pytest runs
unless explicitly overridden.

## AI Governance Control Plane Studio

| Variable | Default | Purpose |
| --- | --- | --- |
| `NEXT_PUBLIC_AI_GOVERNANCE_API_BASE_URL` | `http://localhost:8000` | REST API base URL used by the Next.js Studio. |
| `NEXT_PUBLIC_KEYCLOAK_URL` | - | Keycloak server URL used by the browser client, for example `http://keycloak.localhost:8080`. |
| `NEXT_PUBLIC_KEYCLOAK_REALM` | - | Keycloak realm used by Studio, for example `ai-governance`. |
| `NEXT_PUBLIC_KEYCLOAK_CLIENT_ID` | - | Public Keycloak client ID used by Studio, for example `ai-governance-studio`. |
| `NEXT_PUBLIC_GRAPH_*` | see `console/.env.example` | Optional graph palette colors for ontology visualization. Restart Studio after changing these values. |

The `NEXT_PUBLIC_*` variables above are browser-facing Next.js variables and are
compiled into the Studio bundle. For Docker builds, pass them as
`ai-governance-studio` build argument in `docker-compose.yml`; changing only the
container runtime environment does not update an existing browser bundle. The
Studio does not use a client secret: it authenticates with Authorization Code
Flow and PKCE.
Rebuild Studio after changing it:

```bash
docker compose up --build -d ai-governance-studio
```

When running Studio outside Docker:

```bash
cd console
pnpm install
pnpm dev
```

For local Studio development, Next.js loads `console/.env.local`. The file
contains the public API and Keycloak client settings; restart `pnpm dev` after
changing them. `.env.studio` is used by Docker Compose and is not loaded
automatically by Next.js.

If the REST API is not on `http://localhost:8000`, set
`NEXT_PUBLIC_AI_GOVERNANCE_API_BASE_URL` before starting Studio.

See [Keycloak integration design](../architecture/KEYCLOAK_INTEGRATION.md) for
the token lifecycle, required realm configuration, and tenant authorization
flow.

## Settings Control Plane

AI Governance Control Plane exposes typed platform configuration through `GET /api/v1/settings`
and the Studio `/settings` page. Resolution is deterministic: an environment
variable wins over a persisted runtime value, which wins over the registry
default. Environment-controlled and deployment settings remain read-only.

| Variable | Default | Purpose |
| --- | --- | --- |
| `AI_GOVERNANCE_SETTINGS_REPOSITORY` | `inmemory` | Runtime settings backend: `inmemory`, `sqlite`, or `postgres`. |
| `AI_GOVERNANCE_SETTINGS_SQLITE_PATH` | - | SQLite database path when the settings backend is `sqlite`. |
| `AI_GOVERNANCE_SETTINGS_POSTGRES_DSN` | - | PostgreSQL DSN when the settings backend is `postgres`. |

`model_registry.allowed_runtime_providers` is a live, tenant-scoped JSON
setting that controls which built-in runtime providers can be used for managed
model registration. The default allows the complete built-in vocabulary,
including `custom`; project or organization administrators can restrict it to
their approved runtimes. Observed model evidence is never rejected by this
policy, because it records runtime reality rather than a declaration.

The local Compose stack uses the shared durable SQLite database. Runtime
updates are validated, versioned, and recorded in `setting_audit` with actor,
reason, old value, and new value. Static deployment architecture—including
repository selection, connection endpoints, and identity configuration—must
continue to be changed through Infrastructure-as-Code and restarted.

Compose does not populate operational variables merely to repeat registry
defaults; doing so would intentionally make those controls read-only.
Operational environment overrides should only be set when Infrastructure-as-
Code must pin a value. The corresponding variables are documented by each
setting returned from the API. Examples include
`AI_GOVERNANCE_JOB_WORKER_CONCURRENCY`, `AI_GOVERNANCE_JOB_RETRY_ATTEMPTS`,
`AI_GOVERNANCE_EVALUATION_PASS_THRESHOLD`, and
`AI_GOVERNANCE_ONTOLOGY_RECONCILIATION_INTERVAL`.

For plain-English, end-to-end behavior and persistence details for every
registered setting, see
[Settings Control Plane](../architecture/SETTINGS_CONTROL_PLANE.md).

## Ontology Graph

| Variable | Default | Purpose |
| --- | --- | --- |
| `AI_GOVERNANCE_GRAPH_URI` | `bolt://localhost:7687` | Neo4j Bolt URI for graph-backed ontology adapters. |
| `AI_GOVERNANCE_GRAPH_USER` | `neo4j` | Neo4j username. |
| `AI_GOVERNANCE_GRAPH_PASSWORD` | `ai-governance-local-password` | Neo4j password. |
| `AI_GOVERNANCE_GRAPH_DATABASE` | `neo4j` | Neo4j database name. |
| `AI_GOVERNANCE_RUN_NEO4J_TESTS` | `false` | Set to `true` to run Neo4j integration tests. |

The REST API currently uses in-memory repositories by default. These graph
variables are needed for Neo4j-backed graph adapters and integration tests.
For schema initialization, event recovery, safe retries, persistence, and
troubleshooting, see the [Neo4j Operations Guide](../ontology/neo4j-operations-guide.md).

## MCP Server

| Variable | Default | Purpose |
| --- | --- | --- |
| `AI_GOVERNANCE_API_URL` | `http://127.0.0.1:8000` | REST API URL used by MCP tool calls. |
| `AI_GOVERNANCE_API_TIMEOUT` | `10` | REST request timeout in seconds for MCP clients. |
| `AI_GOVERNANCE_API_RETRIES` | `0` | REST retry count for MCP clients. |
| `LOG_LEVEL` | `INFO` | MCP server log level. |
| `AI_GOVERNANCE_MCP_AUDIT_REPOSITORY` | `sqlite` | MCP audit backend: `sqlite` or `postgres`. |
| `AI_GOVERNANCE_MCP_AUDIT_DATABASE_PATH` | `.ai-governance/mcp_execution_audit.db` | SQLite audit database path (required by the `sqlite` backend). |
| `AI_GOVERNANCE_MCP_AUDIT_POSTGRES_DSN` | - | PostgreSQL DSN (required by the `postgres` backend). |
| `AI_GOVERNANCE_MCP_HOST` | `127.0.0.1` | Host for the optional MCP-over-HTTP adapter. |
| `AI_GOVERNANCE_MCP_PORT` | `8001` | Port for the optional MCP-over-HTTP adapter. |
| `AI_GOVERNANCE_MCP_URL` | - | API health-check URL for the MCP-over-HTTP adapter. |
| `AI_GOVERNANCE_API_TOKEN` | - | Optional bearer token used by MCP when calling a Keycloak-protected API. Never commit this value. |
| `AI_GOVERNANCE_MCP_CLIENT_ID` | `ai-governance-mcp` | Keycloak confidential client used by MCP. |
| `AI_GOVERNANCE_MCP_CLIENT_SECRET` | - | MCP client secret. Never commit this value. |
| `AI_GOVERNANCE_MCP_TOKEN_URL` | - | Keycloak client-credentials token endpoint. |
| `AI_GOVERNANCE_MCP_ACTOR_ID` | generated | MCP service-account subject used for startup membership provisioning. Generated into `.env.service-accounts.generated`; do not hardcode it for fresh environments. |
| `AI_GOVERNANCE_WALKTHROUGH_ACTOR_ID` | generated | Walkthrough service-account subject provisioned with its own membership and role. Generated into `.env.service-accounts.generated`. |
| `AI_GOVERNANCE_MCP_TRANSPORT` | `stdio` | MCP runtime transport: `stdio` or `streamable-http`. MCPO remains a separate stdio wrapper. |
| `AI_GOVERNANCE_MCP_HTTP_HOST` | `127.0.0.1` | Native Streamable HTTP bind host. Set `0.0.0.0` explicitly for a container or ingress deployment. |
| `AI_GOVERNANCE_MCP_HTTP_PORT` | `8002` | Native Streamable HTTP port. |
| `AI_GOVERNANCE_MCP_HTTP_PATH` | `/mcp` | Native MCP protocol endpoint path. |
| `AI_GOVERNANCE_MCP_PUBLIC_URL` | `http://localhost:8002` | Public origin used to publish OAuth protected-resource metadata and validate the MCP token audience. It must match the externally reachable MCP origin and the Keycloak audience mapper. |
| `AI_GOVERNANCE_MCP_HTTP_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated Host values allowed by MCP DNS-rebinding protection. Configure production values explicitly. |
| `AI_GOVERNANCE_MCP_HTTP_ALLOWED_ORIGINS` | empty | Optional comma-separated browser origins allowed by MCP origin validation and CORS preflight. Local Inspector defaults use `http://localhost:6274,http://127.0.0.1:6274`; configure production browser origins explicitly. |
| `AI_GOVERNANCE_MCP_HTTP_STATELESS` | `true` | Creates a fresh SDK transport per HTTP request; no affinity or server-side session store is required. |
| `AI_GOVERNANCE_MCP_HTTP_JSON_RESPONSE` | `true` | Uses JSON for ordinary Streamable HTTP replies while retaining SDK SSE support where needed. |

The repository includes `scripts/mcp/start-mcp.sh`, which wraps the existing stdio
MCP server with `mcpo` and exposes it as an HTTP/OpenAPI service on port 8001.
See [MCP Usage and MCPO](./MCP_USAGE.md) for the architecture, startup
commands, and Keycloak token requirements.
In Docker, the `ai-governance-mcp` service starts alongside the platform and uses
`http://ai-governance-platform:8000` for REST calls:

```bash
docker compose up --build -d
curl http://localhost:8001/openapi.json
```

For host-local development, start the API first and then run:

```bash
./scripts/mcp/start-mcp.sh
```

When `AI_GOVERNANCE_AUTH_MODE=keycloak`, MCP REST calls require a valid bearer token.
The `ai-governance-mcp` client-credentials token is refreshed automatically. The MCP
adapter does not invent an actor or bypass AI Governance Control Plane tenant authorization. In
development mode, the existing header-based REST behavior remains available.

The native endpoint is `http://localhost:8002/mcp`; it is MCP protocol traffic,
not a REST or OpenAPI endpoint. Its `/health` and `/ready` probes are available
without credentials. In Keycloak mode every MCP request requires a caller
bearer token; that exact token is forwarded to the REST control plane, where
the token subject, tenant membership, and RBAC are enforced.

## OAuth client credentials

`AI_GOVERNANCE_OAUTH_*` is AI Governance Control Plane's workload-neutral client-credentials interface.
The guided `ai-governance walkthrough` CLI automatically exchanges these credentials
for a short-lived service-account token in memory; do not export or manage a
bearer token for the normal local or CI flow:

| Variable | Purpose |
| --- | --- |
| `AI_GOVERNANCE_OAUTH_TOKEN_URL` | OAuth/OIDC token endpoint for the confidential client. |
| `AI_GOVERNANCE_OAUTH_CLIENT_ID` | Dedicated workload identity, such as `ai-governance-walkthrough`. |
| `AI_GOVERNANCE_OAUTH_CLIENT_SECRET` | Client secret from a secrets manager or protected CI environment. Never commit it. |

Use `scripts/oauth/fetch-access-token.py --clipboard` when a generic local
tool needs a bearer token pasted into another client. It never prints or saves
the token. The walkthrough itself does not need this utility.

For local compatibility only, the existing complete `AI_GOVERNANCE_MCP_CLIENT_ID`,
`AI_GOVERNANCE_MCP_CLIENT_SECRET`, and `AI_GOVERNANCE_MCP_TOKEN_URL` set is used when generic
OAuth variables are absent. Do not reuse that MCP identity for production
walkthroughs; provision a least-privilege service account with AI Governance Control Plane
membership and roles for the intended organization/project. The local
`ai-governance-walkthrough` client receives `GOVERNANCE_ADMIN`, the narrowest current
built-in role that can observe prompt/model evidence and prepare or submit the
complete governed-replay scenario; it is not an organization administrator.
Existing local walkthrough identities created before this role was introduced
are upgraded automatically when the platform starts.

The local Keycloak bootstrap declares that dedicated client as
`ai-governance-walkthrough`. `scripts/keycloak/get-service-account-actorids.sh`
discovers its immutable subject, writes the tenant-provisioning file, and also
creates `.env.oauth.generated` for host-local OAuth configuration. The file is
loaded by the walkthrough CLI and generic OAuth helper, but remains ignored by
Git because it contains a local client secret.

`--token` is available as an explicit walkthrough CLI override for callers
that already manage a bearer token. The CLI deliberately does not read
`AI_GOVERNANCE_TOKEN` from the shell, preventing a stale export from overriding the
configured OAuth workload identity.

## Optional Provider Settings

| Variable | Required when | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | TruLens / OpenAI-backed evaluation or judge flows | OpenAI API key. |
| `OPENAI_DEFAULT_JUDGE_MODEL` | TruLens / OpenAI-backed judge flows | Default judge model identifier. |
| `AI_GOVERNANCE_TRULENS_MODEL` | TruLens evaluation | Optional explicit judge-model override; otherwise `OPENAI_DEFAULT_JUDGE_MODEL` is used. |

The REST API always registers the deterministic `mock` provider. It also
registers `trulens` when both an OpenAI API key and judge model are configured.
Use `AI_GOVERNANCE_TRULENS_MODEL` to override `OPENAI_DEFAULT_JUDGE_MODEL` for
TruLens. Mock remains the default for a fully offline local stack.

OpenAI-backed TruLens evaluations require `trulens-providers-openai>=2.10.0`.
The locked OSS environment supplies this version or newer; do not downgrade it,
because earlier releases can misread OpenAI Responses API custom tool-call
scores.

### Runtime connections

`OPENAI_API_KEY` is a deployment-owned platform credential for internal
capabilities such as OpenAI-backed evaluation or judge flows. It is not a
tenant or project runtime credential.

Create tenant-owned **Runtime Connections** from **Settings → Runtime
Connections** when a registered model must be invoked. A connection holds a
provider, optional endpoint/organization metadata, scope, enablement state,
and a secret reference such as `env://OPENAI_DEVELOPMENT_API_KEY`; no raw key
is persisted or returned. Connections can be updated as credentials rotate,
without creating a new managed model version. OSS ships native model discovery
and invocation for OpenAI and Anthropic. OpenAI-compatible custom endpoints can
be invoked with an operator-supplied registered model identifier. The allowed
managed model-provider setting is a tenant policy; it does not install an
adapter for another provider.

See [Configure Runtime Connections](../tutorials/configure-runtime-connections.md)
for Studio and REST workflows, credential rotation, scope semantics, and the
current OSS invocation boundary.

## Test Backends

Some repository integration tests require additional backend-specific
configuration:

- PostgreSQL tests require `AI_GOVERNANCE_POSTGRES_DSN`.
- Snowflake tests require the `AI_GOVERNANCE_SNOWFLAKE_*` variables documented in
  [Snowflake Schema](./SNOWFLAKE_SCHEMA.md).
- Neo4j tests require `AI_GOVERNANCE_RUN_NEO4J_TESTS=true` and the graph variables
  above.


## Repository Backends

AI Governance Control Plane uses a factory-based repository construction model. Each repository type
is configured independently via environment variables. The default for every
repository is ``inmemory``. Durable backends require their respective connection
parameters; factories fail fast if they are missing.

These defaults describe a process started directly from the Python package.
The checked-in Docker Compose configuration overrides every SQLite-capable
repository to `sqlite` and uses the shared path
`/var/lib/ai-governance/governance.db`. Ontology graph storage remains separately
configured because `AI_GOVERNANCE_ONTOLOGY_REPOSITORY=sqlite` is not implemented.

### Configuration Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `AI_GOVERNANCE_POLICY_REPOSITORY` | `inmemory` | Policy administration backend. Options: `inmemory`, `sqlite`, `postgres`. |
| `AI_GOVERNANCE_POLICY_SQLITE_PATH` | - | SQLite path for policy repository (required when `sqlite`). |
| `AI_GOVERNANCE_POLICY_POSTGRES_DSN` | - | PostgreSQL DSN for policy repository (required when `postgres`). |
| `AI_GOVERNANCE_EVALUATION_REPOSITORY` | `inmemory` | Evaluation result backend. Options: `inmemory`, `sqlite`, `postgres`. |
| `AI_GOVERNANCE_EVALUATION_SQLITE_PATH` | - | SQLite path for evaluation repository (required when `sqlite`). |
| `AI_GOVERNANCE_EVALUATION_POSTGRES_DSN` | - | PostgreSQL DSN (required when `postgres`). |
| `AI_GOVERNANCE_EXPERIMENT_REPOSITORY` | `inmemory` | Experiment metadata backend. Options: `inmemory`, `sqlite`, `postgres`. |
| `AI_GOVERNANCE_EXPERIMENT_SQLITE_PATH` | - | SQLite path for experiment repository (required when `sqlite`). |
| `AI_GOVERNANCE_EXPERIMENT_POSTGRES_DSN` | - | PostgreSQL DSN (required when `postgres`). |
| `AI_GOVERNANCE_EXPERIMENT_CANDIDATE_REPOSITORY` | `inmemory` | Experiment candidate backend. Options: `inmemory`, `sqlite`, `postgres`. |
| `AI_GOVERNANCE_EXPERIMENT_CANDIDATE_SQLITE_PATH` | - | SQLite path (required when `sqlite`). |
| `AI_GOVERNANCE_EXPERIMENT_CANDIDATE_POSTGRES_DSN` | - | PostgreSQL DSN (required when `postgres`). |
| `AI_GOVERNANCE_EVALUATION_RUN_REPOSITORY` | `inmemory` | Evaluation run backend. Options: `inmemory`, `sqlite`, `postgres`. |
| `AI_GOVERNANCE_EVALUATION_RUN_SQLITE_PATH` | - | SQLite path (required when `sqlite`). |
| `AI_GOVERNANCE_EVALUATION_RUN_POSTGRES_DSN` | - | PostgreSQL DSN (required when `postgres`). |
| `AI_GOVERNANCE_LEADERBOARD_REPOSITORY` | `inmemory` | Leaderboard backend. Options: `inmemory`, `sqlite`, `postgres`. |
| `AI_GOVERNANCE_LEADERBOARD_SQLITE_PATH` | - | SQLite path (required when `sqlite`). |
| `AI_GOVERNANCE_LEADERBOARD_POSTGRES_DSN` | - | PostgreSQL DSN (required when `postgres`). |
| `AI_GOVERNANCE_PROMPT_REPOSITORY` | `inmemory` | Prompt artifact backend. Options: `inmemory`, `sqlite`, `postgres`. |
| `AI_GOVERNANCE_PROMPT_SQLITE_PATH` | - | SQLite path (required when `sqlite`). |
| `AI_GOVERNANCE_PROMPT_POSTGRES_DSN` | - | PostgreSQL DSN (required when `postgres`). |
| `AI_GOVERNANCE_MODEL_REPOSITORY` | `inmemory` | Model artifact backend. Options: `inmemory`, `sqlite`, `postgres`. |
| `AI_GOVERNANCE_MODEL_SQLITE_PATH` | - | SQLite path (required when `sqlite`). |
| `AI_GOVERNANCE_MODEL_POSTGRES_DSN` | - | PostgreSQL DSN (required when `postgres`). |
| `AI_GOVERNANCE_DATASET_REPOSITORY` | `inmemory` | Dataset artifact backend. Options: `inmemory`, `sqlite`, `postgres`. |
| `AI_GOVERNANCE_DATASET_SQLITE_PATH` | - | SQLite path (required when `sqlite`). |
| `AI_GOVERNANCE_DATASET_POSTGRES_DSN` | - | PostgreSQL DSN (required when `postgres`). |
| `AI_GOVERNANCE_DATASET_OBJECT_STORE_BACKEND` | `none` | Dataset content store. Options: `none`, `filesystem`, `s3`. The registry metadata remains in the dataset repository. |
| `AI_GOVERNANCE_DATASET_FILESYSTEM_ROOT` | `.ai-governance/datasets` | Root for immutable dataset objects when the backend is `filesystem`; intended for the non-Docker local workflow. |
| `AI_GOVERNANCE_DATASET_S3_BUCKET` | `ai-governance-datasets` | Bucket for dataset content when the object-store backend is `s3`. |
| `AI_GOVERNANCE_DATASET_S3_ENDPOINT_URL` | - | Optional S3-compatible endpoint. Leave unset for AWS S3; set for SeaweedFS or another compatible service. |
| `AI_GOVERNANCE_DATASET_S3_REGION` | `us-east-1` | S3 region. |
| `AI_GOVERNANCE_DATASET_S3_ACCESS_KEY_ID` | - | Optional static S3 access key. When unset, the standard AWS credential chain is used. |
| `AI_GOVERNANCE_DATASET_S3_SECRET_ACCESS_KEY` | - | Optional static S3 secret key. |
| `AI_GOVERNANCE_DATASET_S3_FORCE_PATH_STYLE` | endpoint-dependent | Use path-style S3 addressing; required by the checked-in SeaweedFS development service. |
| `AI_GOVERNANCE_DATASET_MAX_UPLOAD_BYTES` | `10485760` | Maximum multipart dataset upload size (10 MiB). Uploads support UTF-8 CSV, JSONL, and NDJSON. |
| `AI_GOVERNANCE_DATASET_MAX_RECORD_BYTES` | `1048576` | Maximum encoded size of one CSV row or JSONL record (1 MiB). |
| `AI_GOVERNANCE_DATASET_MAX_FIELDS` | `256` | Maximum fields in one CSV row or JSONL object. |
| `AI_GOVERNANCE_JOB_REPOSITORY` | `inmemory` | Job execution backend. Options: `inmemory`, `sqlite`, `postgres`. |
| `AI_GOVERNANCE_JOB_SQLITE_PATH` | - | SQLite path (required when `sqlite`). |
| `AI_GOVERNANCE_JOB_POSTGRES_DSN` | - | PostgreSQL DSN (required when `postgres`). |
| `AI_GOVERNANCE_GOVERNANCE_DECISION_REPOSITORY` | `inmemory` | Governance decision backend. Options: `inmemory`, `sqlite`, `postgres`. |
| `AI_GOVERNANCE_GOVERNANCE_DECISION_SQLITE_PATH` | - | SQLite path (required when `sqlite`). |
| `AI_GOVERNANCE_GOVERNANCE_DECISION_POSTGRES_DSN` | - | PostgreSQL DSN (required when `postgres`). |
| `AI_GOVERNANCE_ONTOLOGY_SYNC_EVENT_REPOSITORY` | `inmemory` | Ontology sync event backend. Options: `inmemory`, `sqlite`, `postgres`. |
| `AI_GOVERNANCE_ONTOLOGY_SYNC_EVENT_SQLITE_PATH` | - | SQLite path (required when `sqlite`). |
| `AI_GOVERNANCE_ONTOLOGY_SYNC_EVENT_POSTGRES_DSN` | - | PostgreSQL DSN (required when `postgres`). |
| `AI_GOVERNANCE_ONTOLOGY_REPOSITORY` | `inmemory` | Ontology graph backend. Options: `inmemory`, `neo4j`. |
| `AI_GOVERNANCE_ONTOLOGY_SQLITE_PATH` | - | SQLite path (not yet implemented). |
| `AI_GOVERNANCE_ONTOLOGY_POSTGRES_DSN` | - | PostgreSQL DSN (not yet implemented). |

### Backend Support Matrix

| Repository | inmemory | sqlite | postgres |
| --- | --- | --- | --- |
| Policy Administration | Yes | Yes | Yes |
| Evaluation | Yes | Yes | Yes |
| Experiment | Yes | Yes | Yes |
| Experiment Candidate | Yes | Yes | Yes |
| Evaluation Run | Yes | Yes | Yes |
| Leaderboard | Yes | Yes | Yes |
| Prompt | Yes | Yes | Yes |
| Model | Yes | Yes | Yes |
| Dataset | Yes | Yes | Yes |
| Job | Yes | Yes | Yes |
| Governance Decision | Yes | Yes | Yes |
| Ontology Sync Event | Yes | Yes | Yes |
| Ontology Graph | Yes | Not implemented | Not implemented |

### Usage Examples

```bash
# Use SQLite for evaluation and job repositories
AI_GOVERNANCE_EVALUATION_REPOSITORY=sqlite
AI_GOVERNANCE_EVALUATION_SQLITE_PATH=.ai-governance/evaluations.db
AI_GOVERNANCE_JOB_REPOSITORY=sqlite
AI_GOVERNANCE_JOB_SQLITE_PATH=.ai-governance/jobs.db

# Keep everything else in-memory (default)
```

### Design Principles

- **No silent fallback** — unsupported or misconfigured backends raise
  ``ValueError`` with a clear message.
- **Factory-based construction** — repository backends are selected by factory
  classes in ``src/ai_governance/repositories/factories/``.
- **Dependency providers delegate to factories** — REST dependency functions
  call ``load_settings()`` and pass it to the appropriate factory.
- **Runtime collaborators are explicit** — repositories like
  ``GovernanceDecisionRepository`` receive collaborators (e.g. ontology event
  publisher) through factory ``create()`` arguments, not through hidden
  FastAPI dependency lookups.

### Adding a New Repository Backend

1. Define the repository contract (``ABC`` or ``Protocol``).
2. Implement one or more concrete repositories.
3. Create a factory class in ``src/ai_governance/repositories/factories/``.
4. Add configuration fields to ``Settings`` in ``src/ai_governance/settings.py``.
5. Update the REST dependency provider to use the factory.
6. Add unit tests for the factory.
7. Update this configuration reference. |
