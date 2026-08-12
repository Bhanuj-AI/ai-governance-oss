# REST API

## Authentication and tenant context

### Authentication mode

AI Governance Control Plane supports two authentication modes controlled by `AI_GOVERNANCE_AUTH_MODE`:

- **Development mode** (`development`) — actor identity comes from the
  `X-AI-Governance-Actor-Id` header or `AI_GOVERNANCE_DEVELOPMENT_ACTOR_ID` environment
  variable. No token validation occurs.
- **Keycloak mode** (`keycloak`) — requires `Authorization: Bearer <token>`
  on every request. The platform validates the JWT against Keycloak and rejects
  missing, expired, or invalid tokens with HTTP 401.

See [Configuration](./CONFIGURATION.md#authentication) for full details.

### Tenant context

Tenant-scoped requests send `X-AI-Governance-Organization-Id`,
`X-AI-Governance-Project-Id`, `X-Request-Id`, and optionally `X-Correlation-Id`.
`X-AI-Governance-Actor-Id` is accepted only with the development identity provider.
In keycloak mode, the actor identity is derived from the JWT `sub` claim and
the header is ignored. Organization administration is available under
`/api/v1/organizations`; the resolved scope, roles, and permissions are
returned by `/api/v1/context`.

The native MCP Streamable HTTP service forwards the caller's Authorization,
tenant, request, and correlation headers to this control plane. REST remains
the owner of authentication-derived actor identity, membership, and RBAC; MCP
does not accept an actor identity in tool input.

## Overview

AI Governance Control Plane exposes a versioned FastAPI REST control plane for operational
integrations. The REST layer is transport-only: routers use request/response
DTOs, mapper classes, and API service facades while business behavior remains
inside services and registries.

Base path:

```text
/api/v1
```

Documentation endpoints:

```text
/openapi.json
/docs
/redoc
```

## Configuration

Runtime settings such as API host, port, CORS origins, environment label, and
startup demo seeding are controlled by environment variables. See
[Configuration](./CONFIGURATION.md) for the complete startup reference.

Local browser clients are allowed from `http://localhost:3000` and
`http://127.0.0.1:3000` by default. Override allowed browser origins with:

```text
AI_GOVERNANCE_CORS_ALLOW_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

## Health and Metadata

```http
GET /health
GET /ready
GET /api/v1
```

These endpoints expose service health, readiness, and API metadata.

## Registry APIs

```http
GET /api/v1/providers
GET /api/v1/providers/{provider_name}

GET /api/v1/provider-installations
POST /api/v1/provider-installations
POST /api/v1/provider-installations/validate
PATCH /api/v1/provider-installations/{installation_id}

GET /api/v1/runtime-connections
GET /api/v1/runtime-connections/providers
POST /api/v1/runtime-connections/validate
POST /api/v1/runtime-connections
PATCH /api/v1/runtime-connections/{runtime_connection_id}
POST /api/v1/runtime-connections/{runtime_connection_id}/test
GET /api/v1/runtime-connections/{runtime_connection_id}/models

GET /api/v1/prompts
GET /api/v1/prompts/{prompt_name}
GET /api/v1/prompts/versions/{prompt_id}

GET /api/v1/models
GET /api/v1/models/{model_id}
GET /api/v1/models/runtime-providers
POST /api/v1/models
POST /api/v1/models/{model_id}/versions
POST /api/v1/models/{model_id}/activate
POST /api/v1/models/{model_id}/deprecate
POST /api/v1/models/{model_id}/archive

GET /api/v1/datasets
GET /api/v1/datasets/{dataset_id}
POST /api/v1/datasets/upload
POST /api/v1/prompts/observations
POST /api/v1/models/observations
```

Registry APIs expose governed provider, prompt, model, and dataset metadata as
stable REST DTOs. Prompt templates are intentionally not returned from list
responses. `GET /api/v1/prompts/{prompt_name}` returns the metadata for every
registered version of the named prompt. `GET /api/v1/prompts/versions/{prompt_id}`
returns one explicit prompt version, including its template, for operator
inspection.

Provider types are immutable adapters shipped with the deployment. Each adapter
contributes a versioned, secret-free configuration schema resource; discovery
returns that schema, supported metrics, adapter version, and documentation URL.
Studio renders the configuration form from this document and keeps Advanced JSON
for uncommon adapter options.

Provider installations are organization-scoped by default and can be created
for the current project when a local variation is required. They contain
non-sensitive settings plus secret references such as `env://OPENAI_API_KEY`;
secret values are resolved only by the runtime. `POST .../validate` resolves
the references and initializes the adapter without persisting an installation.
An enabled installation is validated server-side on creation and update. Submit
an evaluation, evaluation job, experiment candidate, or replay evaluation with
`provider_installation_id` to resolve that configuration at execution time.

Runtime connections are separate tenant-owned resources for model-runtime
invocation. They contain a provider, non-sensitive endpoint configuration, an
organization or project scope, and secret references only. They are not model
version fields: a key rotation or endpoint change updates the connection rather
than creating a new governed model version. In OSS, OpenAI, Anthropic, and
OpenAI-compatible custom connections are supported; `POST .../test` validates
configuration and resolves secret references without returning their values.
`OPENAI_API_KEY` under deployment integrations remains a platform credential
and is not a tenant runtime connection.

An experiment candidate may reference a compatible connection using its
`runtime_connection_id`. Candidate creation verifies tenant visibility,
enabled state, and model-provider compatibility; execution resolves the
current secret reference only in memory. The resolved value is never included
in the candidate, evaluation run, API response, or job payload.

See [Configure Runtime Connections](../tutorials/configure-runtime-connections.md)
for the complete Studio workflow, request examples, secret-reference rules,
and the current OSS boundary for model invocation.

`POST /api/v1/prompts/observations` and `POST /api/v1/models/observations`
are the vendor-neutral OSS ingestion boundary for runtime or evaluation
evidence. They create immutable **OBSERVED** catalog records rather than
authoring runtime configuration. Producers supply `source_system` and an
optional `source_reference`; prompt producers may withhold content, but must
supply a SHA-256 `content_hash` in that case. Repeating the same observed
identity and evidence is idempotent. A conflicting payload for the same
logical name/version returns `409` rather than overwriting history.
The [producer integration guide](../tutorials/producer-integration.md) includes
copy-paste curl, Python, and Node.js examples.

Managed models are explicitly registered as immutable **DRAFT** versions. At
registration, the control plane resolves and stores a provider-neutral runtime
capability snapshot for that exact model version. Studio and candidate creation
use the snapshot to expose only supported controls; execution adapters translate
generic controls such as `max_output_tokens` to the provider request contract.
`POST /api/v1/models/runtime-capabilities/resolve` previews the snapshot before
registration. Existing model records without a snapshot remain explicitly
`UNVERIFIED` for compatibility and are never silently rewritten. A
managed model keeps its governed `model_name` separate from its immutable
`provider_model_id`, which is the exact identifier sent at execution time.
For supported providers, Studio discovers that identifier from the selected
tenant runtime connection through `GET /api/v1/runtime-connections/{id}/models`;
credential values are never returned. A
governance administrator can activate a managed version, which automatically
deprecates another active version of the same provider/model identity, or
deprecate and archive it explicitly. Archived versions cannot be reactivated.
Observed runtime evidence never accepts these managed lifecycle transitions.

Example observed prompt with protected content:

```json
{
  "name": "support-assistant",
  "version": "v7",
  "source_system": "my-evaluation-service",
  "source_reference": "evaluation-run-123",
  "content_hash": "sha256:…",
  "variables": ["question", "context"]
}
```

The assets UI is a registry browser over these APIs. It does not introduce a
second asset model or calculate lineage in the browser; references and lineage
are read from the ontology query APIs for the selected version.

`POST /api/v1/datasets/upload` accepts multipart form fields `name`, `version`,
`description`, optional `schema_version` (default `1.0`), and `file`. The file
must be UTF-8 `.csv`, `.jsonl`, or `.ndjson`. AI Governance Control Plane validates its structure,
counts records, computes a SHA-256 checksum, stores immutable bytes in the
configured S3-compatible object store, and registers a DRAFT dataset version.
The response is the normal `DatasetResponse`; dataset file content is never
returned by the registry API. An existing name/version returns `409`; the same
checksum under a different version of the same logical dataset also returns
`409`. Object keys are tenant-scoped and content-addressed, and a registry
failure after a successful write triggers compensating object deletion.

## Evaluation APIs

```http
POST /api/v1/evaluations
POST /api/v1/evaluations/jobs
GET /api/v1/evaluations/{evaluation_id}
GET /api/v1/evaluations/history/{execution_id}
GET /api/v1/evaluations/latest/{execution_id}
```

Evaluation APIs submit synchronous provider-backed evaluations, queue
asynchronous evaluation jobs, persist results, and retrieve historical
evaluation evidence. Requests may include
`metric_specs` and provider-specific `provider_config`; provider configuration
is request-only and is never returned in responses.

When `metric_specs` is provided, AI Governance Control Plane validates requested metrics against the
provider descriptor/capabilities before invoking the provider.

## Experiment APIs

```http
POST /api/v1/experiments
GET /api/v1/experiments
GET /api/v1/experiments/{experiment_id}
POST /api/v1/experiments/{experiment_id}/candidates
GET /api/v1/experiments/{experiment_id}/run-plan
GET /api/v1/experiments/{experiment_id}/runs/{run_id}/evaluations?page=1&page_size=25
POST /api/v1/experiments/{experiment_id}/run
POST /api/v1/experiments/{experiment_id}/cancel
GET /api/v1/experiments/{experiment_id}/leaderboard
GET /api/v1/experiments/{experiment_id}/comparison
```

Experiment APIs create and list experiments, register candidates that reference
governed prompt/model/dataset versions, execute candidate models against each
immutable dataset item through their tenant-scoped runtime connection, persist
the resulting workflow execution evidence, evaluate that evidence, compare
candidates, and return leaderboards. Evaluators never recreate candidate
configuration or invoke the candidate model. A run fails with
`EXECUTION_FAILED` when model execution cannot produce evidence.

`GET /api/v1/experiments/{experiment_id}/runs/{run_id}/evaluations` returns
tenant-scoped, item-level evaluator evidence for one run. It is paginated with
`page` and `page_size` (default `25`, maximum `100`) and retains results that
were successfully persisted before a later failure or cancellation. The
response exposes evaluator identity, completion time, metric scores, and the
captured model API latency when available; it
does not expose protected prompt content, dataset content, model outputs, or
provider explanations.

Before starting a run, clients can call `GET /api/v1/experiments/{experiment_id}/run-plan`.
It returns the immutable dataset's declared item count, the candidate count,
and the resulting model-invocation and evaluation-item counts. While a run is
active, the same response contains the persisted active candidate, its position,
and completed model/evaluation item counts. This is a workload estimate, not a
price quote: evaluator implementations may make a provider-specific number of
additional external calls. `POST /api/v1/experiments/{experiment_id}/cancel`
retains evidence already captured and stops future candidate/evaluator calls at
the next safe item boundary.

Candidate comparison requires two different candidates from the same
experiment:

```http
GET /api/v1/experiments/{experiment_id}/comparison
  ?baseline_candidate_id={candidate_id}
  &comparison_candidate_id={candidate_id}
```

The response contains the complete backend candidate configuration for both
selections and metric comparisons based on each candidate's latest completed
evaluation run. Metric rows include `metric_name`, `baseline_value`,
`candidate_value`, and `score_difference`. Only metrics present in at least one
of the two evaluation results are returned; missing values remain `null` and
are not synthesized in the Studio frontend.

The endpoint returns a validation error when both selectors identify the same
candidate, the candidates do not use the same immutable dataset version, or
when either candidate has no completed evaluation run. A
candidate ID that is missing or belongs to another experiment returns the
standard candidate-not-found response.

Direct experiment execution remains synchronous unless the run request includes
an async idempotency envelope. Async experiment execution returns a queued job
reference. Streaming, deployment approval, and policy engines remain outside
this REST phase.

Experiment insight endpoints explain completed experiment evidence:

```http
GET /api/v1/experiments/{experiment_id}/insights
GET /api/v1/experiments/{experiment_id}/candidates/{candidate_id}/insights
GET /api/v1/experiments/{experiment_id}/comparative-insights
```

## Job APIs

```http
POST /api/v1/jobs
GET /api/v1/jobs
GET /api/v1/jobs/{job_id}
POST /api/v1/jobs/{job_id}/cancel
POST /api/v1/jobs/{job_id}/retry
GET /api/v1/jobs/{job_id}/result
```

Job APIs expose the public control plane for asynchronous governance work.
Clients can submit jobs, query status and metadata, list jobs with optional
`status`, `job_type`, and `limit` filters, cancel queued or running jobs, retry
failed jobs, and fetch result references.

Public job APIs do not expose worker leasing, heartbeat, or direct
success/failure mutation endpoints. Those transitions remain internal worker
and repository operations.

## Ontology Synchronization APIs

```http
GET /api/v1/ontology/synchronization/events
GET /api/v1/ontology/synchronization/events/metrics
GET /api/v1/ontology/synchronization/events/{event_id}
GET /api/v1/ontology/synchronization/events/{event_id}/status
POST /api/v1/ontology/synchronization/events/{event_id}/retry
POST /api/v1/ontology/synchronization/events/{event_id}/cancel
```

Ontology synchronization APIs expose the durable event lifecycle used by the
event-driven ontology worker. Operators can list events, inspect status,
requeue failed or dead-letter events, cancel pending events, and read aggregate
event metrics. List queries support `status`, `entity_type`, `entity_id`,
`correlation_id`, `event_type`, and `limit` filters.

## Ontology Graph Query APIs

```http
GET /api/v1/ontology/entities/{entity_type}/{entity_id}
GET /api/v1/ontology/relationships/{relationship_id}
GET /api/v1/ontology/entities/{entity_type}/{entity_id}/relationships
GET /api/v1/ontology/entities/{entity_type}/{entity_id}/neighbourhood
GET /api/v1/ontology/entities/{entity_type}/{entity_id}/upstream
GET /api/v1/ontology/entities/{entity_type}/{entity_id}/downstream
GET /api/v1/ontology/path
POST /api/v1/ontology/demo/seed
```

Ontology graph query APIs expose read-only semantic graph access for entity
lookup, relationship lookup, neighbourhood traversal, upstream lineage,
downstream impact, and bounded path discovery. Query parameters include
`direction`, `relationship_type`, `entity_type`, `depth`, `limit`, `cursor`,
`source_type`, `source_id`, `target_type`, `target_id`, and `max_depth`.
Traversal depth is capped at `5`; result limits are capped at `500`.
Local/dev API startup can populate the in-memory graph repository with the same
small valid graph for Studio visualization, seed the `policy-release-gate`
Policy Engine record, and create approved, proposed-for-review, rejected, and
blocked demo governance decisions. It also seeds ten representative governance
jobs for the Studio Jobs page. The demo seed endpoint can also reseed that data
manually for `/graph`, `/policies`, `/decisions`, and `/jobs`.

## MCP Audit APIs

```http
GET /api/v1/audit
GET /api/v1/audit/{audit_id}
GET /api/v1/replays/{replay_id}/audit
```

Studio audit APIs expose a page-ready read model over MCP execution audit
records. The list endpoint returns summary metrics, available filter values,
paginated records, linked job status when present, and derived interruption
state for stale `STARTED` rows. The detail endpoint returns one audit record
with request metadata, redacted request summary, resolved versions, linked job
context, and related records sharing the same correlation ID.

Replay detail uses `GET /api/v1/replays/{replay_id}/audit` for its own
replay-scoped timeline. It is derived from durable Replay state and its
execution and evaluation jobs, so REST- and worker-driven replay activity is
not confused with the MCP controlled-write feed. The timeline contains the
frozen-source, job submission and outcome, baseline, comparison, drift, and
terminal-result transitions for that replay only.

Low-level MCP audit APIs remain available for direct request/correlation
lookups:

```http
GET /api/v1/mcp/audit
GET /api/v1/mcp/audit/{audit_id}
GET /api/v1/mcp/audit/by-request/{request_id}
GET /api/v1/mcp/audit/by-correlation/{correlation_id}
```

MCP audit APIs expose durable controlled-write audit records. List queries
support `request_id`, `correlation_id`, `tool_name`, `status`, `actor_id`,
`limit`, and `interrupted_after_seconds` filters.

Audit responses include a derived `interrupted` flag for stale `STARTED` rows.
The read API does not silently mutate audit state; interrupted detection is a
read-model signal unless a future recovery task explicitly updates rows.

## Governance APIs

```http
POST /api/v1/governance/compare
POST /api/v1/governance/drift
GET /api/v1/governance/drift/{drift_id}/explanation
GET /api/v1/governance/reports/{evaluation_id}
```

Governance APIs compare persisted evaluations, analyze metric drift, and
explain drift evidence. Legacy report lookup returns
`501 GOVERNANCE_REPORT_NOT_IMPLEMENTED`; evidence reports are available under
`/api/v1/reports`.

Evaluation drift explanations compare an evaluation with prior evidence from
the same execution when available:

```http
GET /api/v1/evaluations/{evaluation_id}/drift-explanation
```

## Decision APIs

```http
POST /api/v1/decisions/evaluate
GET /api/v1/decisions
GET /api/v1/decisions/{decision_id}
GET /api/v1/decisions/{decision_id}/detail
GET /api/v1/decisions/{decision_id}/evidence
GET /api/v1/decisions/{decision_id}/explanation
GET /api/v1/decisions/{decision_id}/lineage
```

Decision APIs expose the shared `GovernanceDecisionApplicationService`.
Evaluation invokes the deterministic reasoning engine, persists the resulting
decision and explanation, records audit, and returns the decision, explanation,
evidence summary, and policy outcomes. Repeated evaluation requests with the
same `request_id` and identical payload return the existing decision where
possible; conflicting reuse returns `DecisionConflict`.

List queries support `target_type`, `target_id`, `status`, `correlation_id`,
and `limit`. Detail responses are optimized for visual inspection and include
the persisted decision, stored evidence summary, stored policy outcomes, and
decision audit records. Evidence responses include persisted evidence
references and a rebuilt decision evidence graph. Lineage uses the ontology
graph query service and does not call graph storage directly.

## Policy Administration APIs

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

Policy administration APIs support Studio policy authoring without exposing
evaluator internals. Policies are project-scoped definitions with versioned
executable snapshots. Creating a policy creates version `1` in `DRAFT` status.
Draft versions can be replaced, activation makes one draft `ACTIVE` and
deprecates the prior active version, and archived versions are terminal.
`GET /api/v1/policies` returns latest-created policies first and supports
submitted inventory queries with `search`, `project_id`, `owner`, `category`,
`status`, `target_type`, `effect`, `limit`, and `offset`.

`GET /api/v1/policy-schema` returns backend-owned target types, fields,
operators, effects, statuses, categories, and severities for editor dropdowns.
Simulation evaluates a selected policy version through
`GovernancePolicyEvaluator.evaluate_with_trace()` and returns matched
conditions, unmatched conditions, and condition-level trace items.

## Investigation APIs

```http
GET /api/v1/investigations/by-correlation/{correlation_id}
GET /api/v1/investigations/by-job/{job_id}
GET /api/v1/investigations/by-evaluation/{evaluation_id}
GET /api/v1/investigations/by-audit/{audit_id}
```

Investigation APIs correlate MCP audit rows, job execution state, and
persisted evaluation results. They are read-only and return evidence-first
responses.

## Report APIs

```http
GET /api/v1/reports/experiments/{experiment_id}
GET /api/v1/reports/evaluations/{evaluation_id}
GET /api/v1/reports/drift/{drift_id}
GET /api/v1/reports/investigations/{correlation_id}
GET /api/v1/reports/mcp-audit/{audit_id}
```

Report APIs generate governance evidence reports as `json` or `markdown`
using the `format` query parameter. They do not persist reports or create
approval/deployment state.

## Error Envelope

REST errors use a common envelope:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable message.",
    "details": {}
  }
}
```

Important REST error codes include:

- `PROVIDER_NOT_FOUND`
- `UNSUPPORTED_METRIC`
- `EVALUATION_NOT_FOUND`
- `EXPERIMENT_NOT_FOUND`
- `CANDIDATE_NOT_FOUND`
- `INVALID_EXPERIMENT_REQUEST`
- `JOB_NOT_FOUND`
- `INVALID_JOB_REQUEST`
- `INVALID_JOB_SUBMISSION`
- `IDEMPOTENCY_CONFLICT`
- `INVALID_GOVERNANCE_REQUEST`
- `GOVERNANCE_REPORT_NOT_IMPLEMENTED`
- `DecisionNotFound`
- `InvalidDecisionRequest`
- `DecisionConflict`
- `PolicyNotFound`
- `PolicyVersionNotFound`
- `PolicyConflict`
- `InvalidPolicyRequest`
- `PolicyValidationFailed`
- `PolicyActivationFailed`
- `PolicyArchiveFailed`
- `PolicySimulationFailed`
- `PolicySchemaUnavailable`
- `EvidenceUnavailable`
- `DecisionPersistenceFailed`
- `DecisionReasoningFailed`
- `validation_error`
- `internal_server_error`

## Settings Control Plane

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/settings` | List effective settings, optionally filtered by `category`. |
| `GET` | `/api/v1/settings/{key}` | Read one typed setting. |
| `PATCH` | `/api/v1/settings/{key}` | Compare-and-set a mutable scoped runtime value. |
| `POST` | `/api/v1/settings/validate` | Parse and validate without persistence. |
| `GET` | `/api/v1/settings/categories` | List registry categories and counts. |
| `GET` | `/api/v1/settings/audit` | Read runtime setting modifications. |

