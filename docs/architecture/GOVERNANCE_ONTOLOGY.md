# Governance Ontology

## Status

- Ontology name: `ai_governance.governance`
- Ontology version: `1.0.0`
- Stability: accepted semantic contract
- Applies to: REST APIs, MCP tools, governance intelligence, repositories, and future graph projections
- Storage dependency: none

This document defines the versioned governance ontology for AI Governance Control Plane. The
ontology is the canonical semantic model for governed AI assets, evaluation
evidence, experiment decisions, jobs, replay investigation, drift analysis, and
MCP write audit records.

The ontology is intentionally independent of a graph database, relational
schema, API transport, or UI. Storage engines project the ontology; they do not
define it.

## Ontology Philosophy

The ontology is the authoritative business model of AI Governance Control Plane; all storage models, APIs, graph projections, UI views, and AI reasoning are derived representations.

## Design Principles

- Governance objects have stable identity and explicit lifecycle state.
- Versioned assets are immutable once created.
- Mutable governance state is represented through lifecycle transitions,
  decisions, jobs, events, and audit records rather than in-place semantic
  rewrites.
- Relationships are directed and named from source to target.
- Relationships describe durable semantics. Events describe temporal facts.
- Actions are first-class governance concepts, even when currently exposed as
  REST endpoints, MCP tools, service methods, or worker jobs.
- Future graph traversal must be deterministic from the relationship taxonomy
  without transport-specific interpretation.

## Naming Conventions

- Entity names use `UpperCamelCase`.
- Relationship names use uppercase snake case verbs or verb phrases.
- Action names use imperative `UpperCamelCase`.
- Event names use past-tense `UpperCamelCase`.
- Entity identifiers use stable opaque IDs from the owning service where
  available.
- Version strings are semantic labels owned by the producing registry or
  provider. The ontology does not require SemVer for asset versions.
- Relationship direction is always read as `Source RELATIONSHIP Target`.

## Common Entity Semantics

Every first-class entity has these semantic attributes unless explicitly noted:

- identity: stable ID within the entity type
- owner: actor, service, provider, or external system responsible for the
  entity
- lifecycle: current lifecycle state or immutable snapshot state
- created_at: timestamp when the entity was created or observed
- immutable_attributes: attributes that must not change after creation
- mutable_attributes: attributes that may change through governed transitions
- versioning_rule: whether the entity is versioned, immutable, or derived

## Entity Taxonomy

### Actor

- Identity: `actor_id`
- Ownership: external identity provider, human operator, service account, or
  MCP agent
- Lifecycle: active, disabled, unknown
- Immutable attributes: `actor_id`, `actor_type`
- Mutable attributes: display metadata
- Versioning rules: not versioned; identity changes create a new actor
- Current projection: `submitted_by`, `created_by`, `creator`, MCP
  `actor_id`, and MCP `actor_type`

### Prompt

- Identity: logical prompt identity, normally derived from a stable prompt
  family or name
- Ownership: prompt registry owner or creator
- Lifecycle: draft, active, deprecated, archived, derived from active versions
- Immutable attributes: logical identity
- Mutable attributes: current active version pointer, lifecycle summary
- Versioning rules: a Prompt is a logical family; changes to content create a
  PromptVersion
- Current projection: grouped from prompt registry records by stable prompt
  family semantics

### PromptVersion

- Identity: `prompt_id` plus `version`, or a registry-provided version ID
- Ownership: `created_by`
- Lifecycle: `DRAFT`, `ACTIVE`, `DEPRECATED`, `ARCHIVED`
- Immutable attributes: `prompt_id`, `name`, `version`, `template`,
  `variables`, `created_at`, `created_by`
- Mutable attributes: lifecycle status only
- Versioning rules: prompt text or variable changes create a new PromptVersion
- Current projection: `Prompt`

### Model

- Identity: logical model identity, normally provider plus model family/name
- Ownership: model registry owner or provider steward
- Lifecycle: draft, active, deprecated, archived, derived from active versions
- Immutable attributes: logical identity, provider family
- Mutable attributes: current active version pointer, lifecycle summary
- Versioning rules: model metadata changes that affect reproducibility create a
  ModelVersion
- Current projection: grouped from model registry records by provider and
  model family semantics

### ModelVersion

