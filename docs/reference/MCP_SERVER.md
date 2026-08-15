# MCP Server

> This page is the detailed server reference. For a first connection and a
> copy-paste test, start with [MCP Usage](./MCP_USAGE.md). The recommended
> remote endpoint is `http://localhost:8002/mcp`; port `8001` is MCPO, not the
> native MCP server.

## In plain language

The MCP server lets an AI client use AI Governance Control Plane capabilities
as tools. It does not create a second governance system: each tool forwards
the request to the existing REST control plane, which remains responsible for
identity, tenant scope, permissions, persistence, and audit.

The preferred HTTP protocol is MCP `2026-07-28`. It is stateless at the
transport layer, so every request can be processed by any server replica.
Older MCP clients continue to work through the same tool path while they
migrate.

## Multi-organization context

Control-plane tools accept a required `context` object containing
`organization_id` and, for project operations, `project_id`. Actor identity is
resolved by the server and is not accepted as an impersonation argument.
Discovery and administration tools include `organization.*`, `project.*`,
`membership.*`, `role_assignment.*`, `authorization.permissions`, and
`context.current`. Tenant context participates in write request hashing and MCP
audit ownership.

## Overview

AI Governance Control Plane exposes a Model Context Protocol server as a stateless transport
adapter over the existing REST control plane.

The MCP server does not own governance rules, persistence, provider behavior,
or orchestration semantics. Each tool validates input, calls exactly one REST
endpoint, maps the REST response, and translates REST errors into tool errors.

## Authentication and token lifecycle

In Keycloak mode, the preferred configuration is the confidential
`ai-governance-mcp` client using OAuth2 client credentials:

```text
AI_GOVERNANCE_MCP_CLIENT_ID=ai-governance-mcp
AI_GOVERNANCE_MCP_CLIENT_SECRET=<secret>
AI_GOVERNANCE_MCP_TOKEN_URL=http://keycloak.localhost:8080/realms/ai-governance/protocol/openid-connect/token
```

The MCP REST client obtains and caches a token, refreshing it before expiry.
`AI_GOVERNANCE_API_TOKEN` is an explicit bearer-token override for testing. The
Keycloak admin token is used only during startup discovery and is never used
for normal MCP REST calls.

The token `sub` is the runtime actor. Backend startup provisions that subject
in `organization_memberships` and `role_assignments`; a Keycloak client or
role alone does not grant AI Governance Control Plane tenant access.

For native Streamable HTTP, this service-account model does not apply. The
incoming `Authorization: Bearer` credential is validated at the HTTP boundary
and forwarded unchanged to the REST control plane for that tool invocation.
The request-local credential is never stored in an environment variable or a
global client token, so concurrent callers cannot exchange identities.

