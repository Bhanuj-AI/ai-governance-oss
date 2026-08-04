# Architecture

## Platform Overview
![Kavach enterprise architecture diagram](/assets/Enterprise%20Architecture%20-%20Marketing.png)

Kavach is a governance control plane for AI systems. It records governed AI
assets, evaluates AI configurations, persists execution evidence, reconstructs
history, analyzes quality change, ranks experiment candidates, and produces
recommendations. It does not own prompt deployment, model deployment,
infrastructure orchestration, or CI/CD execution.

The architecture keeps frameworks and infrastructure at the edge. Runtime
systems can call into Kavach, but Kavach is not the runtime itself.

### Future State
![Kavach enterprise architecture diagram](/assets/Enterprise%20Architecture%20-%20Technical.png)

## Architectural Planes

### Runtime Edge

The Runtime Edge is any external system that produces workflow executions or
requests evaluations. This can be an orchestration framework, an internal
service, a CLI, or the REST control plane.

Kavach depends on the Runtime Edge only through explicit contracts.

### Authentication Plane

The Authentication Plane validates identity tokens and establishes a trusted
principal before any authorization or business logic executes. Kavach supports
two authentication modes:

- **Development mode** (`KAVACH_AUTH_MODE=development`) — actor identity comes
  from the ``X-Kavach-Actor-Id`` header or the ``KAVACH_DEVELOPMENT_ACTOR_ID``
  environment variable. No token validation occurs.
- **Keycloak mode** (`KAVACH_AUTH_MODE=keycloak`) — requires a ``Bearer`` JWT
  in the ``Authorization`` header. The platform validates the token signature
  against Keycloak JWKS, checks issuer and expiry, and builds an immutable
  ``AuthenticatedPrincipal`` from the validated claims.

The authentication plane is strictly separate from authorization. JWT claims
establish identity only; they never grant permissions. Every request still flows
through the existing ``AuthorizationService`` and RBAC model.

```text
JWT (Bearer token)
    |
    v
AuthenticationService
    |  - Validate signature (JWKS)
    |  - Validate issuer
    |  - Validate expiry
    |  - Build AuthenticatedPrincipal
    v
AuthenticatedPrincipal
    |  - subject (immutable actor ID)
    |  - principal_type (USER / SERVICE / SYSTEM)
    |  - organization_id (optional scope hint)
    |  - client_id
    v
TenantContextFactory
    |  - Maps principal.subject -> TenantContext.actor_id
    |  - Generates request_id
    |  - Preserves correlation_id
    v
TenantContext
    |
    v
AuthorizationService (existing RBAC)
```

Configuration:

| Variable | Default | Purpose |
| --- | --- | --- |
| ``KAVACH_AUTH_MODE`` | ``development`` | Authentication mode: ``development`` or ``keycloak``. |
| ``KAVACH_OIDC_ISSUER`` | - | Keycloak realm URL (e.g. ``http://localhost:8080/realms/kavach``). Required in keycloak mode. |
| ``KAVACH_OIDC_JWKS_REFRESH_SECONDS`` | ``300`` | JWKS signing key cache TTL in seconds. |

### Bootstrap administrator identity

The initial Kavach administrator is provisioned during control-plane bootstrap
(idempotent). The identity used depends on ``auth_mode``:

- **Development mode** — uses ``KAVACH_DEVELOPMENT_ACTOR_ID`` (fallback:
  ``local-admin``) and ``KAVACH_DEVELOPMENT_ACTOR_NAME`` (fallback:
  ``Local Administrator``).
- **Keycloak mode** — requires ``KAVACH_BOOTSTRAP_ADMIN_SUB`` (the immutable
  Keycloak user ``sub``). Fails startup if absent. Optionally uses
  ``KAVACH_BOOTSTRAP_ADMIN_NAME`` for display purposes.

The bootstrap operation is idempotent — repeated startup does not create
duplicate organizations or memberships.

Studio's browser authentication, token forwarding, Keycloak realm contract,
and local bootstrap sequence are documented in
[Keycloak integration design](./KEYCLOAK_INTEGRATION.md).

### Audit Plane

The Audit Plane captures workflow and node-level execution records. It stores
the evidence required to understand what happened during an AI workflow and to
reconstruct that workflow later.

### Replay Plane

The Replay Plane reconstructs historical workflow executions from persisted
audit state. Replay exists to support investigation, debugging, and governance
review rather than to rerun live traffic.

### Evaluation Plane

The Evaluation Plane turns workflow outputs into evaluation results. Providers
such as TruLens sit here behind provider contracts. An adapter contributes its
immutable descriptor and a versioned, secret-free configuration schema resource;
Studio renders configuration from that schema rather than encoding provider
fields. A durable installation selects that adapter with organization-wide
settings, optional project-local variation, and secret references resolved only
when a worker executes. Evaluation exists to create governance evidence, not to
be the platform boundary.

### Job Execution Plane

The Job Execution Plane records and executes long-running governance work such
as evaluation, experiment, replay, and drift analysis jobs. It owns Kavach job
semantics such as idempotent submission, queued/running/succeeded/failed states,
worker leases, retry attempts, cancellation, and immutable result references.

It is not a workflow engine. External systems may submit or schedule jobs, but
they own DAGs, cron, branching, and orchestration sequencing.

### Persistence Plane

The Persistence Plane stores governed artifacts and evidence through repository
contracts. Each repository type is backed by a factory class that selects the
concrete implementation based on runtime configuration (``KAVACH_*_REPOSITORY``
environment variables). SQLite is the current durable reference implementation.
The architecture treats storage as replaceable.

Repository backend selection is a control-plane concern:

```text
Environment Variables
        │
        ▼
Kavach Settings
        │
        ▼
Repository Factory
        │
        ▼
Concrete Repository
(InMemory / SQLite / Postgres)
        │
        ▼
FastAPI Dependency Provider
        │
        ▼
Application Service
```

Factories live in ``src/kavach/repositories/factories/``. Each factory accepts
``Settings`` and returns the appropriate repository implementation. Unsupported
backends fail fast with a clear ``ValueError`` — no silent fallback to
in-memory.

The dependency direction for repository construction is:

```text
Settings (environment variables)
        │
        ▼
Repository Factory
        │
        ▼
Concrete Repository Implementation
```

Factories must not import FastAPI dependency modules. Dependency providers may
call factories, but factories must not call dependency providers.

### History Plane

The History Plane retrieves persisted evaluations and organizes them into
history views, trends, summaries, and comparisons. It provides the longitudinal
view needed for governance decisions.

### Governance Plane

The Governance Plane analyzes change over time. It compares evaluations,
calculates drift, and produces governance-oriented artifacts from historical
data. This plane interprets evidence; it does not execute deployments.

Governed outcomes are represented by the `GovernanceDecision` domain model.
The model captures the decision type, status, ontology-aligned target,
evidence references, policy references, provenance, confidence, and
supersession metadata. Persistence, transport APIs, full decision-engine
orchestration, and graph synchronization remain separate architectural
concerns.

Structured governance policies are represented by `GovernancePolicy` and
evaluated by `GovernancePolicyEvaluator`. The evaluator is deterministic and
evidence-local: it evaluates prioritized structured conditions against a
provided evidence context, but it does not fetch evidence, traverse the
ontology graph, persist outcomes, or orchestrate a full decision engine.

Decision-ready evidence is prepared by `DecisionEvidenceBuilder`. The builder
uses the ontology graph query service to collect a bounded evidence
neighbourhood, reports missing evidence explicitly, summarizes stable evidence
IDs, and derives policy evaluation context. It is read-only and does not create
decisions, execute policies, persist evidence, or mutate the graph.

Governance reasoning is orchestrated by `GovernanceReasoningEngine`. The engine
connects evidence building, deterministic evidence summarization, policy
evaluation, outcome precedence, confidence mapping, decision construction, and
non-LLM explanation generation. It produces in-memory decisions only;
persistence and human approval workflows remain separate concerns.

Durable decisions are stored behind the `GovernanceDecisionRepository`
contract. SQLite and PostgreSQL implementations persist governance decisions,
optional deterministic explanations, and audit records while enforcing
finalized-decision immutability. Repository lifecycle operations support
idempotent saves, query by target/status/request ID/correlation ID,
supersession without deleting the old decision, and archival. Repositories may
publish ontology sync events for created, superseded, and archived decisions,
but they do not write directly to Neo4j or embed policy evaluation logic.

Studio policy administration is stored behind the
`PolicyAdministrationRepository` contract. In-memory, SQLite, and PostgreSQL
implementations persist policy definitions and executable policy versions,
including target types, structured rules, lifecycle timestamps, archive state,
pagination, and filterable inventory queries. Repository implementations
enforce one active version per policy by deprecating the previous active
version transactionally when a new active version is saved.

`GovernanceDecisionApplicationService` is the application boundary for REST
and MCP decision workflows. It invokes `GovernanceReasoningEngine`, persists
the resulting decision and explanation, records audit, enforces public
idempotency semantics, normalizes decision errors, and delegates lineage to
`OntologyGraphQueryService`.

Ontology projection remains a separate synchronization concern.
`GovernanceDecisionOntologySynchronizer` accepts either an explicit projection
DTO or a `GovernanceDecision` aggregate and creates graph relationships only
through `OntologyService`.

The canonical semantic contract for governance entities, relationships,
actions, and lifecycle events is defined in the
[Governance Ontology](./GOVERNANCE_ONTOLOGY.md).

![Kavach Ontology Graph](../../assets/Kavach%20Ontology%20Graph.png)

### Registry Plane

The Assets Plane distinguishes ownership as well as versioning. Datasets and
evaluation-provider adapters are **managed** assets: Kavach owns their
registration and lifecycle. Prompt and model records are **observed** assets:
Kavach catalogs the identities and runtime configuration captured by governed
work; it is not a prompt-authoring or model-serving system. The Assets
workspace presents these catalogs with a consistent version, reference,
lineage, and audit-history workflow.

Every persisted asset record carries provenance: `MANAGED`, `OBSERVED`, or the
reserved future value `IMPORTED`, plus optional source-system and source-
reference metadata. The OSS observation endpoints accept generic execution or
evaluation evidence; they do not bundle vendor-specific connectors. Prompt
content can be intentionally withheld while preserving a content hash for
identity and reproducibility.

Registry metadata stays in the configured repository. Dataset *content* is
separate: the local stack writes seeded JSONL to SeaweedFS through the standard
S3 API and records an `s3://` URI in the dataset registry. Production can use
AWS S3 without changing registry semantics or the dataset object-store
contract.

### Experiment Plane

The Experiment Plane assembles governed assets into experiment candidates,
tracks evaluation runs, performs candidate comparison, ranks candidates, and
persists leaderboards.

### API Adapter Plane

The API Adapter Plane exposes framework-neutral route metadata and serializable
payloads. `GovernanceAPI` and `LeaderboardAPI` live here. They do not start a
web server and do not depend on FastAPI, Flask, or another transport framework.

### REST Control Plane

The REST Control Plane exposes versioned HTTP APIs through FastAPI. It provides
health, readiness, API metadata, registry discovery, evaluation submission,
evaluation history, experiment execution, leaderboards, comparison, and drift
analysis endpoints.

REST routers remain transport-only. They depend on API DTOs, mappers, and
application facades. Business rules stay in services and registries, repository
access stays behind services, and provider-specific SDKs stay behind provider
adapters.

## Dependency Direction

The dependency direction is inward toward contracts and domain objects.

```text
External runtimes / transports
        |
        v
API adapters, REST routers, and providers
        |
        v
Services and analyzers
        |
        v
Repositories and mappers
        |
        v
Storage implementations
```

Two rules matter:

- Services depend on repositories, not on storage implementations.
- API adapters depend on services, not on repositories or runtimes directly.

Repository construction follows a separate dependency chain:

```text
Environment Variables
        |
        v
Kavach Settings
        |
        v
Repository Factory
        |
        v
Concrete Repository Implementation
```

Factories must not import FastAPI dependency modules. Dependency providers may
call factories, but factories must not call dependency providers.

## End-to-End Data Flow

The core experiment governance flow is:

```text
Experiment
    |
    v
Experiment Candidate
    |
    v
Evaluation Run
    |
    v
Evaluation Result
    |
    v
Evaluation History
    |
    +--> Comparison / Drift
    |
    v
Ranking
    |
    v
Leaderboard
    |
    v
Recommendation
```

The asynchronous governance job flow is:

```text
JobSubmission
    |
    v
JobRepository
    |
    v
JobWorker
    |
    v
JobExecutor
    |
    v
Domain Service Handler
    |
    v
Immutable Result Ref
```

The flow from asset registration to recommendation is broader:

```text
Prompt Registry ----+
Model Registry -----+--> Experiment Candidate --> Evaluation Run
Dataset Registry ---+                              |
                                                   v
                                            Evaluation Result
                                                   |
                                                   v
                                            History / Comparison
                                                   |
                                                   v
                                               Leaderboard
                                                   |
                                                   v
                                            Recommendation
```

## Replaceable Components

Kavach keeps provider and storage choices behind contracts.

- Evaluation providers are pluggable.
- Repository implementations are pluggable, selected via factory classes.
- SQLite is a current durable backend, not the architectural center.
- REST, CLI, SDK, or MCP adapters can sit above services and framework-neutral
  APIs.

This allows the platform to evolve without rewriting governance logic when a
provider, store, or transport changes.

## Repository Factory Pattern

Repository backend selection is a control-plane configuration concern. Each
repository type has its own factory class in ``src/kavach/repositories/factories/``.

```text
Environment Variables
        │
        ▼
Kavach Settings
        │
        ▼
Repository Factory
        │
        ▼
Concrete Repository
(InMemory / SQLite / Postgres)
        │
        ▼
FastAPI Dependency Provider
        │
        ▼
Application Service
```

Key principles:

- Repository backend selection is a control-plane concern.
- Services depend only on repository contracts, not implementations.
- Dependency providers compose the system but do not choose implementations.
- Repository factories own backend selection.
- Repository implementations are replaceable without changing application services.
- No silent fallback — unsupported backends fail fast with clear errors.

## Framework-Neutral APIs

The current API adapter plane exposes:

- `GovernanceAPI` for history, comparison, and drift payloads
- `LeaderboardAPI` for leaderboard and recommendation payloads

These adapters return plain Python values and route metadata. They are
transport-friendly, but transport-agnostic.

## REST APIs

The current REST control plane exposes:

- `/health` and `/ready` for service checks
- `/api/v1` for API metadata
- `/api/v1/providers` for provider discovery
- `/api/v1/provider-installations` for schema-validated provider configuration
- `/api/v1/prompts`, `/api/v1/models`, and `/api/v1/datasets` for registry reads
- `/api/v1/evaluations` for synchronous evaluation submission and persisted result reads
- `/api/v1/experiments` for experiment creation, candidates, runs, candidate
  comparisons, and leaderboards
- `/api/v1/governance` for comparison, drift analysis, and report lookup
- `/api/v1/jobs` for async governance job submission, status lookup, listing, cancellation, retry, and result references

The REST layer is intentionally separate from provider adapters. It must not
import TruLens, OpenAI, or other provider SDKs directly.
Worker leasing, heartbeat, and success/failure mutation APIs are intentionally
not exposed through public REST routes.

## Non-Goals

The architecture intentionally does not make Kavach responsible for:

- prompt deployment
- model deployment
- runtime promotion
- infrastructure management
- web-server ownership
- CI/CD orchestration

Those systems can consume Kavach recommendations, but they remain outside the
platform boundary.

## Related Documents

- [Design Principles](./DESIGN_PRINCIPLES.md)
- [Governance Ontology](./GOVERNANCE_ONTOLOGY.md)
- [Ontology Foundation](../ontology/ontology-foundation.md)
- [Ontology Synchronization](../ontology/ontology-synchronization.md)
- [Experiment Management](./EXPERIMENT_MANAGEMENT.md)
- [Extensibility](./EXTENSIBILITY.md)
- [Public API](../reference/PUBLIC_API.md)