- Identity: `model_id` plus `version`, or a registry-provided version ID
- Ownership: `creator`
- Lifecycle: `DRAFT`, `ACTIVE`, `DEPRECATED`, `ARCHIVED`
- Immutable attributes: `model_id`, `provider`, `model_name`, `version`,
  `parameters`, `cost`, `latency`, `context_window`, `creator`, `created_at`
- Mutable attributes: lifecycle status only
- Versioning rules: provider, model version, parameter, context, cost, or
  latency changes create a new ModelVersion
- Current projection: `Model`

### Dataset

- Identity: logical dataset identity, normally dataset family or name
- Ownership: dataset registry owner or creator
- Lifecycle: draft, active, frozen, deprecated, archived, derived from active
  versions
- Immutable attributes: logical identity
- Mutable attributes: current active/frozen version pointer, lifecycle summary
- Versioning rules: governed data, schema, checksum, or storage-location
  changes create a DatasetVersion
- Current projection: grouped from dataset registry records by stable dataset
  family semantics

### DatasetVersion

- Identity: `dataset_id` plus `version`, or a registry-provided version ID
- Ownership: `creator`
- Lifecycle: `DRAFT`, `ACTIVE`, `FROZEN`, `DEPRECATED`, `ARCHIVED`
- Immutable attributes: `dataset_id`, `name`, `version`, `description`,
  `storage_uri`, `storage_type`, `schema_version`, `record_count`, `checksum`,
  `creator`, `created_at`
- Mutable attributes: lifecycle status only
- Versioning rules: dataset content, schema, checksum, or storage metadata
  changes create a new DatasetVersion
- Current projection: `Dataset`

### EvaluationProvider

- Identity: provider name plus provider version
- Ownership: provider adapter owner
- Lifecycle: registered, available, unavailable, deprecated
- Immutable attributes: provider name, capability names, descriptor snapshot
  version when referenced by evaluation evidence
- Mutable attributes: availability and registration metadata
- Versioning rules: provider descriptor snapshots on EvaluationResult are
  immutable evidence; provider registry entries may evolve
- Current projection: provider descriptors and evaluation provider adapters

### Experiment

- Identity: `experiment_id`
- Ownership: `owner`
- Lifecycle: `DRAFT`, `RUNNING`, `COMPLETED`, `FAILED`, `ARCHIVED`
- Immutable attributes: `experiment_id`, `name`, `description`, `owner`,
  `created_at`
- Mutable attributes: lifecycle status
- Versioning rules: not versioned; material scope changes should create a new
  experiment or new candidates
- Current projection: `Experiment`

### Candidate

- Identity: `candidate_id`
- Ownership: parent Experiment owner
- Lifecycle: immutable after creation; effective states are pending,
  evaluated, ranked, archived with parent experiment
- Immutable attributes: `candidate_id`, `experiment_id`, `name`, prompt
  reference, model reference, dataset reference, `evaluation_provider`,
  `temperature`, `top_p`, `max_tokens`, metadata, `created_at`
- Mutable attributes: none
- Versioning rules: configuration changes create a new Candidate
- Current projection: `ExperimentCandidate`

### EvaluationRun

- Identity: `run_id`
- Ownership: experiment service, evaluation service, or job executor
- Lifecycle: `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`
- Immutable attributes: `run_id`, `experiment_id`, `candidate_id`,
  `dataset_version`, `evaluation_provider`
- Mutable attributes: status, `started_at`, `completed_at`,
  `evaluation_result_id`
- Versioning rules: not versioned; each execution attempt is a new run
- Current projection: `EvaluationRun`

### EvaluationResult

- Identity: `evaluation_id`
- Ownership: evaluation service and provider
- Lifecycle: immutable evidence snapshot
- Immutable attributes: `evaluation_id`, `execution_id`, `evaluator_type`,
  `evaluator_version`, metrics, artifacts, provider metadata, provider
  descriptor snapshot, `created_at`
- Mutable attributes: none
- Versioning rules: not versioned; new evaluation output creates a new result
- Current projection: `EvaluationResult`

### Metric

- Identity: metric name within an EvaluationResult or provider descriptor
- Ownership: evaluation provider
- Lifecycle: immutable when recorded on an EvaluationResult
- Immutable attributes: metric name, metric value, explanation, provider
  interpretation
- Mutable attributes: none
- Versioning rules: provider-level metric definition changes are provider
  version changes; result-level metric values are immutable
- Current projection: `EvaluationMetric`

### EvaluationArtifact

