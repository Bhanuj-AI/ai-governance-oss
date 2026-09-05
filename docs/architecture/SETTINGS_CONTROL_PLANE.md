# Settings Control Plane

The Settings Control Plane is a typed configuration resource with explicit
`SYSTEM`, `ORGANIZATION`, and `PROJECT` scopes. `SettingDefinition` records
form an immutable registry containing category, type, default, mutability,
sensitivity, restart behavior, environment binding, supported scopes,
runtime-consumer status, and validation rules. Deployment architecture remains
system-only.

Effective configuration follows `environment > project > organization >
system > default`. Runtime values are held by the selected memory, SQLite, or
PostgreSQL settings repository. Each scoped update uses compare-and-set with an
expected version, increments its version, and writes an audit record in the
same repository operation. Stale writes return HTTP 409. Environment values
are never copied into persistence or audit records, and sensitive integration
variables are reported only as connected or disconnected.

REST exposes list, detail, category, validation, update, and audit reads under
`/api/v1/settings`. RBAC uses `settings.read` and `settings.manage`. MCP exposes
`settings.list`, `settings.get`, `settings.categories`, `settings.validate`,
and `settings.update`; validation and mutation use the controlled-write audit
envelope and support dry runs.

Studio groups definitions by their registry category and displays effective
value, source, default, mutability, restart requirement, and runtime version.
An environment override disables editing. Operational variables are not set by
Compose merely to provide defaults; registry defaults remain editable, while
environment variables are reserved for explicit infrastructure overrides.
Dynamic values are re-resolved on every service lookup. Every mutable registry
definition has a live backend consumer; deployment settings remain
restart-bound and read-only.

`mcp.dry_run_default` is a live consumer-backed setting. When an MCP controlled
write omits `dry_run`, the MCP server resolves the effective scoped value from
REST. An explicit `dry_run` in the request always wins.

## Operational Consumers

- General instance name and timezone are returned by API metadata.
- Job settings control worker acquisition concurrency, retry defaults and
  delay, tenant queue admission, and retained read visibility.
- Governance settings control decision retention, replay-history retention,
  and persisted policy-version selection (`active`, `latest`, or explicit).
- Evaluation settings select the default provider, compute persisted
  pass/failure outcomes from global and metric thresholds, and enforce history
  retention.
- Ontology projection and reconciliation intervals are re-resolved by the
  synchronization worker loop on every cycle.
- Audit retention and interrupted timeout control audit reads.
- Agents Runtime settings control deterministic finding detectors: their sample
  counts, baseline and observation windows, thresholds, severity bands, and
  sustained-recovery behaviour. Studio presents these controls in the
  dedicated **Agents Runtime** category.
- MCP dry-run, audit-required, and idempotency-expiry settings are resolved for
  each controlled write. Idempotent results are cached only for the configured
  expiry, and disabling required audit suppresses controlled-write persistence.

## Where values are stored

There are three different kinds of state involved. They should not be confused.

1. A registry default lives in application code. It is used only when no
   environment or runtime value exists.
2. A runtime setting is stored by `AI_GOVERNANCE_SETTINGS_REPOSITORY`. The local Docker
   stack selects SQLite at `/var/lib/ai-governance/governance.db`, so runtime values and
   their audit history survive container restarts. An `inmemory` settings
   repository loses runtime values when the API process stops. PostgreSQL stores
   them durably in the `runtime_setting` and `setting_audit` tables.
3. Runtime working state belongs to the subsystem using the setting. For
   example, jobs are persisted by the job repository, while the MCP idempotency
   result cache is held in the MCP process and is cleared by a restart.

Environment overrides are not stored by AI Governance Control Plane. They belong to the deployment
configuration. If an environment variable is present, it wins at every scope
and the corresponding Studio control becomes read-only.

## Scope and Inheritance Example

Suppose `evaluation.pass_threshold` has these runtime values:

```text
SYSTEM       0.70
ORGANIZATION 0.80
PROJECT      no value
```

The project inherits `0.80` from its organization. If the project later saves
`0.90`, it uses `0.90`. If `AI_GOVERNANCE_EVALUATION_PASS_THRESHOLD=0.95` is supplied
by the deployment, every system, organization, and project uses `0.95` and UI
editing is disabled.

Each scope has its own version. Creating a new override uses
`expected_version: 0`. Updating version 2 uses `expected_version: 2`. If another
administrator has already written version 3, the stale update receives HTTP
409 and must refresh before trying again.

## Duration Format

