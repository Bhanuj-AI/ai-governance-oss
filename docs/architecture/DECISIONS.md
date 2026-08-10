# Decisions

## ADR-001: AI Governance Control Plane Is a Governance Control Plane, Not an AI Runtime

Status: Accepted

### Context

AI systems need governance that survives runtime changes and framework churn.

### Decision

AI Governance Control Plane focuses on governance artifacts, evidence, and recommendations rather
than direct runtime execution ownership.

### Consequences

- runtime frameworks stay outside the core architecture
- governance logic remains reusable across runtimes
- deployment is intentionally out of scope

## ADR-002: Repositories Do Not Own Business Rules

Status: Accepted

### Context

Persistence code becomes brittle when it owns lifecycle or orchestration logic.

### Decision

Repositories store and retrieve records only. Business rules live in services
and registries.

### Consequences

- storage backends remain replaceable
- repository contract tests stay focused
- lifecycle rules have a single home

## ADR-003: Registry Services Own Lifecycle Transitions

Status: Accepted

### Context

Prompts, models, and datasets require governance-specific lifecycle rules.

### Decision

Registry services own activation, deprecation, archival, and related policy.

### Consequences

- lifecycle policy is centralized
- repositories remain simple
- future transports can reuse the same governance rules

## ADR-004: Prompts, Models, Datasets, and Experiments Are Versioned

Status: Accepted

### Context

Historical comparison and replay require exact artifact identity.

### Decision

Governed asset types and experiment-facing records should preserve versioned
identity rather than mutate in place.

### Consequences

- comparisons remain explainable
- replay remains possible
- historical governance evidence is stronger

## ADR-005: Framework-Neutral APIs Before Transport Adapters

Status: Accepted

### Context

The platform needs a transport layer, but not every consumer is an HTTP server.

### Decision

AI Governance Control Plane exposes framework-neutral API adapters first and keeps REST, CLI, or SDK
mounting in outer layers. The FastAPI REST control plane follows this decision
by staying thin and delegating behavior to services and API facades.

### Consequences

- transport logic stays thin
- API behavior is testable without server setup
- framework lock-in is reduced

## ADR-006: SQLite Is a Local/Reference Persistence Implementation, Not the Platform Boundary

Status: Accepted

### Context

SQLite is useful for local development and tests, but it should not define the
platform architecture.

### Decision

SQLite remains a reference backend behind repository contracts.

### Consequences

- future relational or analytical stores can be added
- architecture remains storage-agnostic
- local workflows stay lightweight

## ADR-007: Leaderboards Produce Recommendations, Not Deployments

Status: Accepted

### Context

Ranking outputs are governance evidence, but deployment requires separate
release and infrastructure controls.

### Decision

Leaderboards and leaderboard APIs stop at recommendation semantics.

### Consequences

- AI Governance Control Plane avoids hidden promotion side effects
- external release systems remain in control
- governance artifacts remain portable

## ADR-008: Experiments Reference Registry Entities Instead of Duplicating Asset Metadata

Status: Accepted

### Context

Duplicating prompt, model, or dataset metadata inside experiments would create
drift and competing sources of truth.

### Decision

Experiment candidates reference governed registry entities and versions rather
than embedding copied asset records.

### Consequences

- asset governance stays centralized
- experiments remain smaller and more stable
- replay and comparison use exact governed identities

## Related Documents

- [Architecture](./ARCHITECTURE.md)
- [Design Principles](./DESIGN_PRINCIPLES.md)
- [Experiment Management](./EXPERIMENT_MANAGEMENT.md)
