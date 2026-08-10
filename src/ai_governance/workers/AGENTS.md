# Scope

This directory owns asynchronous job execution runtimes and worker adapters.

## Architectural Facts

- `JobWorker` claims queued jobs through repository leases, releases expired
  leases, executes one job, and records explicit terminal transitions.
- Replay worker runtimes reconstruct `TenantContext` from the execution context
  captured at submission time. A worker must not adopt a new caller's scope for
  an existing job.
- Job handlers invoke application services and publish ontology job events only
  after terminal job state is recorded.

## Change Rules

- Preserve at-least-once-delivery safety across lease expiry, concurrent claims,
  retries, and cancellation. Make cancellation checkpoints and terminal
  transitions explicit.
- Do not duplicate domain rules or perform side effects before their durable
  job-state ordering and failure semantics are defined.
- Log correlation metadata needed to investigate a job without emitting secrets
  or protected content.

## Validation

Use `tests/workers/test_job_worker.py` and
`tests/workers/test_replay_worker_runtime.py`; run the owning service tests
when a worker changes application behavior.
