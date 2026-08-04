# Worker Health & Heartbeats

## Overview

Kavach workers register themselves in the `worker_heartbeat` table and update
their liveness timestamp while polling. This allows the dashboard to detect
idle workers as well as workers processing jobs.

## Persistence

The table is available in SQLite, PostgreSQL, and Snowflake:

| Column | Purpose |
| --- | --- |
| `worker_id` | Stable worker process identifier |
| `worker_type` | Worker category, currently `job` |
| `heartbeat_at` | Latest liveness timestamp |
| `status` | Lifecycle state, currently `RUNNING` |

The worker registry is different from `job_execution.heartbeat_at`, which only
tracks the lease for a specific running job.

## Dashboard status

- `Healthy` — all registered workers reported within the stale threshold.
- `Warning` — one or more registered workers have stale heartbeats.
- `Unknown` — no worker has registered a heartbeat yet.

Configure the threshold with:

```env
KAVACH_WORKER_HEARTBEAT_STALE_SECONDS=120
```

The threshold should be greater than the worker polling interval to avoid false
warnings during normal scheduling jitter.

## Local and Docker behavior

In local SQLite mode, worker heartbeats are stored in the configured SQLite
database. In Docker, the platform and worker processes must use the same
persistent backend for the dashboard to see all workers. Deleting the SQLite
volume removes the registry and causes the dashboard to show `Unknown` until a
worker starts again.

## Troubleshooting

- `Unknown`: confirm the worker process started and uses the same database as the
  REST API.
- `Warning`: inspect worker logs and compare the last heartbeat with the stale
  threshold.
- Duplicate workers: ensure each process receives a unique `worker_id`.
- Stale rows after a crash are expected; they are retained for diagnosis and are
  classified by timestamp rather than silently deleted.