Reads accept a `scope` query and resolve `PROJECT → ORGANIZATION → SYSTEM →
default` inheritance after environment overrides. Updates include `scope`,
`expected_version`, `value`, and a required `reason`; a stale version returns
HTTP 409. Reads require `settings.read`; validation and updates require
`settings.manage`. Responses include effective value, persisted runtime value,
source, inheritance source, supported scopes, runtime-consumer status, type,
default, editability, restart behavior, and update metadata.
Environment-controlled settings cannot be changed through this API.

## Boundaries

REST routers must not import repository implementations, provider adapters, or
provider SDKs. They depend on:

- API models
- API mappers
- dependency-injected API service facades

API service facades may orchestrate existing services and repositories, but
core lifecycle, ranking, comparison, drift, and provider behavior remains in
the existing service/provider layers.

Sensitive metadata keys such as API keys, tokens, passwords, secrets, and
authorization values are scrubbed from REST metadata responses.

## Dependency Injection Architecture

The REST API uses a structured dependency package split by platform plane:

```
src/ai_governance/api/dependencies/
    __init__.py              ← backward-compatible re-exports
    settings.py              ← ApiSettings, get_api_settings
    providers.py             ← get_provider_registry
    repositories.py          ← raw repository factories
    evaluation.py            ← evaluation service wiring
    experiments.py           ← experiment API wiring
    registries.py            ← prompt / model / dataset registry services
    ontology.py              ← ontology graph and sync wiring
    decisions.py             ← governance decision wiring
    jobs.py                  ← job API wiring
    dashboard.py             ← dashboard read service
    policies.py              ← policy administration service
    mcp.py                   ← MCP audit log
    governance_insights.py   ← governance insights and reports
```

All public providers are re-exported through ``__init__.py`` so that existing
imports such as ``from ai_governance.api.dependencies import get_evaluation_api_service``
continue to work without changes to route or test code.

### Repository Factories

Repository construction is config-driven. Each repository provider delegates to
a factory class in ``src/ai_governance/repositories/factories/`` that selects the
concrete implementation based on ``AI_GOVERNANCE_*_REPOSITORY`` environment variables.

```python
@lru_cache(maxsize=1)
def get_evaluation_repository() -> Any:
    from ai_governance.settings import load_settings
    from ai_governance.repositories.factories import EvaluationRepositoryFactory

    return EvaluationRepositoryFactory(load_settings()).create()
```

Factories support ``inmemory`` (default), ``sqlite``, and ``postgres`` backends
where implemented. Unsupported backends fail fast with a clear ``ValueError``.
See [Configuration](./CONFIGURATION.md#repository-backends) for the full backend
matrix.

## Related Documents

- [Public API](./PUBLIC_API.md)
- [Architecture](../architecture/ARCHITECTURE.md)
- [Extensibility](../architecture/EXTENSIBILITY.md)
