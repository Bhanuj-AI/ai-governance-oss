# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog.
This project follows Semantic Versioning.

---

## [1.0.2] - 2026-08-13

### Added

- dded a privacy-preserving OSS telemetry foundation for anonymous product and workload insights.
- Added provider-neutral, versioned telemetry contracts with persistent anonymous installation identity.
- Added bounded local aggregation for product usage and performance research metrics.
- Added `ESSENTIAL`, `PRODUCT_ANALYTICS`, and `PERFORMANCE_RESEARCH` telemetry categories with configurable collection policies.
- Added privacy allow-list enforcement preventing prompts, responses, identities, tenant/project information, policies, evidence, secrets, and customer content from being exported.
- Added pluggable telemetry exporters with `None` and PostHog implementations.
- Added asynchronous delivery, bounded retries, and failure isolation so telemetry availability cannot affect platform workflows.
- Added system telemetry settings with HTTPS validation and `env://` secret references.
- Added read-only `/api/v1/telemetry/status` and `/api/v1/telemetry/preview` endpoints for operator transparency.
- Added evaluation and lifecycle-derived aggregate usage instrumentation.
- Added telemetry subsystem operational metrics for export health, failures, pending snapshots, and dropped snapshots.
- Added operator documentation covering configuration, privacy guarantees, transmitted fields, PostHog integration, and telemetry controls.

## [1.0.1] - 2026-08-12

### Added

#### Governed Asset Lifecycle
- Managed prompt creation and immutable prompt-version creation alongside
  runtime-observed prompt records, with provenance retained per asset.
- Explicit managed-model registration, immutable model versions, and lifecycle
  actions for activation, deprecation, and archival.
- Declared model runtime capability profiles, including provider/model-version
  parameter schemas and validation for OpenAI, Anthropic, and
  OpenAI-compatible runtimes.
- Studio controls for creating prompts, creating new prompt/model versions,
  registering models, filtering catalogs by provenance, and selecting only
  active governed asset versions for experiment candidates.

#### Runtime Connections
- Tenant-scoped Runtime Connections as first-class operational resources,
  separate from deployment-level integrations and immutable model definitions.
- Secret-reference based OpenAI, Anthropic, and OpenAI-compatible connection
  configurations with provider policy enforcement, validation/test state, and
  Studio management under **Settings → Runtime Connections**.
- Runtime Connection REST API and a configuration tutorial covering secure
  setup, credential rotation, scope, and experiment use.

#### Candidate Execution and Evaluation Evidence
- Candidate Execution Runtime that renders managed prompts, reads immutable
  dataset items, invokes the registered model through its Runtime Connection,
  and persists secret-free workflow execution evidence before evaluation.
- Provider runtime adapter SPI with OpenAI support and execution telemetry for
  provider request ID, latency, token usage, finish reason, and failures.
- Per-item evaluation-result persistence and paginated REST retrieval,
  including model API latency and retained completed results when a run fails
  or is cancelled.
- Experiment cancellation, item execution progress, and structured lifecycle
  events for candidate execution.

#### Observability and Studio
- Structured, secret-safe candidate execution logs correlated by experiment,
  candidate, run, and execution identifiers.
- Evaluation Runs view with configurable automatic refresh, durable item-result
  table, pagination, model API latency, cancellation state, and resizable run
  summary columns.
- A reusable `model-runtime-capability-profile` skill for adding declared
  provider/model capability schemas.

### Changed

- Prompt and model catalogs now represent declared/managed and
  runtime-observed records together instead of treating observation as the
  only registry lifecycle.
- Experiment evaluation now uses the exact persisted candidate execution
  evidence; evaluators no longer reconstruct candidate configuration or score
  a synthetic empty answer.
- Candidate comparison requires the same immutable dataset identity and
  version across all candidates.
- Prompt, model, Runtime Connection, and evaluation-result reads and writes
  carry explicit tenant context rather than silently using default scope.

### Fixed

- Hardened filesystem-backed dataset object storage against path traversal,
  absolute-path, and symlink-escape attempts.
- Reconciled cancelled experiments so stale child runs do not remain shown as
  running.
- Improved runtime failure reporting for unavailable dataset content,
  incompatible/inactive connections, unsupported parameters, and unresolved
  provider model identifiers.

## [1.0.0] - 2026-08-08

### Added

#### Governance
- Governance Decision Engine
- Governance Ontology
- Policy Engine
- Evidence Graphs
- Decision Lineage

#### AI Asset Management
- Prompt Registry
- Model Registry
- Dataset Registry
- Immutable Versioning

#### Evaluation
- Experiment Management
- Evaluation Framework
- Candidate Comparison
- Drift Analysis

#### Replay
- Workflow Replay
- Execution Audit
- Replay-aware Governance

#### Platform
- REST API
- MCP Server
- Kavach Studio
- SQLite & PostgreSQL persistence
- Neo4j ontology support
- SeaweedFS/S3 dataset storage
- Plugin extension framework