- Identity: artifact identity or URI within an EvaluationResult
- Ownership: evaluation provider or storage owner
- Lifecycle: immutable evidence reference
- Immutable attributes: artifact type, URI, payload, metadata as recorded
- Mutable attributes: none in the ontology; underlying external object
  retention is outside AI Governance Control Plane
- Versioning rules: changed artifact content creates a new artifact reference
- Current projection: `EvaluationArtifact`

### EvaluationHistory

- Identity: execution ID, experiment ID, candidate ID, or query scope plus
  retrieval timestamp
- Ownership: history service
- Lifecycle: derived read model
- Immutable attributes: query scope for the read
- Mutable attributes: none; regenerated from evaluation evidence
- Versioning rules: not versioned; history records are projections over
  EvaluationResult objects
- Current projection: `EvaluationHistory`

### EvaluationComparison

- Identity: baseline evaluation ID plus candidate evaluation ID
- Ownership: governance/history service
- Lifecycle: derived governance evidence
- Immutable attributes: baseline evaluation ID, candidate evaluation ID,
  metric comparisons, generated comparison values
- Mutable attributes: none
- Versioning rules: regenerate if comparison algorithm version changes; retain
  old output when used as decision evidence
- Current projection: `EvaluationComparison`

### DriftAnalysis

- Identity: baseline evaluation ID plus candidate evaluation ID plus analyzer
  version
- Ownership: governance plane
- Lifecycle: derived governance evidence
- Immutable attributes: compared evaluation IDs, score difference, changed
  metrics, new metrics, removed metrics, severity
- Mutable attributes: none
- Versioning rules: new analyzer semantics produce a new DriftAnalysis
- Current projection: `EvaluationDrift`

### Leaderboard

- Identity: `leaderboard_id`
- Ownership: ranking service
- Lifecycle: immutable ranking snapshot
- Immutable attributes: `leaderboard_id`, `experiment_id`,
  `ranking_strategy`, `generated_at`, ordered entries
- Mutable attributes: none
- Versioning rules: reranking creates a new Leaderboard
- Current projection: `Leaderboard`

### LeaderboardEntry

- Identity: leaderboard ID plus rank or candidate ID
- Ownership: parent Leaderboard
- Lifecycle: immutable ranking evidence
- Immutable attributes: rank, candidate ID, overall score, metrics, cost,
  latency, reason
- Mutable attributes: none
- Versioning rules: changed ranking output creates a new LeaderboardEntry in a
  new Leaderboard
- Current projection: `LeaderboardEntry`

### GovernanceDecision

![AI Governance Control Plane Governance Decision](../../assets/Governance%20Decisions.png)

- Identity: decision ID
- Ownership: approving actor, governance service, or external policy system
- Lifecycle: proposed, approved, rejected, blocked, superseded, archived
- Immutable attributes: decision ID, decision type, target entity, evidence
  references, policy references, reason, confidence, provenance, created_at,
  finalized_at, archived_at, supersession references
- Mutable attributes: lifecycle status until finalized
- Versioning rules: finalized decisions are immutable; changed decisions
  supersede prior decisions
- Current projection: `GovernanceDecision`
- Domain contract: `ai_governance.decisions.GovernanceDecision` with value objects for
  target, evidence reference, policy reference, provenance, and supersession
- Supported decision types: `APPROVE`, `REJECT`, `BLOCK`, `RECOMMEND`,
  `PROMOTE`, `ARCHIVE`, `INVESTIGATE`
- Supported target types: `Candidate`, `Experiment`, `PromptVersion`,
  `ModelVersion`, `DatasetVersion`, `EvaluationRun`, `EvaluationResult`,
  `Job`, and `GovernanceDecision`
- Validation rules: decision ID and reason are required; at least one evidence
  reference is required; target IDs, policy references, evidence references,
  producer IDs, and supersession references cannot be blank; provenance
  timestamps are timezone-aware; a decision cannot supersede itself
- Evidence preparation: `DecisionEvidenceBuilder` reads bounded ontology
  neighbourhoods for decision targets and returns `DecisionEvidenceGraph`,
  `DecisionEvidenceSummary`, and `PolicyEvaluationContext` projections without
  mutating graph state or creating decisions
- Evidence completeness: missing target, evaluation result, metric, policy
  reference, and result-limit evidence are represented as `MissingEvidence`
  entries with `INFO`, `WARNING`, or `CRITICAL` severity
