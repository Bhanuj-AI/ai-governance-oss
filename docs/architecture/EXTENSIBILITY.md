# Extensibility

## Overview

AI Governance Control Plane is designed to grow through explicit extension points. New providers,
stores, analyzers, and adapters should fit into existing ownership boundaries
instead of bypassing them.

## Open-Core Plugin Framework

The OSS package owns the extension contracts consumed by separately released
plugins, including a future `ai-governance-enterprise` package. The dependency flow is
one way: an extension may import `ai_governance.spi`, `ai_governance.plugins`,
`ai_governance.hooks`, and `ai_governance.events`; AI Governance Control Plane OSS never imports or detects a
specific extension package.

Plugins are loaded from the `ai_governance.plugins` Python entry-point group and may
also be passed directly to `create_app(plugins=[...])` in an embedding
application. Every plugin declares immutable `PluginMetadata`, including its
compatible AI Governance Control Plane version range and requested capabilities. Startup fails for
duplicate names, incompatible versions, unsupported capabilities, provider
conflicts, route conflicts, and plugin lifecycle failures.

An independently released extension package registers its plugin through
standard Python package metadata—there is no OSS source modification or
enterprise-specific import:

```toml
# ai-governance-enterprise/pyproject.toml
[project]
dependencies = ["ai-governance>=1.2,<1.3"]

[project.entry-points."ai_governance.plugins"]
enterprise-quality = "ai_governance_enterprise.plugins.quality:QualityPlugin"
```

```python
from ai_governance.events import EvaluationCompleted
from ai_governance.hooks import FailurePolicy
from ai_governance.plugins import AIGovernancePlugin, PluginMetadata
from ai_governance.spi.search import SearchProvider


class QualityPlugin(AIGovernancePlugin):
    metadata = PluginMetadata(
        name="quality-plugin",
        version="1.0.0",
        required_ai_governance_version=">=1.2,<1.3",
        capabilities=("search.read",),
    )

    def validate(self, context):
        pass

    def register(self, context):
        context.providers.register(SearchProvider, EnterpriseSearch(), replace=True)
        context.hooks.register(
            name="after_execution",
            handler=self.record_execution,
            order=100,
            failure_policy=FailurePolicy.ISOLATE_AND_CONTINUE,
        )
        context.events.subscribe(
            event_type=EvaluationCompleted,
            handler=self.analyze_evaluation,
        )
        context.routes.add(
            method="GET",
            path="/api/v1/intelligence/findings",
            handler=self.list_findings,
        )

    def start(self, context):
        pass

    def stop(self, context):
        pass
```

Provider replacement always requires `replace=True`; decorators compose around
the currently resolved provider. Hooks and event subscriptions are ordered by
`(order, registration order)`, receive explicit immutable tenant context, and
record execution outcomes. Route replacement is disabled unless OSS explicitly
authorizes that method/path as a replacement point; adding a duplicate route
always fails startup.

Operators can inspect the resolved plugin, provider, hook, event, and route
state at `GET /api/v1/runtime/extensions`. Extension implementations must not
import `ai_governance.services`, `ai_governance.repositories`, or other undocumented runtime
internals.

Three working rules apply across extensions:

- add mappers for persistence implementations
- add repository contract tests for repository implementations
- keep adapters thin and provider-specific code isolated
- keep REST routers thin and delegate business behavior to API services
- keep MCP tools thin and delegate every operation to one REST endpoint

## Model Runtime Providers

OSS includes native Runtime Connection adapters for OpenAI and Anthropic, and
OpenAI-compatible custom endpoints. The allowed-provider setting is an
authorization policy, not a provider installation mechanism: adding a provider
name to that setting cannot make the platform discover models or invoke a
provider it does not implement.

To add a non-compatible native runtime, contribute or maintain a fork that
adds all three provider-owned pieces: a `ModelRuntimeAdapter` for candidate
execution, a model-catalog discovery implementation, and a deterministic
runtime capability profile. The adapter must be wired into both API and worker
composition, preserve tenant-scoped Runtime Connection resolution, and never
persist or log credential values. Do not present an unimplemented provider as
an OSS Runtime Connection option.

## EvaluationProvider

Responsibility:
Produce `EvaluationResult` objects from evaluation inputs.

Must not own:
Persistence, experiment lifecycle, ranking, or transport behavior.

Expected tests:
Provider-specific unit tests and integration tests that validate returned
metrics and metadata shape.

Example use case:
Add a Phoenix-backed provider alongside TruLens.

## EvaluationRepository

Responsibility:
Persist and retrieve evaluation results.

Must not own:
Metric interpretation, drift logic, or lifecycle rules.

Expected tests:
Repository contract tests, mapper tests, and storage implementation tests.

