# Replay Management

Replay Management records a governed request to reproduce a historical workflow
execution. It is not an execution retry.

Creating a replay creates a tenant-scoped `Replay` in `DRAFT`, validates
immutable source evidence, freezes a `ReplayConfiguration`, and then records
either `READY` or `FAILED`. `READY` means the request is prepared for
execution; no workflow, job, evaluation, comparison, drift analysis, or
ontology update is performed during preparation.

Replays are idempotent within an organization and project. The same idempotency
key and request hash returns the existing replay; a different hash is rejected.
Records can be archived, but are never deleted through the normal lifecycle.

The public transport surface is:

- `POST /api/v1/replays`
- `GET /api/v1/replays`
- `GET /api/v1/replays/{replay_id}`
- `POST /api/v1/replays/{replay_id}/archive`

MCP provides `replay.create`, `replay.get`, `replay.list`, and
`replay.archive`. The create tool supports a dry run that resolves historical
configuration without persisting a replay or reserving its idempotency key.

Replay Management depends on source-execution evidence through an application
boundary. It does not depend on Evaluation History, Experiment Management, job
execution, or ontology synchronization.

## Execution

Submitting a READY replay creates one `REPLAY_EXECUTION` Job. Job retries keep
the same replay, job, frozen configuration hash, and reserved replay execution
identity; they do not create another Replay record.

The job handler resolves a framework-neutral execution adapter, creates a new
`WorkflowExecution`, and persists source-to-replay lineage in the new execution
metadata. The source execution is never changed. Execution stops after this
evidence is recorded: it does not evaluate, compare, or analyse drift.

The execution lifecycle adds `QUEUED`, `RUNNING`, `EXECUTION_COMPLETED`, and
`CANCELLED`. Submission and cancellation are available through
`POST /api/v1/replays/{replay_id}/submit` and
`POST /api/v1/replays/{replay_id}/cancel`, and through `replay.submit` and
`replay.cancel` MCP tools.

## Governed evidence

`EXECUTION_COMPLETED` replays can be evaluated through a separate
`REPLAY_EVALUATION` job. The workflow is never rerun when evaluation, baseline
resolution, comparison, or drift analysis is retried.

The evaluation handler resumes from evidence references stored on `Replay`:
replay evaluation, compatible source baseline, comparison, drift, and final
result. It verifies source-to-produced-execution lineage before allowing the
cross-execution comparison. A completed replay owns one immutable
`ReplayResult`, containing compact comparison and drift summaries plus stable
references to the underlying governance evidence.

The successful evidence lifecycle is `EXECUTION_COMPLETED -> EVALUATING ->
COMPARING -> COMPLETED`. Failures retain all already-persisted evidence and
can be archived; cancellation is supported until completion.

The public additions are `POST /api/v1/replays/{replay_id}/evaluate` and
`GET /api/v1/replays/{replay_id}/result`, with `replay.evaluate` and
`replay.result` in MCP. Evaluation dry runs validate state and submission
inputs without creating jobs or evidence.

## Local smoke test

Run the full replay lifecycle without external services:

```sh
sh scripts/replay/run-smoke.sh
```

It uses in-memory repositories and deterministic adapters, then prints the
completed replay and immutable result references.

## Studio

Kavach Studio exposes Replay as a first-class capability at `/replays`,
`/replays/new`, and `/replays/{replayId}`. The console only consumes the
tenant-scoped Replay APIs: it never reconstructs executions, chooses baselines,
calculates drift, or writes ontology data.

Historical source selection uses `GET /api/v1/replay-executions/search`, a
tenant-scoped opaque-cursor discovery contract. It returns a small, safe
projection of executions and supports ID/workflow/status/time-range search plus a
replayable-only filter; it must be backed by a projected execution search index
in production, not a full runtime-database scan. The execution detail view
provides the contextual **Create replay** path, while exact ID/deep-link entry
remains a fallback. Creating or validating a Replay resolves the selected
source again, so browser selection never bypasses authorization or frozen
evidence validation.

The detail view uses React Flow lineage derived from persisted Replay
references, so it remains useful while ontology projection is pending. Nodes
can be repositioned locally and reset to their persisted layout; connections
remain read-only. The graph distinguishes source and produced executions,
execution/evaluation jobs, baseline and replay evaluations, comparison, drift,
and final result evidence.

Local/dev startup demo seeding includes 27 tenant-scoped Replay records so the
inventory pagination can be reviewed. Twenty-two records are completed and
include frozen configuration plus immutable result, comparison, and drift
references; five provide ready, active, comparison, and failure lifecycle
examples without submitting real workflow or provider work. It also seeds 27
matching replayable historical execution projections, making the discovery,
validation, and create journey work locally.

## Durable execution catalog

Replay source discovery is a lightweight, eventually consistent projection;
it is never the authority for Replay creation. Configure
`KAVACH_REPLAY_EXECUTION_CATALOG_BACKEND=postgres` together with the existing
`KAVACH_REPLAY_POSTGRES_DSN` to persist tenant-scoped execution projections in
PostgreSQL. The projection stores identity, workflow summary, execution status,
timestamps, replayability, and evaluation-availability indicators only. Search
uses `executed_at DESC, execution_id DESC` opaque keyset cursors. Validation
and creation always re-resolve the full source execution through the
authoritative source resolver.

## Job worker runtime

`REPLAY_EXECUTION`, `REPLAY_EVALUATION`, `EVALUATION`, and `EXPERIMENT` are
consumed by the ordinary `JobWorker` through a shared worker runtime. A worker atomically claims one
queued job with a lease, dispatches it by `JobType`, and acknowledges a result
only after the handler has committed its Replay evidence. SQLite claims use a
transactional compare-and-set, so competing local workers cannot both claim
the same job.

The built-in `historical` adapter reconstructs a completed execution from the
frozen source snapshot. Once that execution and its lineage are persisted, the
runtime idempotently submits the replay evaluation job (default provider:
`mock`). Redelivery after a worker interruption reuses the persisted replay
execution ID and evaluation job idempotency key; it never creates a second
Replay or produced execution.

For local and Docker use, the source resolver is a durable SQLite execution
store whenever `KAVACH_REPLAY_EXECUTION_CATALOG_BACKEND=sqlite`. It is separate
from the search catalog because it retains the full source/produced execution
payload required by handlers. API and worker processes therefore share the
same Replay, Job, evaluation, experiment, and execution data when the corresponding
`KAVACH_*_SQLITE_PATH` settings point at one database.

Evaluation and Experiment handlers consume the immutable async submission
payloads produced by their respective APIs (`evaluation.submit_async` and
`experiment.run_async`). Legacy `REPLAY` and unrelated `DRIFT_ANALYSIS` jobs
are deliberately not claimed by this runtime, so a Replay worker cannot turn
unsupported work into a failed job.

Run a dedicated worker process with:

```sh
uv run python -m kavach.workers.replay_worker_runtime
```

Set `KAVACH_RUN_REPLAY_WORKER=true` to run the same runtime alongside the API
process in local development. Docker Compose starts `kavach-replay-worker` as a
separate process sharing the `kavach_sqlite_data` volume. `SIGTERM` and
`SIGINT` stop polling after the current safe handler boundary; unacknowledged
work is recovered after its lease expires. Cancelling a queued or running
Replay records cancellation on both Replay and Job, and the handlers check the
persisted cancellation request before and after their safe execution stages.