Durations are positive integers followed by one unit:

- `ms` for milliseconds
- `s` for seconds
- `m` for minutes
- `h` for hours
- `d` for days
- `w` for weeks

Examples are `500ms`, `30s`, `15m`, `24h`, and `30d`.

## General Settings

### `general.instance_name`

Default: `AI Governance Control Plane`. Environment override: `AI_GOVERNANCE_INSTANCE_NAME`.

This is the human-readable name returned by `GET /api/v1`. The metadata route
resolves it using the request's organization and project context, so different
projects may display different instance names. A runtime value is persisted by
the settings repository; the API metadata response itself is generated on each
request.

### `general.environment`

Default: `local`. Environment variable: `AI_GOVERNANCE_ENV`. Read-only and system-only.

This describes the deployment environment and participates in deployment
guardrails such as development-identity protection. It is not editable at
runtime because changing an environment label does not safely transform a
running deployment.

### `general.version`

Read-only and system-only. It reports the installed AI Governance Control Plane package version from
Python distribution metadata. It is not a runtime setting and changes only
when a different AI Governance Control Plane build is installed.

### `general.build`

Default: `development`. Environment variable: `AI_GOVERNANCE_BUILD_ID`. Read-only and
restart-bound.

This identifies the deployed build. Build scripts or CI should populate it. It
is deployment metadata, not a value AI Governance Control Plane writes to the settings repository.

### `general.timezone`

Default: `UTC`. Environment override: `AI_GOVERNANCE_TIMEZONE`.

This is returned by API metadata so clients know the configured display
timezone. AI Governance Control Plane continues to persist authoritative timestamps in UTC; this
setting does not rewrite stored timestamps.

## Repository Settings

Repository selections are deployment architecture. They are read-only,
system-only, and require a restart because repository objects are constructed
during process startup.

### `repositories.active_backend`

Environment variable: `AI_GOVERNANCE_POLICY_REPOSITORY`. It currently reports the
policy-administration repository selection (`inmemory`, `sqlite`, or
`postgres`). Other domain repositories retain their own `AI_GOVERNANCE_*_REPOSITORY`
variables.

### `repositories.settings_backend`

Environment variable: `AI_GOVERNANCE_SETTINGS_REPOSITORY`. It selects where runtime
settings and settings audit records are stored. With `inmemory`, changes are
process-local. SQLite and PostgreSQL are durable.

### `repositories.connection_status`

Read-only. This is currently a registry-provided `connected` display value,
not an active database probe. Service readiness remains the authoritative
operational health signal.

### `repositories.migration_status`

Read-only. This is currently a registry-provided `current` display value, not
an active migration inspection. It must not be used as a deployment gate until
it is backed by a migration-state provider.

## Job settings

### `jobs.worker_concurrency`

Default: `4`; valid range: `1` to `128`. Environment override:
`AI_GOVERNANCE_JOB_WORKER_CONCURRENCY`.

Before a configured `JobWorker` acquires another queued job, it counts jobs in
`RUNNING` state. If the effective concurrency has already been reached, the
worker leaves the next job queued. The setting is persisted by the settings
repository; job states are persisted separately by the job repository.

Workers must be constructed with `ConfigurationService` for this gate to be
active. The setting limits application job execution, not operating-system
threads or Kubernetes replicas.

### `jobs.retry_attempts`

Default: `3`; valid range: `1` to `10`. Environment override:
`AI_GOVERNANCE_JOB_RETRY_ATTEMPTS`.

When a REST job, evaluation job, or experiment job omits `max_attempts`, the
submission route resolves this setting and stores the result on the `Job`.
Supplying `max_attempts` explicitly on a request wins. Because the chosen value
is copied into the persisted job, later setting changes affect new jobs only.

### `jobs.retry_delay`

Default: `1ms`. Environment override: `AI_GOVERNANCE_JOB_RETRY_DELAY`.

When a failed job is retried, `JobApiService` adds this duration to the job's
completion or update time. A retry before that instant is rejected. The delay
is resolved at retry time, so changing it immediately affects existing failed
jobs that have not yet been retried.

### `jobs.queue_size`

Default: `1000`; valid range: `1` to `100000`. Environment override:
`AI_GOVERNANCE_JOB_QUEUE_SIZE`.

After checking for an existing idempotent job, submission counts queued jobs in
the selected organization and project. A new submission is rejected when that
tenant queue has reached the effective capacity. Existing idempotent requests
still return their original job even when the queue is full.

