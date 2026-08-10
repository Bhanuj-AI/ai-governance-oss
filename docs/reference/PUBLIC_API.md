# Public API

## Overview

This document summarizes the current public API surface exposed by the AI Governance Control Plane
package. It focuses on responsibilities and usage boundaries rather than
exhaustive method signatures.

Public APIs expose and project the canonical
[Governance Ontology](../architecture/GOVERNANCE_ONTOLOGY.md). API DTOs and MCP
tools should preserve the ontology's entity, relationship, action, and event
semantics even when the transport shape differs.

For startup and environment variables, see
[Configuration](./CONFIGURATION.md). For HTTP endpoints, see
[REST API](./REST_API.md). For MCP tools, see [MCP Server](./MCP_SERVER.md).
For an API-orchestrated product walkthrough, see the
[Governed Replay Walkthrough](../tutorials/governed-replay-walkthrough.md).

## Extension API

The stable open-core extension surface is intentionally package-scoped:

- `ai_governance.spi`: provider contracts, including `SearchProvider` and
  `EvaluationProvider`
- `ai_governance.plugins`: `AIGovernancePlugin`, `PluginMetadata`, lifecycle context, and
  explicit provider/route registries
- `ai_governance.hooks`: immutable hook invocations, failure policies, and the hook
  registry
- `ai_governance.events`: versioned `DomainEvent` contracts, including
  `EvaluationCompleted`, and the event publisher

Extensions must use these packages rather than importing core implementation
services or repositories. See [Extensibility](../architecture/EXTENSIBILITY.md)
for registration, lifecycle, compatibility, and route-contribution rules.

## Domain Models

### GovernanceDecision

Responsibility:
Represent an evidence-backed governance outcome produced by AI Governance Control Plane.

Public imports:

- `ai_governance.GovernanceDecision`
- `ai_governance.decisions.GovernanceDecision`
- `ai_governance.domain.GovernanceDecision`

Related decision value objects and enums:

- `DecisionType`
- `DecisionStatus`
- `DecisionTargetType`
- `DecisionProducerType`
- `DecisionConfidenceLevel`
- `DecisionTarget`
- `DecisionEvidenceReference`
- `DecisionPolicyReference`
- `DecisionProvenance`
- `DecisionSupersession`
- `DecisionAuditAction`
- `DecisionAuditRecord`
- `DecisionValidationError`

Notes:

- targets must use ontology-aligned `DecisionTargetType` values
- every decision requires at least one `DecisionEvidenceReference`
- policies are references only; policy execution is not part of the domain
  model
- provenance requires a non-empty producer ID and timezone-aware creation time
- finalized decisions are represented as immutable dataclass instances
- helper factories are available for proposed, approved, rejected, and blocked
  decisions
- persistence, REST endpoints, MCP tools, ontology synchronization, and
  decision-engine orchestration are separate layers

### GovernancePolicy

Responsibility:
Represent a versioned, deterministic policy definition for producing
governance-oriented outcomes from structured evidence.

Public imports:

- `ai_governance.GovernancePolicy`
- `ai_governance.decisions.GovernancePolicy`
- `ai_governance.domain.GovernancePolicy`

Related policy models and enums:

- `PolicyStatus`
- `PolicyCategory`
- `PolicySeverity`
- `PolicyEffect`
- `PolicyConditionOperator`
- `PolicyCondition`
- `PolicyRule`
- `PolicyEvaluationContext`
- `PolicyEvaluationOutcome`
- `PolicyEvaluationTraceItem`
- `PolicyEvaluationTraceOutcome`
- `GovernancePolicyEvaluator`

Notes:

- policies target ontology-aligned `DecisionTargetType` values
- rules are evaluated in ascending priority order
- every rule requires at least one structured condition
- conditions use dot-path lookup against `PolicyEvaluationContext.evidence`
- `EXISTS` and `MISSING` are the only operators that allow `expected_value=None`
- no matching rule returns `PolicyEffect.NO_DECISION`
- the evaluator does not mutate the policy or evaluation context
- `evaluate_with_trace()` returns the same final policy outcome plus
  condition-level trace data for Studio simulation
- the framework does not provide persistence, REST endpoints, MCP tools,
  evidence fetching, graph traversal, or a full governance reasoning engine

### PolicyAdministrationService

Responsibility:
Own Studio policy authoring, project-scoped policy definitions, version
lifecycle, schema metadata, and simulation over the existing evaluator.

Public imports:

- `ai_governance.PolicyAdministrationService`
- `ai_governance.services.PolicyAdministrationService`
- `ai_governance.services.policies.PolicyAdministrationService`
- `ai_governance.PolicyDefinition`
- `ai_governance.decisions.PolicyDefinition`
- `ai_governance.PolicyVersion`
- `ai_governance.decisions.PolicyVersion`
- `ai_governance.PolicyAdministrationRepository`
- `ai_governance.repositories.PolicyAdministrationRepository`
- `ai_governance.InMemoryPolicyAdministrationRepository`
- `ai_governance.repositories.InMemoryPolicyAdministrationRepository`

Notes:

- `create_policy()` creates a stable `PolicyDefinition` and initial draft
  `PolicyVersion(version="1")`
- policy names are unique within a project for the in-memory local store
- `create_policy_version()` creates a new draft version for an existing policy
- `update_draft_version()` replaces draft content only
- `activate_version()` activates a draft and deprecates any current active
  version for that policy
- `archive_version()` archives draft, deprecated, or active versions; archived
  versions cannot be activated again
- `get_policy_schema()` returns backend-owned target types, fields, operators,
  effects, statuses, categories, and severities for Studio authoring
- `simulate_version()` materializes `PolicyVersion -> GovernancePolicy` and
  evaluates with trace; the service does not execute governance decisions

### DecisionEvidenceBuilder

Responsibility:
Build read-only, decision-ready evidence from the governance ontology graph.

Public imports:

- `ai_governance.DecisionEvidenceBuilder`
- `ai_governance.decisions.DecisionEvidenceBuilder`
- `ai_governance.domain.DecisionEvidenceBuilder`

Related evidence models:

- `DecisionEvidenceGraph`
- `EvidenceNode`
- `EvidenceEdge`
- `MissingEvidence`
- `DecisionEvidenceSummary`

Notes:

- `build_for_target()` reads a bounded ontology neighbourhood for an
  ontology-aligned `DecisionTargetType`
- `summarize()` extracts sorted evidence IDs for evaluation results, metrics,
  drift analyses, leaderboards, jobs, MCP audit records, and policies
- `build_policy_context()` maps evidence into a stable
  `PolicyEvaluationContext`
- missing target, missing evaluation results, missing metrics, missing policy
  references, and result-limit truncation are represented explicitly
- outputs are deterministic for the same graph state and inputs
- the builder does not mutate graph state, persist evidence, create decisions,
  execute policies, expose REST endpoints, expose MCP tools, or implement UI

### GovernanceReasoningEngine

Responsibility:
Produce a deterministic in-memory `GovernanceDecision` from a target, evidence,
policies, and outcome-mapping rules.

Public imports:

- `ai_governance.GovernanceReasoningEngine`
- `ai_governance.decisions.GovernanceReasoningEngine`
- `ai_governance.domain.GovernanceReasoningEngine`

Related reasoning models and services:

- `GovernanceReasoningRequest`
- `GovernanceReasoningOutcome`
- `ReasoningEvidenceSummary`
- `ReasoningEvidenceSummarizer`
- `DecisionExplanation`
- `GovernancePolicyProvider`
- `InMemoryGovernancePolicyProvider`

Notes:

- `reason()` always uses `DecisionEvidenceBuilder` for evidence collection
- evidence is summarized deterministically before policy evaluation
- policies are loaded through `GovernancePolicyProvider`
- policy outcomes use fixed precedence:
  `BLOCK > REJECT > APPROVE > RECOMMEND > INVESTIGATE > NO_DECISION`
- decision confidence is derived from matched policies and missing evidence
- decision IDs are deterministic and do not include current time
- explanations are generated from policy outcomes and evidence summaries, not
  from an LLM
- the engine does not persist decisions, expose REST endpoints, expose MCP
  tools, mutate evidence, or implement human approval workflows

### GovernanceDecisionRepository

Responsibility:
Persist authoritative governance decisions, deterministic explanations, and
decision lifecycle audit records behind a storage-independent contract.

Public imports:

- `ai_governance.GovernanceDecisionRepository`
- `ai_governance.repositories.GovernanceDecisionRepository`
- `ai_governance.InMemoryGovernanceDecisionRepository`
- `ai_governance.repositories.InMemoryGovernanceDecisionRepository`
- `ai_governance.SQLiteGovernanceDecisionRepository`
- `ai_governance.repositories.SQLiteGovernanceDecisionRepository`
- `ai_governance.PostgresGovernanceDecisionRepository`
- `ai_governance.repositories.PostgresGovernanceDecisionRepository`

