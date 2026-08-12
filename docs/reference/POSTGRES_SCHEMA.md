# PostgreSQL Schema

## Overview

PostgreSQL is AI Governance Control Plane's production reference persistence backend. It implements
the same repository contracts as SQLite and in-memory repositories, so services
remain storage-independent.

The PostgreSQL schema mirrors the SQLite schema semantically while using
PostgreSQL-native types where useful:

- `TIMESTAMPTZ` for persisted timestamps
- `JSONB` for structured metadata and configuration fields
- `DOUBLE PRECISION` for scores, cost, latency, and runtime parameters
- explicit primary keys, unique constraints, and indexes

Schema initialization is intentionally simple and uses `CREATE TABLE IF NOT
EXISTS`. AI Governance Control Plane does not include a migration framework yet.

## Control-plane tenancy and RBAC

PostgreSQL persists the authenticated actor's AI Governance Control Plane tenancy state separately
from Keycloak. The `actor_id` in these tables is the verified JWT `sub`; a
Keycloak username, email, role, or tenant claim does not create authorization
by itself.

### organizations

Stores organization tenancy boundaries. `organization_id` is the primary key;
`slug` is unique, and `status`, `created_at`, and `updated_at` track lifecycle.

### projects

Stores projects within an organization. The primary key is
`(organization_id, project_id)`, with a foreign key to `organizations` and a
slug unique within each organization.

### organization_memberships

Stores the authoritative relationship between an actor and an organization.

Columns:

- `organization_id` — foreign key to `organizations`
- `actor_id` — immutable verified JWT `sub`
- `display_name` — optional presentation value
- `status` — membership lifecycle state; only `ACTIVE` memberships authorize
- `created_at`, `updated_at` — `TIMESTAMPTZ`

The composite primary key is `(organization_id, actor_id)`. This permits one
actor to belong to multiple organizations while preventing duplicates inside
one organization. `idx_membership_actor_status` supports tenant authorization
lookups.

Membership rows are created explicitly by the tenancy service: organization
creation provisions the creator, membership-management operations add actors,
and clean local bootstrap provisions the initial admin. Changing Keycloak
attributes does not insert or update this table.

### role_assignments

Stores organization-wide or project-scoped role grants. Its foreign key
`(organization_id, actor_id)` references `organization_memberships`, so an
actor must have a membership before receiving a role. Partial unique indexes
prevent duplicate grants at either scope. A role grants permissions only while
the corresponding membership is active.

### authorization_audit

Stores authorization evidence, including organization/project scope, actor,
operation, permission, allow/deny result, reason code, matched roles, and
permission-model version.

## Tables

### agent_evaluation

Responsibility:
Store evaluation results and their per-metric records.

Columns:

- `evaluation_id`
- `execution_id`
- `evaluator_type`
- `evaluator_version`
- `metric_name`
- `metric_score`
- `metadata_json`
- `provider_metadata_json`
- `provider_descriptor_snapshot_json`
- `artifacts_json`
- `created_at`
- `explanation`
- `organization_id`
- `project_id`

Notes:

- primary key is `(evaluation_id, metric_name)`
- indexed by execution, metric, and evaluator
- item-evaluation listing is scoped by organization and project
- `metadata_json` is stored as `JSONB`
- provider descriptor snapshots and runtime metadata are stored as generic
  `JSONB`, not provider-specific columns

### prompt_registry

Responsibility:
Store immutable prompt versions and prompt lifecycle state.

Columns:

- `prompt_id`
- `name`
- `version`
- `template`
- `variables_json`
- `created_at`
- `created_by`
- `status`

Notes:

- unique by `(name, version)`
- `variables_json` is stored as `JSONB`
- `created_at` is stored as `TIMESTAMPTZ`

### model_registry

Responsibility:
Store governed model versions and lifecycle state.

Columns:

- `model_id`
- `provider`
- `model_name`
- `version`
- `parameters_json`
- `cost_json`
- `latency`
- `context_window`
- `creator`
- `created_at`
- `status`

Notes:

- unique by `(provider, model_name, version)`
- `parameters_json` and `cost_json` are stored as `JSONB`
- `created_at` is stored as `TIMESTAMPTZ`

### dataset_registry