### `jobs.retention`

Default: `30d`. Environment override: `AI_GOVERNANCE_JOB_RETENTION`.

Job list reads resolve this setting and hide completed terminal jobs older than
the retention cutoff. The current implementation is logical retention: it does
not physically delete job rows. Queued and running work is not expired by this
setting.

## Governance Settings

### `governance.decision_retention`

Default: `365d`. Environment override: `AI_GOVERNANCE_DECISION_RETENTION`.

Every newly evaluated decision receives an internal recorded-at timestamp.
Decision list and detail reads compare that timestamp with the effective
retention cutoff. Expired decisions are excluded from lists and direct access
behaves as not found. The decision remains in its repository for historical
integrity; retention is logical rather than destructive.

### `governance.replay_retention`

Default: `90d`. Environment override: `AI_GOVERNANCE_REPLAY_RETENTION`.

`EvaluationHistoryService` filters source evaluation results before creating
replay history, comparisons, summaries, or drift analysis. Results older than
the cutoff do not participate in replay-facing views. Evaluation rows remain
stored in their repository.

### `governance.default_policy_version_behavior`

Default: `active`. Allowed values: `active`, `latest`, and `explicit`.
Environment override: `AI_GOVERNANCE_DEFAULT_POLICY_VERSION_BEHAVIOR`.

The persisted governance policy provider resolves this setting when a decision
is evaluated:

- `active` selects each policy's active version.
- `latest` selects its newest non-archived version.
- `explicit` selects only versions supplied in request metadata under
  `policy_versions`, for example `{"policy-a": "3"}`.

Policy definitions are restricted to the request's organization and project.
If requested policies cannot produce a version under the selected behavior,
decision evaluation reports them as missing rather than silently choosing a
different version.

## Evaluation Settings

### `evaluation.default_provider`

Default: `mock`. Environment override: `AI_GOVERNANCE_DEFAULT_EVALUATION_PROVIDER`.

Synchronous evaluation requests may omit `provider_name`. In that case the
route resolves this setting and asks the provider registry for that provider.
An explicit request provider wins. The selected provider name is persisted on
the evaluation result.

### `evaluation.pass_threshold`

Default: `0.8`; valid range: `0` to `1`. Environment override:
`AI_GOVERNANCE_EVALUATION_PASS_THRESHOLD`.

After a provider returns metric scores, AI Governance Control Plane uses this value as the fallback
threshold for every metric. It calculates an average score and records a
`ai_governance_evaluation_outcome` structure in evaluation metadata containing the
pass result, score, thresholds, and failed metric names. The outcome is stored
with the evaluation result.

### `evaluation.thresholds`

Default: `{}`. Environment override: `AI_GOVERNANCE_EVALUATION_THRESHOLDS`.

This JSON object overrides the default threshold for named metrics. For
example:

```json
{
  "answer_relevance": 0.85,
  "groundedness": 0.90
}
```

A metric not present in this object uses `evaluation.pass_threshold`. An
evaluation passes only when it has metrics and every metric meets its resolved
threshold.

### `evaluation.retention`

Default: `180d`. Environment override: `AI_GOVERNANCE_EVALUATION_RETENTION`.

Evaluation history reads hide results older than the effective cutoff before
selecting the latest result. This is logical retention; it does not delete the
stored evaluation or its artifacts.

## Ontology Settings

### `ontology.projection_interval`

Default: `30s`. Environment override: `AI_GOVERNANCE_ONTOLOGY_PROJECTION_INTERVAL`.

The ontology synchronization worker processes a batch of pending projection
events, then waits for this duration. It resolves the setting again on every
cycle, so a runtime change affects the next wait without restarting the worker.

### `ontology.reconciliation_interval`

Default: `5m`. Environment override:
`AI_GOVERNANCE_ONTOLOGY_RECONCILIATION_INTERVAL`.

The same worker tracks the next full reconciliation time. When due, it asks the
diff-based reconciler to compare authoritative repositories with the ontology
and repair drift. The setting is re-resolved each cycle.

Both interval settings are consumed by `OntologySynchronizationWorker.run_forever`.
The worker must be started with a `ConfigurationService` and a stoppable event.

### `ontology.neo4j_endpoint`

Environment variable: `AI_GOVERNANCE_GRAPH_URI`. Read-only, system-only, and
restart-bound. It reports the endpoint used when graph adapters are built.
Changing it through the UI is intentionally forbidden because live graph
repository switching is outside the control-plane boundary.