Example use case:
Add another provider-backed evaluation repository alongside the SQLite and
PostgreSQL implementations.

## PromptRepository

Responsibility:
Store prompt versions and retrieve them by ID or logical version identity.

Must not own:
Activation, archival, or version conflict rules.

Expected tests:
Repository contract tests plus mapper coverage for persistence-backed
implementations.

Example use case:
Add a production relational store for prompt governance.

## ModelRepository

Responsibility:
Persist governed model versions and resolve them by logical model identity.

Must not own:
Activation and deprecation orchestration.

Expected tests:
Repository contract tests and mapper tests.

Example use case:
Store enterprise model metadata in another repository backend.

## DatasetRepository

Responsibility:
Persist governed dataset metadata.

Must not own:
Dataset promotion, freezing, or archival policy.

Expected tests:
Repository contract tests and mapper tests.

Example use case:
Back dataset governance with a shared operational database.

## ExperimentRepository

Responsibility:
Persist experiment metadata and lifecycle state.

Must not own:
Candidate creation, evaluation execution, or ranking behavior.

Expected tests:
Repository contract tests and storage-specific tests.

Example use case:
Store experiments in a multi-user backend.

## EvaluationRunRepository

Responsibility:
Persist experiment evaluation run evidence.

Must not own:
Evaluation execution, run status policy beyond storage semantics, or ranking.

Expected tests:
Repository contract tests and persistence tests.

Example use case:
Move evaluation run storage to another shared backend.

## LeaderboardRepository

Responsibility:
Persist immutable leaderboards and leaderboard entries.

Must not own:
Ranking calculations, recommendation logic, or transport payload formatting.

Expected tests:
Repository contract tests, mapper tests, and backend-specific persistence tests.

Example use case:
Persist leaderboard history for organization-wide governance review.

## GovernanceAPI

Responsibility:
Expose history, latest evaluation, drift, and comparison payloads through a
framework-neutral adapter.

Must not own:
Evaluation execution, storage access details, or web-server behavior.

Expected tests:
API unit tests for route metadata and payload conversion.

Example use case:
Reuse governance route metadata in a CLI, SDK, or documentation generator.

## LeaderboardAPI

Responsibility:
Expose leaderboard and recommendation payloads through a framework-neutral
adapter.

Must not own:
Ranking generation, candidate deployment, or transport framework lifecycle.

Expected tests:
API unit tests for route metadata, latest leaderboard lookup, and
recommendation semantics.

Example use case:
Publish experiment recommendations to a CLI or internal release tool.

## REST Routers

Responsibility:
Expose versioned HTTP endpoints using DTOs, mappers, and dependency-injected
API services.

Must not own:
Repository access, provider SDK imports, ranking rules, drift rules, lifecycle
policy, or persistence mapping.

Expected tests:
API tests for status codes, response DTOs, error envelopes, OpenAPI exposure,
dependency overrides, and import-boundary checks.

Example use case:
Add a new `/api/v1` resource group for an existing service capability.

## API Service Facades

Responsibility:
Adapt REST inputs into existing application service calls and map service
errors into transport-specific exceptions.

Must not own:
Core domain rules that already belong in registry, experiment, evaluation,
ranking, or governance services.

Expected tests:
Facade or endpoint tests proving service delegation, validation boundaries, and
privacy constraints such as not returning provider configuration.

Example use case:
Coordinate experiment execution from a synchronous REST request while keeping
candidate validation, evaluation, and ranking behavior in existing services.

## MCP Tools

Responsibility:
Expose existing AI Governance Control Plane REST control-plane capabilities to AI assistants and
agent frameworks through tool calls.

Must not own:
Repositories, provider SDKs, domain object construction, worker operations, or
business rules.

Expected tests:
Tool registration, request validation, REST request mapping, response mapping,
error translation, metrics, and REST integration tests.

Example use case:
Expose `evaluation.history` as a tool that calls the REST evaluation history
endpoint and returns the REST DTO payload.

### Optional MCP Tool Packages

An optional tool package registers through the `ai_governance.mcp.plugins` Python
entry-point group. It implements `MCPToolPlugin` and receives only
`MCPToolPluginContext`, which registers a tool and performs tenant-scoped REST
GET or POST calls. The MCP server discovers compatible packages during startup;
it does not import or conditionally name an Enterprise distribution.

Use this boundary for tools whose REST capability is owned by an independently
released extension. Core MCP handlers remain in OSS when they expose OSS REST
capabilities.

## RankingStrategy

Responsibility:
Score candidates according to a defined optimization rule.

Must not own:
Persistence, candidate retrieval, or transport behavior.

Expected tests:
Strategy unit tests for scoring behavior and error handling.

Example use case:
Add a weighted multi-objective ranking strategy.

