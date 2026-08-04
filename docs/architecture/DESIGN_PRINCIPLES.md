# Design Principles

## Control Plane Ownership

Kavach owns governance state and governance decisions. It tracks assets,
results, comparisons, rankings, and recommendations. It does not own the live
AI runtime or the deployment system.

## Explicit Contracts

Every boundary should be visible in code and understandable from local context.
Repository interfaces, provider interfaces, and framework-neutral APIs are all
examples of explicit contracts.

Hidden cross-system contracts are avoided because they make replay, migration,
and extension brittle.

## Repository vs Registry vs Service

Repositories own persistence only. They store and retrieve domain records.
Registries own lifecycle and governance rules for versioned assets. Services own
orchestration and domain workflows that span multiple repositories.

Good:

- `PromptRegistryService` owns activation and archival rules.
- `RankingService` owns candidate ranking and leaderboard generation.

Bad:

- `SQLitePromptRepository` owns lifecycle transitions.
- `SQLiteLeaderboardRepository` decides which candidate should win.

## Immutable Artifacts

Governed records should be immutable where possible. Immutable prompts, models,
datasets, evaluation runs, and leaderboards make historical reasoning simpler
and replay safer.

Mutable control flows should create new records or new versions instead of
mutating historical facts.

## Version Everything

Prompts, models, datasets, and experiment-facing artifacts should be versioned.
Versioning is required for reproducibility, comparison, auditability, and
replay.

## Replayability

If a governance decision cannot be reconstructed later, it is weak evidence.
Replayability is a first-order requirement, not a debugging extra.

That requirement affects storage, versioning, immutability, and API design.

## Storage Independence

The platform does not depend on SQLite as a core architectural choice. SQLite
is the local and reference backend today. Repository contracts preserve the
ability to add PostgreSQL, Snowflake, or other stores later.

## Provider Independence

Evaluation logic must remain behind provider interfaces. TruLens is the current
implementation, but the architecture should not require TruLens-specific
knowledge outside provider code.

## Framework-Neutral APIs

API adapters return route metadata and serializable payloads without taking a
dependency on an HTTP framework, CLI framework, or SDK generator.

Good:

- `LeaderboardAPI` returns payloads that can also be exposed by the REST control plane.

Bad:

- `LeaderboardAPI` deploys the winning candidate.

## Governance over Deployment

Kavach recommends and records; downstream systems deploy. The boundary matters
because governance evidence must remain transportable across runtime and release
platforms.

## Failure Isolation

Failures should stop at the narrowest useful boundary. A provider failure should
not silently mutate registry state. A persistence implementation should not own
fallback business logic. A transport adapter should not rerun ranking logic.

## Debuggability

The system should be explainable from persisted facts:

- which version was evaluated
- which provider produced the result
- which run completed
- which leaderboard recommended a candidate

The design prefers explicit records over clever indirection.

## Operational Stability over Elegance

The repository favors predictable ownership boundaries over abstraction density.
The correct question is whether a change preserves governable behavior, not
whether it reduces a few lines of code.

## Related Documents

- [Architecture](./ARCHITECTURE.md)
- [Decisions](./DECISIONS.md)
- [Extensibility](./EXTENSIBILITY.md)