Related persistence models:

- `DecisionAuditAction`
- `DecisionAuditRecord`
- `DecisionExplanation`

Notes:

- `save()` inserts new decisions and allows idempotent saves of identical
  finalized decisions
- mutation of an existing finalized decision ID is rejected
- `save_with_explanation()` persists a `DecisionExplanation` alongside the
  decision
- query methods read by decision ID, target, status, provenance request ID,
  and provenance correlation ID
- `supersede()` keeps the old decision readable, marks it `SUPERSEDED`, links
  both decisions through `DecisionSupersession`, records audit, and publishes a
  superseded event when configured
- `archive()` marks a decision `ARCHIVED`, records audit, and publishes an
  archived event when configured
- repositories do not execute policies, call REST/MCP tools, perform human
  approval, or write directly to graph storage

### GovernanceDecisionApplicationService

Responsibility:
Coordinate public decision evaluation, retrieval, evidence, explanation, and
lineage workflows for REST and MCP adapters.

Public imports:

- `ai_governance.GovernanceDecisionApplicationService`
- `ai_governance.services.GovernanceDecisionApplicationService`
- `ai_governance.DecisionEvaluateCommand`
- `ai_governance.services.DecisionEvaluateCommand`

Notes:

- `evaluate()` invokes `GovernanceReasoningEngine.reason()`, persists the
  decision and `DecisionExplanation`, records a `CREATED` audit row, and
  returns the decision, explanation, evidence summary, and policy outcomes
- repeated requests with the same `request_id` and payload return the existing
  decision response where possible
- reused `request_id` or deterministic decision IDs with a different payload
  raise `DecisionConflictError`
- `get()`, `detail()`, `list()`, `evidence()`, `explanation()`, and
  `lineage()` are shared by REST and MCP-facing adapters
- `detail()` returns the persisted decision plus stored evidence summary,
  policy outcomes, and audit records for read-only inspection surfaces
- lineage delegates to `OntologyGraphQueryService`; the service does not call
  Neo4j directly, duplicate policy logic, generate LLM explanations, or
  implement human approval workflows

## Framework-Neutral APIs

### GovernanceAPI

Responsibility:
Expose governance history, latest evaluation, drift, and comparison payloads as
serializable Python values.

Notes:

- provides route metadata through `GovernanceRoute`
- depends on `EvaluationHistoryService`
- does not start a web server
- does not perform evaluation execution

### LeaderboardAPI

Responsibility:
Expose experiment leaderboard and recommendation payloads as serializable Python
values.

Notes:

- provides route metadata through `LeaderboardRoute`
- depends on the current ranking service implementation
- does not generate leaderboards during reads
- does not deploy or promote candidates

## REST Control Plane

The FastAPI control plane exposes versioned HTTP APIs under `/api/v1`.

Public REST resource groups:

- health and readiness
- API metadata and OpenAPI documentation
- providers
- prompts
- models
- datasets
- evaluations
- experiments
- jobs
- governance
- ontology graph queries

REST routers are intentionally not exported from the package root as the main
Python API surface. They are mounted through `ai_governance.api.app:create_app`.
Routers depend on DTOs, mappers, and API service facades; they do not import
repository implementations or provider adapters.

## AI Governance Control Plane Studio

The Next.js Studio in `console/` is a public operator-facing frontend over the
REST dashboard, decision, and graph query APIs. It does not expose Python
package APIs, direct Neo4j access, graph mutation, or frontend-owned ontology
semantics.

## Guided CLI

The `ai-governance` command currently provides a deliberately focused, guided product
walkthrough rather than a second operational control plane:

```bash
ai-governance walkthrough governed-replay
```

It only calls public REST endpoints to observe prompt/model evidence, select
registered data and replayable history, inspect existing evaluation and
decision evidence, prepare a replay, and open the corresponding Studio views.
It never reaches repositories, persistence backends, or governance internals.

The command writes and checkpoints a JSON run manifest containing the API
version, actual asset/execution/evaluation/decision/replay IDs, step outcomes,
and inspection URLs. `--output-json` is suitable for CI; `--submit-replay`
explicitly queues the replay job and does not imply that execution, evaluation,
comparison, or drift have completed. `ai-governance walkthrough cleanup` previews
local diagnostic manifests and requires `--apply` to remove them; it never
touches governed assets.