## DriftAnalyzer-Style Governance Analyzers

Responsibility:
Interpret historical evidence and identify meaningful quality change.

Must not own:
Storage, experiment execution, or transport concerns.

Expected tests:
Analyzer unit tests with representative metric histories and edge cases.

Example use case:
Add dataset statistical drift analysis or policy-driven regression gating.

## JobHandler

Responsibility:
Execute one governance job type and return a stable `JobResult` with an
immutable result reference.

Must not own:
Scheduling, DAG orchestration, provider SDK setup, or repository lease
management.

Expected tests:
Handler tests should verify result references, failure behavior, and
idempotency assumptions for the domain operation they wrap.

Example use case:
Add an experiment job handler that invokes existing experiment services and
returns a leaderboard or evaluation run reference.

## JobRepository

Responsibility:
Persist job state, idempotency keys, input hashes, attempt counts, leases,
heartbeats, and result references.

Must not own:
Domain execution, scheduling, workflow dependencies, or retry policy beyond
the repository state transitions required by the job contract.

Expected tests:
Repository tests for idempotency lookup, queued acquisition, lease expiry,
retry exhaustion, cancellation, success, and failure transitions.

Example use case:
Add PostgreSQL or Snowflake job persistence behind the same job repository
contract.

## Implementation Guidance

When adding a new persistence backend:

1. implement the repository contract
2. add a persistence mapper if records differ from domain objects
3. create or extend the corresponding factory class in
   ``src/ai_governance/repositories/factories/``
4. add configuration fields to ``Settings`` in ``src/ai_governance/settings.py``
5. update the REST dependency provider to use the factory
6. reuse the existing contract test pattern
7. add backend-specific tests for indexing, ordering, and replacement semantics

SQLite, PostgreSQL, and Snowflake are the current relational repository
implementations. SQLite remains useful for local development and tests.
PostgreSQL is the production OLTP reference persistence implementation.
Snowflake is an optional enterprise analytics persistence implementation.
All sit below repository contracts, and services should not depend directly on
any database.

### Adding a New Repository Factory

1. Define the repository contract (``ABC`` or ``Protocol``).
2. Implement one or more concrete repositories.
3. Create a factory class in ``src/ai_governance/repositories/factories/``.
4. Add configuration to ``AIGovernanceSettings`` (``src/ai_governance/settings.py``).
5. Update the REST dependency provider to delegate to the factory.
6. Add unit tests for the factory (inmemory, sqlite, postgres-not-implemented,
   invalid-backend).
7. Update architecture and configuration documentation.

Repository providers should never instantiate concrete repository implementations
directly. Backend selection is owned by factories.

Snowflake support is deliberately scoped to persistence. It does not add
Snowpark, Cortex, Streams, Dynamic Tables, Tasks, Native Apps, runtime
deployment, or orchestration behavior.

When adding a new adapter:

1. depend on services, not repositories
2. return transport-friendly payloads
3. keep route metadata explicit
4. do not trigger domain side effects during reads

When adding a REST endpoint:

1. define request and response DTOs
2. add a mapper between DTOs and domain/service objects
3. delegate behavior to an API service facade
4. keep routers free of repository imports and provider SDK imports
5. add API tests for success, errors, OpenAPI, and import boundaries

Job REST endpoints may expose public submission, lookup, cancellation, retry,
and result-reference operations. They must not expose worker-only leasing,
heartbeat, or success/failure mutation operations.

When adding an MCP tool:

1. define a request DTO
2. register an OSS-owned tool during MCP server startup, or contribute an
   optional tool through `MCPToolPlugin` and the `ai_governance.mcp.plugins` entry
   point
3. delegate to exactly one REST endpoint
4. map REST errors through the MCP exception mapper
5. add unit tests for validation and request mapping

When adding a new job type:

1. add or reuse a `JobType`
2. define the expected `input_refs` contract
3. implement a `JobHandler`
4. register the handler with `JobExecutor`
5. return an immutable `result_ref`
6. keep scheduling and workflow sequencing outside AI Governance Control Plane

When adding provider-specific logic:

1. keep it behind the provider boundary
2. do not let provider assumptions leak into registries or APIs
3. preserve replay and reproducibility semantics

## Related Documents

- [Architecture](./ARCHITECTURE.md)
- [Design Principles](./DESIGN_PRINCIPLES.md)
- [Public API](../reference/PUBLIC_API.md)
- [SQLite Schema](../reference/SQLITE_SCHEMA.md)
- [PostgreSQL Schema](../reference/POSTGRES_SCHEMA.md)
- [Snowflake Schema](../reference/SNOWFLAKE_SCHEMA.md)
- [MCP Server](../reference/MCP_SERVER.md)