### `ontology.connection_health`

Read-only. `unknown` means no graph health probe has populated an authoritative
state. This field must not be treated as a replacement for Neo4j or platform
health checks.

## Audit Settings

### `audit.retention`

Default: `365d`. Environment override: `AI_GOVERNANCE_AUDIT_RETENTION`.

Audit list and detail endpoints hide records older than the effective cutoff.
The underlying audit rows are retained; no destructive purge is performed.

### `audit.interrupted_timeout`

Default: `15m`. Environment override: `AI_GOVERNANCE_AUDIT_INTERRUPTED_TIMEOUT`.

When an audit request does not explicitly supply
`interrupted_after_seconds`, the API converts this duration to seconds. A
`STARTED` record with no completion timestamp is reported as interrupted after
that period. An explicit query parameter wins for that request.

### `audit.backend`

Environment variable: `AI_GOVERNANCE_MCP_AUDIT_BACKEND`. Read-only, system-only, and
restart-bound. This setting currently reports deployment intent. Actual MCP
construction selects in-memory storage when
`AI_GOVERNANCE_MCP_AUDIT_DATABASE_PATH` is empty and SQLite when a path is present;
PostgreSQL audit construction is not yet wired. It cannot be replaced in a
running process.

## MCP Settings

### `mcp.dry_run_default`

Default: `false`. Environment override: `AI_GOVERNANCE_MCP_DRY_RUN_DEFAULT`.

For a controlled MCP write that omits `dry_run`, the MCP server asks the REST
Settings API for the effective project, organization, or system value. `true`
validates and audits the operation without performing its REST mutation. An
explicit `dry_run` value in the MCP request always wins.

The setting is persisted by the settings repository. No separate dry-run state
is stored in MCP.

### `mcp.audit_required`

Default: `true`. Environment override: `AI_GOVERNANCE_MCP_AUDIT_REQUIRED`.

MCP resolves this value for every controlled write. When `true`, the MCP audit
log persists its started and completed records. When `false`, the operation
still runs but those controlled-write audit records are not saved. Structured
process logs and REST-side domain auditing are separate concerns.

### `mcp.idempotency_expiry`

Default: `24h`. Environment override: `AI_GOVERNANCE_MCP_IDEMPOTENCY_EXPIRY`.

MCP identifies a controlled operation by tool name, idempotency key,
organization, and project. It caches the successful result in the MCP process
for this duration:

- Repeating the same input returns the cached result without performing REST
  mutation again.
- Reusing the key with different input is rejected.
- After expiry, the operation may execute again.

The setting is durable when the settings repository is durable, but the result
cache is in memory. Restarting MCP clears it, and separate MCP replicas do not
share it. Job idempotency remains independently durable in the job repository.

## Integration Settings

Integration entries are read-only connection indicators derived from explicit
deployment variables. Secret values are never returned.

- `integrations.openai` reports connected when `OPENAI_API_KEY` is present.
- `integrations.neo4j` reports connected when `AI_GOVERNANCE_GRAPH_URI` is present.
- `integrations.msteams` reports connected when
  `AI_GOVERNANCE_MSTEAMS_WEBHOOK_URL` is present.
- `integrations.webhook` reports connected when `AI_GOVERNANCE_WEBHOOK_URL` is
  present.

These indicators confirm configuration presence, not successful remote
authentication or continuous connectivity.

## System Settings

System entries are read-only and system-only:

- `system.version` is the installed Python package version.
- `system.commit_sha` comes from `AI_GOVERNANCE_COMMIT_SHA` and identifies source
  revision.
- `system.build_date` comes from `AI_GOVERNANCE_BUILD_DATE`.
- `system.python_version` is calculated from the running Python interpreter.

They are deployment/runtime metadata and are never persisted as editable
runtime settings.

## End-to-end Update Example

To create a project-level evaluation threshold:

```http
PATCH /api/v1/settings/evaluation.pass_threshold
X-AI-Governance-Organization-Id: org_default
X-AI-Governance-Project-Id: project_default
X-AI-Governance-Actor-Id: local-admin
Content-Type: application/json

{
  "value": 0.9,
  "reason": "Raise the release quality bar",
  "scope": "PROJECT",
  "expected_version": 0
}
```

AI Governance Control Plane validates the value, compares the expected project-setting version,
writes the new runtime value and audit record atomically, and returns the
effective result. Subsequent evaluations in that project resolve `0.9` and
persist their threshold outcome. Other projects continue inheriting their own
organization or system values.
