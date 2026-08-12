# Snowflake Schema

## Overview

Snowflake is AI Governance Control Plane's optional enterprise analytics persistence backend. It
implements the same repository contracts as SQLite and PostgreSQL, so services
remain storage-independent.

The Snowflake schema mirrors the SQLite and PostgreSQL schemas semantically
while using Snowflake-native types:

- `TIMESTAMP_TZ` for persisted timestamps
- `VARIANT` for structured metadata and configuration fields
- `FLOAT` for scores, cost, latency, and runtime parameters
- `NUMBER` for integer-like values
- informational primary key and unique declarations

AI Governance Control Plane initializes the schema with `CREATE TABLE IF NOT EXISTS`. Snowflake
support does not introduce Snowpark, Cortex, Dynamic Tables, Streams, Tasks,
Stages, or deployment orchestration.

## Control-plane tenancy and RBAC

Snowflake uses the same logical tenancy model as SQLite and PostgreSQL when it
is selected as a repository backend. Keycloak authenticates the actor, but
AI Governance Control Plane persists the authorization relationship. `actor_id` is the verified JWT
`sub`; Keycloak roles and tenant claims do not replace membership rows.

### organizations and projects

`organizations` stores organization boundaries, with `organization_id` as the
primary identifier and unique slugs. `projects` stores projects under an
organization using the composite identity `(organization_id, project_id)` and
an organization foreign-key relationship.

### organization_memberships

Stores the authoritative organization membership for authenticated actors.

Columns:

- `organization_id`
- `actor_id` — immutable verified JWT `sub`
- `display_name`
- `status` — only `ACTIVE` memberships authorize
- `created_at`, `updated_at` — `TIMESTAMP_TZ`

The logical primary key is `(organization_id, actor_id)`. It allows an actor to
belong to multiple organizations while preventing duplicate memberships in the
same organization. Implementations should retain the equivalent actor/status
lookup key used by the SQLite and PostgreSQL repositories.

Membership persistence is explicit: organization creation adds the creator,
membership-management operations add other actors, and clean local bootstrap
adds the initial admin. Keycloak attribute changes constrain token scope but do
not provision or modify Snowflake membership records.

### role_assignments

Stores organization-wide and project-scoped role grants. The logical foreign
key `(organization_id, actor_id)` references `organization_memberships`, so a
role cannot be effective without a matching membership. Duplicate grants are
prevented separately for organization and project scope, and inactive
memberships invalidate the grant for authorization.

### authorization_audit

Stores authorization decision evidence: tenant scope, actor, operation,
permission, result, reason code, matched roles, and permission-model version.
Snowflake-native timestamp and semi-structured types should be used according
to the deployment schema while preserving these repository fields.

## Tables

### agent_evaluation

Stores evaluation results as one row per metric.

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
- result-listing operations are scoped by `(organization_id, project_id)`
- `metadata_json` is stored as `VARIANT`
- provider descriptor snapshots and runtime metadata are stored as generic
  `VARIANT`, not provider-specific columns

### prompt_registry

Stores immutable prompt versions and lifecycle state.

Columns:

- `prompt_id`
- `name`
- `version`
- `template`
- `variables_json`
- `created_at`
- `created_by`
- `status`

### model_registry

Stores governed model versions and lifecycle state.

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

### dataset_registry

Stores versioned dataset metadata.

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

### experiment

Stores experiment metadata and lifecycle state.

Columns:

- `experiment_id`
- `name`
- `description`
- `owner`
- `created_at`
- `status`

### experiment_candidate

Stores immutable experiment candidate configurations.

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

### evaluation_run

Stores experiment-level evaluation execution evidence.

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

### worker_heartbeat

Stores the latest liveness signal for each worker, including idle workers that
do not currently own a job lease.

Columns:

- `worker_id` — stable worker identifier and primary key
- `worker_type` — worker category, such as `job`
- `heartbeat_at` — latest `TIMESTAMP_TZ` heartbeat
- `status` — worker lifecycle status, currently `RUNNING`

The dashboard compares `heartbeat_at` with
`AI_GOVERNANCE_WORKER_HEARTBEAT_STALE_SECONDS`. This is distinct from the job-level
`heartbeat_at` stored on `job_execution`.
- `status`

### leaderboard

Stores leaderboard snapshots for experiments.

Columns:

- `leaderboard_id`
- `experiment_id`
- `ranking_strategy`
- `generated_at`

### leaderboard_entry

Stores ranked entries for each leaderboard snapshot.

Columns:

- `leaderboard_id`
- `rank`
- `candidate_id`
- `overall_score`
- `metrics_json`
- `cost`
- `latency`
- `reason`

### job_execution

Stores asynchronous governance job state, idempotency metadata, lease metadata,
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

### mcp_execution_audit

Stores durable MCP controlled-write audit rows. MCP inserts a row when a write
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

- JSON-like columns use `VARIANT`
- `request_summary_json` is redacted and should not contain secret-bearing
  provider configuration

## Testing

Snowflake repository tests are optional for normal local development. They skip
unless Snowflake environment variables are configured:

- `AI_GOVERNANCE_SNOWFLAKE_ACCOUNT`
- `AI_GOVERNANCE_SNOWFLAKE_USER`
- `AI_GOVERNANCE_SNOWFLAKE_PASSWORD`, `AI_GOVERNANCE_SNOWFLAKE_AUTHENTICATOR`,
  `AI_GOVERNANCE_SNOWFLAKE_TOKEN`, or `AI_GOVERNANCE_SNOWFLAKE_PRIVATE_KEY_PATH`
- `AI_GOVERNANCE_SNOWFLAKE_WAREHOUSE`
- `AI_GOVERNANCE_SNOWFLAKE_DATABASE`
- `AI_GOVERNANCE_SNOWFLAKE_SCHEMA`
- `AI_GOVERNANCE_SNOWFLAKE_ROLE` optionally

Tests create a generated `AI_GOVERNANCE_TEST_<uuid>` schema, initialize AI Governance Control Plane tables
there, and drop that schema after the test session.

## Boundary Notes

Snowflake is intentionally treated as:

- an enterprise analytics persistence backend
- an optional repository implementation
- a way to query governance metadata alongside analytical data

It is intentionally not treated as:

- a core platform dependency
- a deployment or runtime orchestration layer
- an implicit dependency on Cortex, Snowpark, Streams, Dynamic Tables, or Tasks

## Related Documents

- [Architecture](../architecture/ARCHITECTURE.md)
- [Extensibility](../architecture/EXTENSIBILITY.md)
- [SQLite Schema](./SQLITE_SCHEMA.md)
- [PostgreSQL Schema](./POSTGRES_SCHEMA.md)