Responsibility:
Store versioned dataset metadata for governed evaluation use.

Columns:

- `dataset_id`
- `name`
- `version`
- `description`
- `storage_uri`
- `storage_type`
- `schema_version`
- `record_count`
- `checksum`
- `creator`
- `created_at`
- `status`

Notes:

- unique by `(name, version)`
- `created_at` is stored as `TIMESTAMPTZ`

### experiment

Responsibility:
Store experiment metadata and lifecycle state.

Columns:

- `experiment_id`
- `name`
- `description`
- `owner`
- `created_at`
- `status`

Notes:

- unique by `name`
- `created_at` is stored as `TIMESTAMPTZ`

### experiment_candidate

Responsibility:
Store immutable experiment candidate configurations.

Columns:

- `candidate_id`
- `experiment_id`
- `name`
- `prompt_id`
- `prompt_version`
- `model_id`
- `model_version`
- `dataset_id`
- `dataset_version`
- `evaluation_provider`
- `temperature`
- `top_p`
- `max_tokens`
- `metadata_json`
- `created_at`

Notes:

- indexed by `experiment_id`
- `metadata_json` is stored as `JSONB`
- `created_at` is stored as `TIMESTAMPTZ`

### evaluation_run

Responsibility:
Store experiment-level evaluation execution evidence.

Columns:

- `run_id`
- `experiment_id`
- `candidate_id`
- `dataset_version`
- `evaluation_provider`
- `evaluation_result_id`
- `started_at`
- `completed_at`
- `status`
- `failure_reason`
- `total_item_count`
- `completed_item_count`
- `evaluated_item_count`

Notes:

- indexed by `experiment_id` and `candidate_id`
- `started_at` and `completed_at` are stored as `TIMESTAMPTZ`

### leaderboard

Responsibility:
Store immutable leaderboard snapshots for experiments.

Columns:

- `leaderboard_id`
- `experiment_id`
- `ranking_strategy`
- `generated_at`

Notes:

- indexed by `experiment_id` and `ranking_strategy`
- `generated_at` is stored as `TIMESTAMPTZ`

### leaderboard_entry

Responsibility:
Store ranked entries for each leaderboard snapshot.

Columns:

- `leaderboard_id`
- `rank`
- `candidate_id`
- `overall_score`
- `metrics_json`
- `cost`
- `latency`
- `reason`

Notes:

- primary key is `(leaderboard_id, rank)`
- candidate-level lookup is indexed
- `metrics_json` is stored as `JSONB`

### job_execution

Responsibility:
Store asynchronous governance job state, idempotency metadata, lease metadata,
retry attempts, and immutable result references.

Columns:

- `job_id`
- `job_type`
- `status`
- `input_refs_json`
- `input_hash`
- `idempotency_key`
- `submitted_by`
- `attempt_count`
- `max_attempts`
- `result_ref`
- `failure_reason`
- `leased_by`
- `lease_expires_at`
- `heartbeat_at`
- `created_at`
- `updated_at`
- `started_at`
- `completed_at`

Notes:

- primary key is `job_id`
- `(job_type, idempotency_key)` is unique
- indexed by status and by `(job_type, status)`
- `input_refs_json` is stored as `JSONB`

### worker_heartbeat

Responsibility:
Store the latest liveness signal for each job worker, including workers that
are currently idle and have no leased job.

Columns:

- `worker_id` — stable worker process identifier and primary key
- `worker_type` — worker category, such as `job`
- `heartbeat_at` — latest `TIMESTAMPTZ` heartbeat
- `status` — worker lifecycle status, currently `RUNNING`

Notes:

- the dashboard compares `heartbeat_at` with `AI_GOVERNANCE_WORKER_HEARTBEAT_STALE_SECONDS`
- stale workers are reported as `Warning`; no registered workers are `Unknown`
- this table is separate from `job_execution.heartbeat_at`, which tracks a job lease

### mcp_execution_audit

Responsibility:
Store durable MCP controlled-write audit rows. MCP inserts a row when a write
tool starts and updates the same row when it completes, fails, or is validated
as a dry run.

Columns:

- `audit_id`
- `request_id`
- `correlation_id`
- `tool_name`
- `tool_version`
- `actor_id`
- `actor_type`
- `agent_name`
- `agent_session_id`
- `client_name`
- `client_version`
- `idempotency_key`
- `operation_type`
- `resource_type`
- `resource_id`
- `request_hash`
- `request_summary_json`
- `resolved_versions_json`
- `reason`
- `dry_run`
- `status`
- `job_id`
- `result_reference`
- `error_code`
- `error_message`
- `started_at`
- `completed_at`
- `duration_ms`
- `metadata_json`

Notes:

- primary key is `audit_id`
- indexed by request ID, idempotency key, and `(tool_name, status)`
- `request_summary_json`, `resolved_versions_json`, and `metadata_json` are
  stored as `JSONB`
- `request_summary_json` is redacted and should not contain secret-bearing
  provider configuration

### governance_decision

Responsibility:
Store authoritative governance decisions and optional deterministic
explanations.

Columns:

- `decision_id`
- `decision_type`
- `status`
- `target_type`
- `target_id`
- `reason`
- `confidence`
- `evidence_json`
- `policies_json`
- `provenance_json`
- `supersession_json`
- `explanation_json`
- `metadata_json`
- `created_at`
- `finalized_at`
- `archived_at`

Notes:

- primary key is `decision_id`
- indexed by `(target_type, target_id)`, status, provenance request ID, and
  provenance correlation ID
- structured fields are stored as `JSONB`
- timestamps are stored as `TIMESTAMPTZ`
- finalized decisions are immutable at the repository layer; supersession and
  archive operations use explicit lifecycle methods

### governance_decision_audit

Responsibility:
Store append-only decision lifecycle audit records.

Columns:

- `audit_id`
- `decision_id`
- `action`
- `actor_id`
- `producer_id`
- `correlation_id`
- `request_id`
- `reason`
- `created_at`
- `metadata_json`

Notes:

- primary key is `audit_id`
- `decision_id` references `governance_decision`
- indexed by `(decision_id, created_at)` and correlation ID
- `metadata_json` is stored as `JSONB`

### policy_definition

Responsibility:
Store Studio-owned policy identities and definition metadata.

Columns:

- `policy_id`
- `organization_id`
- `project_id`
- `name`
- `description`
- `category`
- `owner`
- `created_by`
- `created_at`
- `updated_at`
- `metadata_json`

Notes:

- primary key is `policy_id`
- `(project_id, name)` is unique
- indexed by organization, project, category, owner, and creation time
- timestamps are stored as `TIMESTAMPTZ`
- `metadata_json` is stored as `JSONB`

### policy_version

Responsibility:
Store executable policy versions, lifecycle state, target scope, and rules.

Columns:

- `policy_id`
- `version`
- `status`
- `target_types_json`
- `rules_json`
- `created_by`
- `created_at`
- `activated_at`
- `deprecated_at`
- `archived_at`
- `metadata_json`

Notes:

- primary key is `(policy_id, version)`
- `policy_id` references `policy_definition`
- indexed by policy and status
- one active version per policy is enforced with a partial unique index
- target types, rules, and metadata are stored as `JSONB`
- timestamps are stored as `TIMESTAMPTZ`

## Test Configuration

PostgreSQL repository tests are integration tests and are skipped unless
`AI_GOVERNANCE_POSTGRES_DSN` is set.

```bash
AI_GOVERNANCE_POSTGRES_DSN="postgresql://user:password@localhost:5432/ai_governance_test" uv run pytest tests/repositories/postgres
```

Each test creates a unique schema, sets the connection `search_path` to that
schema, initializes the AI Governance Control Plane tables, and drops the schema afterwards.

## Boundary Notes

PostgreSQL is intentionally treated as:

- the production reference persistence implementation
- a repository-contract implementation
- a storage backend owned below the service layer

It is intentionally not treated as:

- a reason for services to depend on PostgreSQL
- a place for governance lifecycle rules
- a migration framework
- a deployment or operations layer

## Related Documents

- [Architecture](../architecture/ARCHITECTURE.md)
- [Public API](./PUBLIC_API.md)
- [Extensibility](../architecture/EXTENSIBILITY.md)
- [SQLite Schema](./SQLITE_SCHEMA.md)