- Reasoning: `GovernanceReasoningEngine` combines evidence building,
  deterministic evidence summarization, policy evaluation, outcome precedence,
  confidence mapping, decision construction, and `DecisionExplanation`
  generation without persistence, transport APIs, MCP tools, UI behavior, or
  LLM-generated text
- Persistence: `GovernanceDecisionRepository` stores decisions, optional
  deterministic explanations, and append-only `DecisionAuditRecord` rows in
  SQLite or PostgreSQL; finalized decisions are idempotent but immutable, and
  superseded decisions remain readable
- Lifecycle events: repository implementations can publish
  `GovernanceDecisionCreated`, `GovernanceDecisionSuperseded`, and
  `GovernanceDecisionArchived` ontology synchronization events when configured
- Ontology projection: `GovernanceDecisionOntologySynchronizer` projects
  `DECIDES_ON`, `GENERATED_FROM`, `GOVERNED_BY`, `APPROVED_BY`,
  `REJECTED_BY`, `BLOCKED_BY`, and `SUPERSEDES` relationships through
  `OntologyService`; repositories never write graph state directly

### Policy

- Identity: stable policy ID plus immutable policy version
- Ownership: governance administrators; REST authoring is project-scoped through
  `PolicyDefinition`
- Lifecycle: draft, active, deprecated, archived
- Immutable version attributes after activation: version, target types, policy
  rules, rule conditions, effects, reason templates, priorities, created_at,
  created_by
- Mutable definition attributes: name, description, owner, metadata, updated_at
  through administration workflows
- Versioning rules: rule changes create a new Policy version
- Current execution projection: `PolicyVersion -> GovernancePolicy`
- Domain contract: `ai_governance.decisions.GovernancePolicy` with structured
  `PolicyRule`, `PolicyCondition`, `PolicyEvaluationContext`, and
  `PolicyEvaluationOutcome` value objects
- Administration contract: `PolicyAdministrationService` owns create, draft
  update, version creation, activation, archive, listing, schema, and
  simulation workflows without making the reasoning engine depend on Studio
  DTOs
- Supported policy effects: `APPROVE`, `REJECT`, `BLOCK`, `RECOMMEND`,
  `INVESTIGATE`, `NO_DECISION`
- Supported condition operators: `GREATER_THAN`,
  `GREATER_THAN_OR_EQUAL`, `LESS_THAN`, `LESS_THAN_OR_EQUAL`, `EQUALS`,
  `NOT_EQUALS`, `IN`, `NOT_IN`, `EXISTS`, `MISSING`
- Evaluation rules: rules are evaluated by ascending priority; all conditions
  in a rule must match; first matching rule wins; missing field paths only
  match `MISSING`; no matching rule returns `NO_DECISION`
- Simulation rules: Studio simulation uses
  `GovernancePolicyEvaluator.evaluate_with_trace()` and returns matched
  conditions, unmatched conditions, and condition-level trace items
- Boundary: the policy framework evaluates supplied evidence context only; it
  does not fetch evidence, traverse the graph, persist governance decisions,
  perform RBAC, or implement human approval workflows

### Job

