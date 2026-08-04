# Plugin Runtime Processes

Kavach plugins are not limited to the REST API. A plugin can contribute generic
providers, hooks, event subscribers, settings, permissions, routes, and job
handlers to any supported Kavach process.

This document describes the OSS runtime contract. It deliberately does not
describe a product-specific event platform or external delivery mechanism.

For the guided version, including diagrams and a support checklist, read
[Plugin Extensions in Plain English](PLUGIN_EXTENSION_GUIDE.md).

## Why worker processes load plugins

Some facts happen in the API process and others happen in a worker process.
For example, an API can durably queue a job, while a worker later starts,
completes, fails, or cancels it. An in-process `EventPublisher` only notifies
subscribers registered in the process that owns the transition.

Therefore every plugin-enabled host uses the same bootstrap path:

```text
discover installed plugins
        ↓
validate and register their generic contributions
        ↓
start plugins
        ↓
run the API or worker
        ↓
stop plugins during shutdown
```

`create_plugin_registry()` implements the first two steps. The API and the
standalone replay worker both use it. The replay worker passes the registry's
generic `EventPublisher` to `JobWorker`, so subscribers can observe worker
lifecycle facts as well as facts created by the API.

## Lifecycle ownership

Kavach owns plugin lifecycle ordering:

1. `validate` checks plugin configuration without starting work.
2. `register` adds generic contributions and event subscriptions.
3. `start` runs after every plugin has registered successfully.
4. `stop` runs during process shutdown in reverse registration order.

A worker must call `stop` even when its run loop exits through an exception or
an interrupt. This gives extensions one consistent cleanup point, independent
of whether the process is an API server or a background worker.

## What OSS guarantees—and what it does not

`EventPublisher` is a generic, in-process contract. It lets independently
installed plugins observe generic facts such as a resource lifecycle change.
It does not persist events, call external services, promise cross-process
delivery, or know about a particular product tier.

Durable persistence, outbox records, retries, delivery leases, dead letters,
and external sink providers belong to the extension that needs those business
semantics. A plugin may subscribe to generic lifecycle facts and implement
those concerns without adding product-specific names or persistence schemas to
Kavach OSS.

## Running a standalone replay worker

Run the worker with the same installed plugin distributions and relevant
configuration as the API process:

```sh
python -m kavach.workers.replay_worker_runtime
```

For a smoke test that claims at most one job:

```sh
python -m kavach.workers.replay_worker_runtime --once
```

The API and worker must also point to the same durable job repository. A
worker with different plugin installation or configuration can still run jobs,
but its optional plugin subscribers will not observe worker-local facts.