The CLI automatically exchanges configured `AI_GOVERNANCE_OAUTH_*` workload
credentials for a short-lived token in memory. This is a service-account
identity, not organization-admin impersonation; normal membership and RBAC
checks still apply. No bearer token export is required. `--token` is an
explicit override only; the CLI does not read `AI_GOVERNANCE_TOKEN` from the shell.

## MCP Server

Public MCP entry points:

- `AIGovernanceMCPServer`
- `create_mcp_server`

The MCP server is a stateless transport adapter over the REST control plane. It
registers read-first governance tools and delegates every tool invocation to one
REST endpoint.

## Registry Services

### PromptRegistryService

Responsibility:
Govern prompt versions, lifecycle transitions, and prompt comparisons.

### ModelRegistryService

Responsibility:
Govern model versions, lifecycle transitions, and model comparisons.

### DatasetRegistryService

Responsibility:
Govern dataset versions, lifecycle transitions, and dataset comparisons.

Dataset registry metadata is storage-independent. Dataset content can be kept
in an S3-compatible object store and referenced by the immutable dataset
version's storage URI; the local Compose stack uses SeaweedFS and production
deployments can use AWS S3.

### Evaluation Provider Registry

Responsibility:
Expose provider descriptors, capability metadata, and configuration-schema
versions for registry discovery. Provider records are part of the Assets
workspace but are not model-serving integrations.

## Experiment Services

### ExperimentService

Responsibility:
Create and manage experiment lifecycle state.

### ExperimentCandidateService

Responsibility:
Create and retrieve immutable experiment candidates that reference governed
registry assets.

### ExperimentEvaluationService

Responsibility:
Execute experiment candidates, persist evaluation runs, compare candidates, and
support winner selection workflows.

### RankingService

Responsibility:
Rank candidates using pluggable `RankingStrategy` implementations and persist
leaderboards.

## Evaluation Services

### EvaluationService

Responsibility:
Coordinate provider-backed evaluation execution.

### EvaluationWorker

Responsibility:
Run evaluation tasks as worker-oriented execution units.

### EvaluationHistoryService

Responsibility:
Retrieve historical evaluation evidence, build summaries, compare evaluations,
and support drift analysis.

## Job Services

### JobSubmissionService

Responsibility:
Submit governance jobs with validation, stable input hashing, and idempotency
enforcement.

### JobApiService

Responsibility:
Expose public job operations for REST and SDK-style callers, including submit,
lookup, filtered listing, cancellation, retry, and result reference retrieval
without exposing worker lease mutation APIs.

### JobExecutor

Responsibility:
Dispatch jobs to injectable handlers by `JobType`.

### JobWorker

Responsibility:
Acquire queued jobs through repository leases, execute them through
`JobExecutor`, and persist success or failure outcomes.

### JobRepository

Responsibility:
Persist job state, idempotency metadata, retry attempts, leases, heartbeats,
and result references.

## Repositories as Contracts

The public repository layer defines persistence contracts rather than storage
policy. Key contracts include:

- `EvaluationRepository`
- `PromptRepository`
- `ModelRepository`
- `DatasetRepository`
- `ExperimentRepository`
- `ExperimentCandidateRepository`
- `EvaluationRunRepository`
- `LeaderboardRepository`
- `JobRepository`

SQLite, PostgreSQL, Snowflake, and in-memory implementations sit behind these
contracts. Snowflake exports live under `ai_governance.databases.snowflake` and
`ai_governance.repositories.snowflake` and remain optional infrastructure concerns.

## Providers as Contracts

The provider boundary allows evaluation backends to change without rewriting
platform logic.

Current provider surface:

- `EvaluationProvider`
- TruLens implementation

Future providers should remain isolated behind the same contract.

## Related Documents

- [Architecture](../architecture/ARCHITECTURE.md)
- [Governance Ontology](../architecture/GOVERNANCE_ONTOLOGY.md)
- [Ontology Foundation](../ontology/ontology-foundation.md)
- [Ontology Synchronization](../ontology/ontology-synchronization.md)
- [Extensibility](../architecture/EXTENSIBILITY.md)
- [REST API](./REST_API.md)
- [MCP Server](./MCP_SERVER.md)
- [Governed Replay Walkthrough](../tutorials/governed-replay-walkthrough.md)
- [SQLite Schema](./SQLITE_SCHEMA.md)
- [PostgreSQL Schema](./POSTGRES_SCHEMA.md)
- [Snowflake Schema](./SNOWFLAKE_SCHEMA.md)