- Identity: `job_id`
- Ownership: `submitted_by` and job control plane
- Lifecycle: `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `CANCELLED`
- Immutable attributes: `job_id`, `job_type`, `input_refs`, `input_hash`,
  `idempotency_key`, `submitted_by`, `max_attempts`, `created_at`
- Mutable attributes: status, attempt count, result reference, failure reason,
  lease metadata, heartbeat, timestamps
- Versioning rules: not versioned; retries mutate job execution state while
  preserving input identity
- Current projection: `Job`

### MCPAuditRecord

- Identity: `audit_id`
- Ownership: MCP server and invoking actor
- Lifecycle: started, succeeded, failed, dry-run completed, cancelled
- Immutable attributes: audit ID, request ID, correlation ID, tool name,
  tool version, actor/client metadata, idempotency key, operation type,
  request hash, request summary, resolved versions, reason, dry-run flag,
  started_at
- Mutable attributes: status, resource ID, job ID, result reference, error
  fields, completed_at, duration, metadata
- Versioning rules: audit record identity is stable; status updates complete
  the same record
- Current projection: `MCPExecutionAuditRecord`

### WorkflowExecution

- Identity: `execution_id`
- Ownership: runtime edge or replay plane
- Lifecycle: completed, failed, cancelled, reconstructed
- Immutable attributes: workflow ID, execution ID, workflow name, workflow
  version, execution status, input, final state, ordered events
- Mutable attributes: none once reconstructed
- Versioning rules: each runtime execution creates a new WorkflowExecution;
  replay does not rewrite the original execution
- Current projection: `WorkflowExecution`

### ReplayInvestigation

- Identity: replay request ID or execution ID plus investigation timestamp
- Ownership: replay/investigation service
- Lifecycle: requested, reconstructed, completed, failed
- Immutable attributes: target execution ID, query scope, reconstructed
  evidence references
- Mutable attributes: status and investigation annotations until completed
- Versioning rules: each replay investigation is a new entity
- Current projection: `ReplayRequest`, `ReplayEvaluationHistory`, and
  investigation services

### GovernanceInsight

- Identity: insight ID or deterministic evidence scope plus generated timestamp
- Ownership: governance intelligence services
- Lifecycle: generated, reviewed, archived
- Immutable attributes: insight type, severity, message, evidence references,
  generated_at
- Mutable attributes: review status and reviewer annotations
- Versioning rules: regenerated insight output is a new insight
- Current projection: `GovernanceInsight`

### GovernanceReport

- Identity: report ID or deterministic report scope plus generated timestamp
- Ownership: governance reporting service
- Lifecycle: generated, delivered, archived
- Immutable attributes: report scope, format, evidence references, generated
  insights, generated_at
- Mutable attributes: delivery status and archival metadata
- Versioning rules: regenerated report output is a new report
- Current projection: `GovernanceReport`

## Relationship Taxonomy

![AI Governance Control Plane Ontology Graph](../../assets/AI Governance Control Plane%20Ontology%20Graph.png)

All relationships are directed. Cardinality is stated from source to target.

| Relationship | Source | Target | Cardinality | Lifecycle | Constraints |
| --- | --- | --- | --- | --- | --- |
| `HAS_VERSION` | Prompt | PromptVersion | 1 to many | Durable | Target belongs to exactly one logical Prompt. |
| `VERSION_OF` | PromptVersion | Prompt | many to 1 | Durable | Inverse of `HAS_VERSION`. |
| `HAS_VERSION` | Model | ModelVersion | 1 to many | Durable | Target belongs to exactly one logical Model. |
| `VERSION_OF` | ModelVersion | Model | many to 1 | Durable | Inverse of `HAS_VERSION`. |
| `HAS_VERSION` | Dataset | DatasetVersion | 1 to many | Durable | Target belongs to exactly one logical Dataset. |
| `VERSION_OF` | DatasetVersion | Dataset | many to 1 | Durable | Inverse of `HAS_VERSION`. |
| `SUPERSEDES` | PromptVersion, ModelVersion, DatasetVersion, GovernanceDecision, Policy | Same entity type | 0 or 1 to 1 | Durable | Source and target must share logical family or decision scope. |
| `OWNED_BY` | Governed entity | Actor | many to 1 | Durable | Every non-derived governed entity should resolve to an owner when known. |
| `CREATED_BY` | Governed entity | Actor | many to 1 | Durable | Captures provenance of creation. |
| `HAS_CANDIDATE` | Experiment | Candidate | 1 to many | Durable | Candidate must reference the same `experiment_id`. |
| `PARTICIPATES_IN` | Candidate | Experiment | many to 1 | Durable | Candidate belongs to exactly one Experiment. |
| `USES` | Candidate | PromptVersion | many to 1 | Durable | Candidate must bind exactly one prompt version. |
| `USES` | Candidate | ModelVersion | many to 1 | Durable | Candidate must bind exactly one model version. |
| `USES` | Candidate | DatasetVersion | many to 1 | Durable | Candidate must bind exactly one dataset version. |
| `EVALUATED_BY` | Candidate, EvaluationRun, EvaluationResult | EvaluationProvider | many to 1 | Durable | Provider identity and version must be reproducible from evidence. |
| `HAS_RUN` | Experiment | EvaluationRun | 1 to many | Durable | Run must reference the parent experiment. |
| `EXECUTES` | EvaluationRun | Candidate | many to 1 | Durable | Run evaluates exactly one candidate. |
| `PRODUCES` | EvaluationRun; Replay | EvaluationRun -> EvaluationResult; Replay -> WorkflowExecution, EvaluationResult, EvaluationComparison | Source-specific | Durable after completion | Completed runs produce one EvaluationResult; a Replay records its reconstructed execution and derived evaluation evidence. |
| `HAS_METRIC` | EvaluationResult | Metric | 1 to many | Durable | Metrics are immutable within the result. |
| `HAS_ARTIFACT` | EvaluationResult | EvaluationArtifact | 0 to many | Durable | Artifacts are evidence references. |
| `RECORDED_IN` | EvaluationResult | EvaluationHistory | many to many | Derived | History is a projection over persisted results. |
| `COMPARED_WITH` | EvaluationResult | EvaluationResult | many to many | Derived or durable when persisted | Direction is baseline to candidate. |
| `GENERATES` | EvaluationComparison | Metric | 1 to many | Durable when persisted | Metric comparison output must name the metric and values. |
| `CAUSED_DRIFT` | EvaluationComparison, Replay | DriftAnalysis | Source-specific | Durable when materialized | Drift analysis must identify baseline and candidate evidence. |
| `RANKED_BY` | Candidate | Leaderboard | many to many | Durable | Candidate appears through a LeaderboardEntry. |
| `HAS_ENTRY` | Leaderboard | LeaderboardEntry | 1 to many | Durable | Entries must have consecutive ranks starting at 1. |
| `RANKS` | LeaderboardEntry | Candidate | many to 1 | Durable | Entry must reference exactly one Candidate. |
| `RECOMMENDS` | Leaderboard, GovernanceInsight | Candidate | 0 or 1 to many | Derived or durable when accepted | Recommendation must carry evidence and reason. |
| `GENERATED_FROM` | Job; Leaderboard; GovernanceInsight/Report; GovernanceDecision; Replay | Job inputs: EvaluationResult, EvaluationRun, Leaderboard, DriftAnalysis, GovernanceReport; Leaderboard: EvaluationRun; Insight/Report: EvaluationResult, EvaluationRun, Job, Candidate, Experiment, MCPAuditRecord; Decision: EvaluationResult, Metric, DriftAnalysis, Leaderboard, Job, MCPAuditRecord, Policy; Replay: EvaluationResult | many to many | Durable | Source-specific evidence contract. This prevents invalid broad pairs while retaining decision metric and policy provenance. |
| `DECIDES_ON` | GovernanceDecision | Candidate, Experiment, PromptVersion, ModelVersion, DatasetVersion, EvaluationRun, EvaluationResult, Job, GovernanceDecision | many to 1 | Durable | Decision target must be an ontology entity. |
| `APPROVED_BY` | GovernanceDecision | Actor | many to 1 | Durable | Required for approved decisions. |
| `REJECTED_BY` | GovernanceDecision | Actor | many to 1 | Durable | Required for rejected decisions. |
| `BLOCKED_BY` | Candidate, Experiment, Job, GovernanceDecision | Policy, GovernanceDecision, DriftAnalysis | many to many | Durable while active | Block reason must be traceable to evidence or policy. |
| `GOVERNED_BY` | Entity, Action | Policy | many to many | Durable | Policy version must be explicit when enforced. |
| `SUBMITTED_AS` | Action | Job | 0 or 1 to 1 | Durable | Long-running actions may have one job per submission. |
| `RESULTED_IN` | Job, Replay | Job: EvaluationResult, EvaluationRun, Leaderboard, DriftAnalysis, GovernanceReport; Replay: ReplayResult | 0 or 1 to many | Durable after success | Result reference must resolve to target evidence. |
| `AUDITED_BY` | Action, Job, REST/MCP write request | MCPAuditRecord | 0 or 1 to many | Durable | MCP write actions must be audited. |
| `REFERENCES_RESOURCE` | MCPAuditRecord | PromptVersion, ModelVersion, DatasetVersion, Experiment, Candidate, EvaluationRun, Job | many to many | Durable | Resolved versions should be stored for reproducibility. |
| `REPLAY_OF` | ReplayInvestigation, Replay | ReplayInvestigation: WorkflowExecution, EvaluationResult, Job; Replay: WorkflowExecution | many to 1 | Durable | Replay target must be immutable or reconstructable evidence. |
| `RECONSTRUCTS` | ReplayInvestigation | WorkflowExecution | 1 to 1 | Durable | Reconstructed execution must preserve original execution ID. |
| `OBSERVED_BY` | WorkflowExecution | EvaluationResult | 1 to many | Durable | EvaluationResult `execution_id` must match WorkflowExecution. |
| `INVESTIGATES` | ReplayInvestigation, GovernanceInsight | MCPAuditRecord, Job, EvaluationResult, DriftAnalysis | many to many | Durable | Investigation evidence must remain traceable. |

## Action Taxonomy

Actions are semantic governance operations. A transport may expose an action as
a REST endpoint, MCP tool, service method, worker job, or future UI command.

| Action | Primary targets | Produces | Constraints |
| --- | --- | --- | --- |
| `Register` | PromptVersion, ModelVersion, DatasetVersion, EvaluationProvider | Created entity, `Created` event | Versioned assets must include owner and immutable reproducibility metadata. |
| `Activate` | PromptVersion, ModelVersion, DatasetVersion, Policy | `Activated` event | Only one active version per configured logical scope unless policy allows many. |
| `Deprecate` | PromptVersion, ModelVersion, DatasetVersion, Policy | `Deprecated` event | Deprecated entities remain readable and traversable. |
| `Archive` | PromptVersion, ModelVersion, DatasetVersion, Experiment, Job, GovernanceInsight, GovernanceReport | `Archived` event | Archived entities cannot be selected for new candidates unless explicitly allowed. |
| `CreateExperiment` | Experiment | Experiment, `Created` event | Owner is required. |
| `AddCandidate` | Experiment | Candidate, `Created` event | Candidate must bind prompt, model, dataset, and provider versions. |
| `Evaluate` | Candidate, WorkflowExecution | EvaluationRun, EvaluationResult, metrics, artifacts | Evaluation provider and dataset version must be explicit. |
| `SubmitJob` | Long-running action | Job | Idempotency key and input hash are required. |
| `CancelJob` | Job | `Cancelled` event | Terminal jobs cannot be cancelled. |
| `RetryJob` | Job | Updated Job, new attempt events | Retry preserves original input hash. |
| `Replay` | WorkflowExecution, EvaluationResult, Job | ReplayInvestigation, reconstructed history | Replay must not mutate original evidence. |
| `Compare` | EvaluationResult, Candidate, PromptVersion, ModelVersion, DatasetVersion | EvaluationComparison or domain diff | Baseline and candidate direction must be explicit. |
| `AnalyzeDrift` | EvaluationComparison, EvaluationResult pair | DriftAnalysis | Analyzer version or threshold policy must be knowable. |
| `Rank` | Experiment, Candidate set, EvaluationRun set | Leaderboard, LeaderboardEntry | Ranking strategy must be explicit. |
| `SelectWinner` | Leaderboard, Candidate | GovernanceDecision or recommendation | Evidence and reason are required. |
| `Approve` | GovernanceDecision, Candidate, Policy, versioned asset | Approved decision, `Approved` event | Approving actor is required. |
| `Reject` | GovernanceDecision, Candidate, Policy, versioned asset | Rejected decision, `Rejected` event | Rejecting actor and reason are required. |
| `Promote` | Candidate, PromptVersion, ModelVersion, DatasetVersion | GovernanceDecision, possible activation event | Promotion must reference evaluation or policy evidence. |
| `Investigate` | Job, MCPAuditRecord, EvaluationResult, DriftAnalysis, WorkflowExecution | ReplayInvestigation or GovernanceInsight | Evidence scope must be stable and replayable. |
| `ProduceReport` | Experiment, EvaluationResult, DriftAnalysis, ReplayInvestigation | GovernanceReport | Report must list evidence references. |
| `AuditWrite` | MCP write action | MCPAuditRecord | Request hash, actor, reason, and resolved versions are required. |

## Event Taxonomy

Events provide temporal context and must not replace relationships. Events may
be emitted by services, repositories, jobs, MCP tools, or future graph
synchronizers.

| Event | Applies to | Required context |
| --- | --- | --- |
| `Created` | All first-class entities | Entity ID, actor or service, timestamp |
| `Updated` | Mutable lifecycle/read models | Entity ID, changed fields, actor or service, timestamp |
| `Activated` | Versioned assets, Policy | Entity ID, previous active version when applicable |
| `Deprecated` | Versioned assets, Policy | Entity ID, reason |
| `Archived` | Versioned assets, Experiment, Job, GovernanceInsight, GovernanceReport | Entity ID, reason |
| `EvaluationStarted` | EvaluationRun, Job | Run ID, candidate ID, provider, timestamp |
| `EvaluationCompleted` | EvaluationRun, EvaluationResult | Run ID, result ID, provider, timestamp |
| `EvaluationFailed` | EvaluationRun, Job | Run ID or job ID, failure reason |
| `DecisionProduced` | GovernanceDecision, Leaderboard, GovernanceInsight | Decision/evidence ID, target entity, reason |
| `ReplayStarted` | ReplayInvestigation | Target execution or evidence ID |
| `ReplayCompleted` | ReplayInvestigation, WorkflowExecution | Reconstructed execution ID and evidence references |
| `ReplayFailed` | ReplayInvestigation | Target ID and failure reason |
| `DriftDetected` | DriftAnalysis | Baseline ID, candidate ID, severity |
| `JobQueued` | Job | Job ID, type, idempotency key |
| `JobStarted` | Job | Job ID, attempt, worker identity |
| `JobSucceeded` | Job | Job ID, result references |
| `JobFailed` | Job | Job ID, attempt, failure reason |
| `JobCancelled` | Job | Job ID, actor or service |
| `MCPAuditStarted` | MCPAuditRecord | Audit ID, request ID, correlation ID, tool |
| `MCPAuditCompleted` | MCPAuditRecord | Audit ID, status, resource/job/result references |
| `MCPAuditFailed` | MCPAuditRecord | Audit ID, error code, error message |
| `ReportGenerated` | GovernanceReport | Report scope and evidence references |

## Ontology Versioning

The ontology version follows SemVer:

- Patch changes clarify wording or add non-normative examples.
- Minor changes add optional entities, relationships, attributes, actions, or
  events without changing existing semantics.
- Major changes rename or remove entities, relationships, required fields, or
  lifecycle meanings.

Compatibility rules:

- Existing entity and relationship names remain valid for the full major
  version.
- Deprecated concepts must remain documented with replacement guidance for at
  least one major version.
- Consumers may negotiate by major version. A `1.x` consumer can reject a
  `2.x` ontology.
- Additive minor-version concepts must not be required by existing `1.x`
  consumers unless a transport declares a newer minimum ontology version.
- Stored evidence must retain the ontology version used when the evidence was
  produced if that evidence is serialized outside internal repository models.

Migration guidelines:

- Do not rewrite immutable evidence to satisfy ontology changes.
- Add projection logic for new relationships before removing old projections.
- Use `SUPERSEDES` for decision, policy, and version lineage.
- Preserve old relationship names as aliases during a major-version migration
  when feasible.
- Migration documents must state source version, target version, affected
  entities, affected relationships, and replay implications.

## Ontology Governance

Ownership:

- The AI Governance Control Plane maintainers own the ontology.
- Domain service owners own the projection of their domain objects into the
  ontology.
- Storage implementations own persistence mechanics only.

Review rules:

- New first-class governance concepts require an ontology update before API,
  MCP, or storage-specific implementation.
- New relationships must define source, target, direction, cardinality,
  lifecycle, and constraints.
- New actions must identify target entities, produced evidence, and audit
  requirements.
- New events must identify required context and must not duplicate durable
  relationship semantics.
- Breaking changes require a major ontology version and migration guidance.

Documentation requirements:

- Every entity must document identity, ownership, lifecycle, immutable
  attributes, mutable attributes, and versioning rules.
- Every relationship must be discoverable from the relationship taxonomy.
- Every transport-facing feature must map to actions and entities in this
  document or explicitly state that it is outside governance semantics.

Approval process:

1. Propose ontology changes in an architecture document or design epic.
2. Review affected domain services, REST APIs, MCP tools, repository
   projections, and governance intelligence.
3. Add migration notes for persisted or serialized evidence.
4. Update tests or smoke checks that depend on changed public semantics.
5. Merge only after the semantic contract and implementation projection agree.

## Current Capability Coverage

The ontology covers the current AI Governance Control Plane capabilities:

- prompt, model, and dataset registries with versioning, lifecycle management,
  and diffing
- provider-backed evaluation results, metrics, artifacts, and history
- experiment lifecycle management, candidates, evaluation runs, comparisons,
  ranking, leaderboards, recommendations, and winner selection
- governance comparison, drift analysis, insights, and reports
- workflow execution replay and replay-aware investigation
- asynchronous governance jobs, idempotency, retries, cancellation, and result
  references
- REST and MCP control-plane operations
- MCP write-operation audit records with actor, request, correlation,
  idempotency, resolved-version, and result provenance

## Out of Scope

This ontology version does not implement:

- graph database storage
- graph synchronization
- graph traversal APIs
- REST or MCP endpoint changes
- Studio visualization
- LLM reasoning over the ontology
- external deployment or CI/CD promotion systems

Those systems may consume this ontology, but they remain implementation
concerns outside this document.
