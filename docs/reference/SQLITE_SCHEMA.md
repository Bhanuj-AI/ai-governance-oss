# SQLite Schema

## Overview

SQLite is the local and lightweight reference persistence backend for AI Governance Control Plane.
It is used for local development, tests, and as a concrete implementation of
the repository contracts. It is not the platform boundary.

PostgreSQL is the production reference persistence backend. Additional stores
such as Snowflake may be added through the same repository contracts.

## Control-plane tenancy and RBAC

The following tables persist AI Governance Control Plane's tenant membership and authorization
model. Identity-provider tokens authenticate the caller, but they do not
replace these records: the `actor_id` stored here is the verified JWT `sub`.

### organizations

Responsibility:
Store the organization tenancy boundary.

Current schema summary:

- `organization_id` (primary key)
- `name`
- `slug` (unique)
- `status`
- `created_at`
- `updated_at`

### projects

Responsibility:
Store projects within an organization.

Current schema summary:

- composite primary key: `(organization_id, project_id)`
- `name`, `slug`, `description`, `status`
- `created_at`, `updated_at`

Each project references `organizations(organization_id)` and its slug is unique
within that organization.

### organization_memberships

Responsibility:
Persist which authenticated actors belong to each organization. This is the
authoritative AI Governance Control Plane membership record used by authorization; it is not derived
automatically from Keycloak roles or tenant claims.

Current schema summary:

- composite primary key: `(organization_id, actor_id)`
- `actor_id`: the immutable verified JWT `sub`
- `display_name`: optional presentation value only
- `status`: membership lifecycle state; authorization requires `ACTIVE`
- `created_at`, `updated_at`

`organization_id` references `organizations`. The composite key allows one
actor to be a member of multiple organizations while preventing duplicate
memberships within a single organization. The
`idx_membership_actor_status` index supports authorization lookups by
organization, actor, and status.

Memberships are created explicitly by the tenancy service: organization
creation creates the creator's active membership, membership-management APIs
add members, and a clean local control-plane database receives the bootstrap
admin membership. A JWT's `organization_id` claim only constrains the requested
tenant; it does not insert or update this table.

### role_assignments

Responsibility:
Persist organization- and project-scoped built-in role grants.

Current schema summary:

- `assignment_id` (primary key)
- `organization_id`, `project_id` (optional), `actor_id`
- `role`
- `created_at`, `created_by`

The foreign key `(organization_id, actor_id)` references
`organization_memberships`, so a role assignment cannot exist without a
membership for the same actor and organization. Partial unique indexes prevent
duplicate organization-scoped and project-scoped grants. A role assignment
grants permissions only while its corresponding membership is active.

### authorization_audit

Responsibility:
Store the evidence for authorization decisions.

It records organization/project scope, actor, requested operation and
permission, allow/deny result, reason, matched roles, and permission-model
version.

## Tables

### agent_evaluation

Responsibility:
Store evaluation results and their per-metric records.

Current schema summary:

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
- provider descriptor snapshots and runtime metadata are stored as generic JSON
  text, not provider-specific columns

### prompt_registry

Responsibility:
Store immutable prompt versions and prompt lifecycle state.

Current schema summary:

- `prompt_id`
- `name`
- `version`
- `template`
- `variables_json`
- `created_at`
- `created_by`
- `status`

### model_registry

Responsibility:
Store governed model versions and lifecycle state.

Current schema summary:

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

Responsibility:
Store versioned dataset metadata for governed evaluation use.

Current schema summary:

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

Responsibility:
Store experiment metadata and lifecycle state.

Current schema summary:

- `experiment_id`
- `name`
- `description`
- `owner`
- `created_at`
- `status`

### experiment_candidate

Responsibility:
Store immutable experiment candidate configurations.

Current schema summary:

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

Responsibility:
Store experiment-level evaluation execution evidence.

Current schema summary:

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

### leaderboard

Responsibility:
Store immutable leaderboard snapshots for experiments.

Current schema summary:

- `leaderboard_id`
- `experiment_id`
- `ranking_strategy`
- `generated_at`

### leaderboard_entry

Responsibility:
Store ranked entries for each leaderboard snapshot.

Current schema summary:

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

### job_execution

Responsibility:
Store asynchronous governance job state, idempotency metadata, lease metadata,
retry attempts, and immutable result references.

Current schema summary:

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
- `input_refs_json` is canonical JSON, and `input_hash` is derived from that
  canonical representation

### mcp_execution_audit

Responsibility:
Store durable MCP controlled-write audit rows. MCP inserts a row when a write
tool begins and updates the same row when the call completes, fails, or is
validated as a dry run.

Current schema summary:

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
- `request_summary_json` stores a redacted summary, not raw secret-bearing
  payloads
- interrupted MCP calls remain visible as `STARTED`

### governance_decision

Responsibility:
Store authoritative governance decisions and optional deterministic
explanations.

Current schema summary:

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
- JSON fields store canonical text JSON
- finalized decisions are immutable at the repository layer; supersession and
  archive operations use explicit lifecycle methods

### governance_decision_audit

Responsibility:
Store append-only decision lifecycle audit records.

Current schema summary:

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

### policy_definition

Responsibility:
Store Studio-owned policy identities and definition metadata.

Current schema summary:

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
- `metadata_json` stores canonical text JSON

### policy_version

Responsibility:
Store executable policy versions, lifecycle state, target scope, and rules.

Current schema summary:

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
- target types, rules, and metadata are stored as canonical text JSON

## Schema Shape

The SQLite schema mirrors the platform’s control-plane flow:

```text
prompt_registry
model_registry
dataset_registry
        |
        v
experiment -> experiment_candidate -> evaluation_run -> agent_evaluation
                                                |
                                                v
                                           leaderboard
                                                |
                                                v
                                       leaderboard_entry

job_execution -> immutable result_ref

mcp_execution_audit -> controlled MCP write evidence

governance_decision -> governance_decision_audit

policy_definition -> policy_version
```

## Boundary Notes

SQLite is intentionally treated as:

- a local backend
- a test backend
- a reference implementation

It is intentionally not treated as:

- the platform architecture
- the only supported persistence model
- a reason to collapse repository contracts

## Related Documents

- [Architecture](../architecture/ARCHITECTURE.md)
- [Public API](./PUBLIC_API.md)
- [Extensibility](../architecture/EXTENSIBILITY.md)
- [PostgreSQL Schema](./POSTGRES_SCHEMA.md)