For a macOS local smoke test, use
`uv run python scripts/mcp/fetch-access-token.py`. It exchanges
the dedicated local MCP client credentials for a short-lived token carrying
the native MCP resource audience, then copies that token to the clipboard
without printing it. This helper is for local testing only;
remote clients should use their own user or workload identity as described in
[MCP Usage](./MCP_USAGE.md#authentication-tokens--identity).

## Configuration

The MCP server reads these environment variables:

```text
AI_GOVERNANCE_API_URL
AI_GOVERNANCE_API_TIMEOUT
AI_GOVERNANCE_API_RETRIES
LOG_LEVEL
AI_GOVERNANCE_MCP_AUDIT_DATABASE_PATH
AI_GOVERNANCE_MCP_CLIENT_ID
AI_GOVERNANCE_MCP_CLIENT_SECRET
AI_GOVERNANCE_MCP_TOKEN_URL
AI_GOVERNANCE_API_TOKEN
```

Native Streamable HTTP additionally uses `AI_GOVERNANCE_MCP_TRANSPORT`,
`AI_GOVERNANCE_MCP_HTTP_HOST`, `AI_GOVERNANCE_MCP_HTTP_PORT`, `AI_GOVERNANCE_MCP_HTTP_PATH`,
`AI_GOVERNANCE_MCP_PUBLIC_URL`,
`AI_GOVERNANCE_MCP_HTTP_ALLOWED_HOSTS`, `AI_GOVERNANCE_MCP_HTTP_ALLOWED_ORIGINS`,
`AI_GOVERNANCE_MCP_HTTP_STATELESS`, and `AI_GOVERNANCE_MCP_HTTP_JSON_RESPONSE`.

## Native Streamable HTTP

The native endpoint supports both MCP protocol eras through one transport
boundary. MCP `2026-07-28` is the preferred stateless path; see [the official
specification announcement](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
for the protocol-level changes.

| Protocol era | Lifecycle at `/mcp` | Deployment consequence |
| --- | --- | --- |
| `2026-07-28` | Every request carries its protocol version, client metadata, and capabilities in `_meta`, with `Mcp-Method` and (where applicable) `Mcp-Name` headers. There is no `initialize` or `Mcp-Session-Id`. | Any request can land on any replica; ordinary round-robin load balancing needs no session affinity or shared MCP session store. |
| Legacy handshake revisions | The SDK retains the `initialize` lifecycle and session behavior for compatible clients. | Retained only as a migration path; monitor per-era request telemetry before retirement. |

The boundary normalizes both protocol forms before a tool is invoked:

```text
legacy handshake request ──┐
                            ├── SDK negotiation ──► request-local identity
2026 self-contained request ┘                         │
                                                      ▼
                                  canonical tool registry → audit → REST control plane
```

Earlier handshake/session clients remain supported for compatibility during
the migration window. Both eras invoke the same canonical MCP tool registry,
authorization forwarding, audit path, idempotency behavior and REST-backed
application services. The server records anonymous per-era request counts in
its in-process MCP metrics to guide eventual legacy retirement.

Stateless MCP does not make governance data ephemeral. Replay executions,
jobs, decisions, evaluations, and audit records remain durable resources. A
workflow that needs state passes its explicit resource identifier (for example
an execution or job ID) in a later tool call; it must not rely on hidden MCP
session state.

Start the remote MCP service separately from stdio and MCPO:

```bash
uv run ai-governance-mcp --transport streamable-http --host 0.0.0.0 --port 8002
```

It exposes `POST`, `GET`, and `DELETE` at `/mcp` through the official MCP
Python SDK. The default configuration is stateless and prefers JSON responses.
`GET /health` confirms process liveness and `GET /ready` confirms that the MCP
application initialized. Terminate TLS at the ingress or gateway; configure
allowed hosts and origins there rather than trusting arbitrary forwarding
headers.

In Keycloak mode, an unauthenticated request receives an RFC 9728 challenge
pointing to `/.well-known/oauth-protected-resource/mcp`. That metadata
advertises the Keycloak issuer and the canonical resource
`AI_GOVERNANCE_MCP_PUBLIC_URL/mcp`. The server accepts a token only when its verified
`aud` claim includes that exact resource. The local realm maps
`http://localhost:8002/mcp` into tokens issued to the confidential
`ai-governance-mcp` service client for smoke tests and the public PKCE
`ai-governance-mcp-vscode` client for user sign-in. Change the mappers together
with `AI_GOVERNANCE_MCP_PUBLIC_URL` when using another public origin.

Defaults:

```text
AI_GOVERNANCE_API_URL=http://127.0.0.1:8000
AI_GOVERNANCE_API_TIMEOUT=10
AI_GOVERNANCE_API_RETRIES=0
LOG_LEVEL=INFO
AI_GOVERNANCE_MCP_AUDIT_DATABASE_PATH=.ai-governance/mcp_execution_audit.db
```

See [Configuration](./CONFIGURATION.md) for the full project environment
reference, including REST API, Studio, graph, and test backend variables.

## Tool Groups

### Provider Tools

| Tool | REST Endpoint |
| ---- | ------------- |
| `provider.list` | `GET /api/v1/providers` |

### Registry Tools

| Tool | REST Endpoint |
| ---- | ------------- |
| `registry.list_prompts` | `GET /api/v1/prompts` |
| `registry.get_prompt` | `GET /api/v1/prompts/{prompt_name}` |
| `registry.list_models` | `GET /api/v1/models` |
| `registry.get_model` | `GET /api/v1/models/{model_id}` |
| `registry.list_datasets` | `GET /api/v1/datasets` |
| `registry.get_dataset` | `GET /api/v1/datasets/{dataset_id}` |

### Evaluation Tools

| Tool | REST Endpoint |
| ---- | ------------- |
| `evaluation.history` | `GET /api/v1/evaluations/history/{execution_id}` |
| `evaluation.latest` | `GET /api/v1/evaluations/latest/{execution_id}` |
| `evaluation.metrics` | `GET /api/v1/evaluations/{evaluation_id}` |
| `evaluation.get` | `GET /api/v1/evaluations/{evaluation_id}` |
| `evaluation.submit_async` | `POST /api/v1/evaluations/jobs` |

### Experiment Tools

| Tool | REST Endpoint |
| ---- | ------------- |
| `experiment.list` | `GET /api/v1/experiments` |
| `experiment.get` | `GET /api/v1/experiments/{experiment_id}` |
| `experiment.candidates` | `GET /api/v1/experiments/{experiment_id}/candidates` |
| `experiment.runs` | `GET /api/v1/experiments/{experiment_id}/runs` |
| `experiment.compare_candidates` | `GET /api/v1/experiments/{experiment_id}/comparison` |
| `experiment.leaderboard` | `GET /api/v1/experiments/{experiment_id}/leaderboard` |
| `experiment.create` | `POST /api/v1/jobs` |
| `experiment.add_candidate` | `POST /api/v1/jobs` |
| `experiment.run_async` | `POST /api/v1/experiments/{experiment_id}/run` |

### Governance Tools

| Tool | REST Endpoint |
| ---- | ------------- |
| `governance.compare` | `POST /api/v1/governance/compare` |
| `governance.drift` | `POST /api/v1/governance/drift` |
| `governance.report` | `GET /api/v1/governance/reports/{evaluation_id}` |
| `governance.summarize_experiment` | `GET /api/v1/experiments/{experiment_id}/insights` |
| `governance.explain_candidate` | `GET /api/v1/experiments/{experiment_id}/candidates/{candidate_id}/insights` |
| `governance.compare_candidates` | `GET /api/v1/experiments/{experiment_id}/comparative-insights` |
| `governance.investigate_execution` | `GET /api/v1/investigations/by-correlation/{correlation_id}` |
| `governance.investigate_job` | `GET /api/v1/investigations/by-job/{job_id}` |
| `governance.investigate_evaluation` | `GET /api/v1/investigations/by-evaluation/{evaluation_id}` |
| `governance.investigate_audit` | `GET /api/v1/investigations/by-audit/{audit_id}` |
| `governance.explain_drift` | `GET /api/v1/governance/drift/{drift_id}/explanation` |
| `governance.summarize_drift` | `GET /api/v1/evaluations/{evaluation_id}/drift-explanation` |
| `governance.generate_experiment_report` | `GET /api/v1/reports/experiments/{experiment_id}` |
| `governance.generate_evaluation_report` | `GET /api/v1/reports/evaluations/{evaluation_id}` |
| `governance.generate_drift_report` | `GET /api/v1/reports/drift/{drift_id}` |
| `governance.generate_investigation_report` | `GET /api/v1/reports/investigations/{correlation_id}` |

The compare and drift endpoints are POST because the REST API accepts request
bodies for the evaluation pair. They are read-only analysis operations and do
not mutate governance state.

Governance insight tools are read-only. They summarize existing
experiment, audit, job, evaluation, and drift evidence. They do not promote,
deploy, approve releases, or mutate governance state.

### Governance Decision Tools

| Tool | REST Endpoint |
| ---- | ------------- |
| `governance_decision.evaluate` | `POST /api/v1/decisions/evaluate` |
| `governance_decision.get` | `GET /api/v1/decisions/{decision_id}` |
| `governance_decision.list` | `GET /api/v1/decisions` |
| `governance_decision.evidence` | `GET /api/v1/decisions/{decision_id}/evidence` |
| `governance_decision.explain` | `GET /api/v1/decisions/{decision_id}/explanation` |
| `governance_decision.lineage` | `GET /api/v1/decisions/{decision_id}/lineage` |

Decision tools call the same application service path as REST. The evaluate
tool persists a deterministic decision and explanation, records decision audit,
and returns structured decision, explanation, evidence summary, and policy
outcome data. The MCP layer does not duplicate reasoning, policy evaluation,
evidence building, or graph lineage logic.

### Job Tools

| Tool | REST Endpoint |
| ---- | ------------- |
| `job.list` | `GET /api/v1/jobs` |
| `job.status` | `GET /api/v1/jobs/{job_id}` |
| `job.cancel` | `POST /api/v1/jobs/{job_id}/cancel` |
| `job.retry` | `POST /api/v1/jobs/{job_id}/retry` |

### Ontology Graph Tools

| Tool | REST Endpoint |
| ---- | ------------- |
| `ontology_graph.get_entity` | `GET /api/v1/ontology/entities/{entity_type}/{entity_id}` |
| `ontology_graph.get_relationship` | `GET /api/v1/ontology/relationships/{relationship_id}` |
| `ontology_graph.get_relationships` | `GET /api/v1/ontology/entities/{entity_type}/{entity_id}/relationships` |
| `ontology_graph.neighbourhood` | `GET /api/v1/ontology/entities/{entity_type}/{entity_id}/neighbourhood` |
| `ontology_graph.upstream` | `GET /api/v1/ontology/entities/{entity_type}/{entity_id}/upstream` |
| `ontology_graph.downstream` | `GET /api/v1/ontology/entities/{entity_type}/{entity_id}/downstream` |
| `ontology_graph.find_paths` | `GET /api/v1/ontology/path` |

Ontology graph tools are read-only and call the REST graph query APIs. They do
not call Neo4j directly.

### MCP Audit Tools

| Tool | REST Endpoint |
| ---- | ------------- |
| `mcp_audit.list` | `GET /api/v1/mcp/audit` |
| `mcp_audit.get` | `GET /api/v1/mcp/audit/{audit_id}` |
| `mcp_audit.find_by_request` | `GET /api/v1/mcp/audit/by-request/{request_id}` |
| `mcp_audit.find_by_correlation` | `GET /api/v1/mcp/audit/by-correlation/{correlation_id}` |

## Write Envelope

Controlled write tools share this required envelope:

```json
{
  "request_id": "...",
  "idempotency_key": "...",
  "requested_by": "...",
  "actor_type": "HUMAN | AGENT | SERVICE",
  "reason": "...",
  "dry_run": false,
  "metadata": {}
}
```

Optional correlation fields include:

- `correlation_id`
- `agent_name`
- `agent_session_id`
- `client_name`
- `client_version`

The MCP layer validates the envelope. The REST job control plane owns
idempotency semantics and returns an existing job when the same idempotency key
is submitted with the same canonical input.

## Dry Run

When `dry_run` is true, MCP validates the envelope and tool-specific schema,
records the MCP audit entry, and returns a validation result without calling
REST or creating a job.

Business validation remains in REST/application services for non-dry-run
requests.

## MCP Execution Audit

Controlled write tools record MCP execution audit entries before calling REST
and update the same durable audit row after completion. Audit records include
request/correlation IDs, actor metadata, tool name, operation/resource details,
canonical request hash, safe request summary, dry-run status, job ID, result
reference, error details, and duration.

By default, MCP stores audit rows in the SQLite database at
`.ai-governance/mcp_execution_audit.db`. Set `AI_GOVERNANCE_MCP_AUDIT_DATABASE_PATH` to use a
different SQLite database path.

Full request payloads are not blindly stored. Sensitive fields such as
`provider_config`, API keys, tokens, passwords, and secrets are redacted from
the audit summary.

Audit read responses expose a derived `interrupted` flag for stale `STARTED`
rows. The read model does not silently mutate the audit row. A row is treated
as interrupted when it is still `STARTED`, has no completion timestamp, and is
older than the requested `interrupted_after_seconds` threshold.

## Settings Tools

- `settings.list` and `settings.get` expose effective typed configuration.
- `settings.categories` lists the registry navigation model.
- `settings.validate` validates a proposed value without persistence.
- `settings.update` writes a mutable runtime value.

`settings.update` also requires a scope and expected version. The write tools
require the controlled-write envelope. Dry-run updates call
REST validation, create an MCP audit record, and do not persist the value.
Environment overrides and static deployment settings remain read-only.

For every controlled MCP write, an explicit `dry_run` wins. When it is omitted,
the server resolves the inherited `mcp.dry_run_default` value for the request's
project/organization context through the Settings REST API.

## Runtime Boundary

```text
AI Assistant
      |
      v
MCP Tool
      |
      v
REST Client
      |
      v
AI Governance Control Plane REST Control Plane
      |
      v
Application Services
```

MCP handlers must not import repositories, provider SDKs, domain construction
logic, or worker operations. Controlled writes return job references whenever
they submit execution work.

## Error Handling

REST error envelopes are translated into MCP tool errors. The tool error
payload includes the mapped code, message, optional details, and status code
for diagnostics.

## Observability

The in-process metrics snapshot includes:

- `tool_invocations_total`
- `tool_latency_ms`
- `tool_failures_total`
- `active_requests`
- `rest_calls`
- `rest_failures`

Structured logs are emitted per tool call with tool name, request ID, status,
duration, and error code. Sensitive request payloads are not logged.

## Usage
[MCP Usage](../reference/MCP_USAGE.md)

```

## Related Documents

- [REST API](./REST_API.md)
- [Public API](./PUBLIC_API.md)
- [Extensibility](../architecture/EXTENSIBILITY.md)
- [MCP Usage](../reference/MCP_USAGE.md)
