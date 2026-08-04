# Configure Evaluation Provider Installations

This guide is for platform operators who configure evaluator instances for
Kavach Studio. It distinguishes the shipped provider adapter from the
configuration that a team selects for its evaluations, experiments, and
replays.

## Overview

- The provider type must be shipped and active in the running deployment.
  Studio lists these under **Assets → Evaluation Providers → Installed Adapters**.
- Use a durable settings repository. Docker and `.env.local` use SQLite by
  default; production deployments should use the approved SQLite volume or
  PostgreSQL settings backend.
- Make each referenced secret available to both the REST API and worker
  processes. A replay or asynchronous evaluation resolves its secret in the
  worker, not in the browser.

## Concepts

| Concept | Owned by | Example |
| --- | --- | --- |
| Provider type | Deployment | `trulens`, `mock` |
| Provider installation | Organization by default | `TruLens Production` |
| Settings | Installation | model, metrics, timeout |
| Secret references | Installation | `env://OPENAI_API_KEY` |

Provider types are immutable Python adapters. An installation is a persistent,
tenant-scoped configuration of one of those adapters. Creating an installation
does not install code or store a credential. Kavach captures the adapter version
when an installation is created, so Studio shows operators exactly which shipped
adapter version the installation targets.

## Create a TruLens Installation

1. Open **Assets → Evaluation Providers**.
2. Select **New Installation**. Studio pre-fills a valid configuration for the
   selected provider type.
3. Give the installation a clear operational name, such as `TruLens Production`
   or `TruLens Cost-Controlled`.
4. Review and edit the non-secret settings:

   ```json
   {
     "model": "gpt-5-mini",
     "enabled_metrics": [
       "answer_relevance",
       "context_relevance",
       "groundedness"
     ],
     "timeout_seconds": 30
   }
   ```

5. Reference, rather than paste, the credential:

   ```json
   {
     "openai_api_key": "env://OPENAI_API_KEY"
   }
   ```

6. Select **Validate Connection**. Kavach resolves each secret reference and
   initializes the adapter without saving or running an evaluation.
7. Leave **Enabled** selected and create the installation. Studio keeps
   **Create Installation** disabled until this exact configuration validates;
   the API repeats validation before it permits an enabled installation.

The TruLens adapter accepts `model`, `enabled_metrics`, `timeout_seconds`, and
optional metadata. The API key belongs only in `secret_refs` under the
`openai_api_key` key; do not put any token, key, or password in Settings.

## Use Installation

- When creating an experiment candidate, select the installation under
  **Provider installation**.
- When evaluating a completed replay, select it in **Evaluate Replay**.
- REST clients may pass `provider_installation_id` for synchronous or queued
  evaluations.

At runtime Kavach looks up the installation in the selected tenant/project,
checks that it is enabled, verifies that its provider type is still shipped,
then builds the adapter configuration. Secret references are dereferenced only
immediately before the adapter runs. The resolved secret is not returned by the
API, persisted in the installation, or copied into a job payload.

## Validate Connection

**Validate Connection** verifies secret resolution and provider initialization
without persisting an installation or executing an evaluation. Enabled
installations are validated again by the API on creation and update, so a UI
client cannot accidentally enable a configuration that failed validation.

For local TruLens use, ensure both processes have the same environment:

```text
OPENAI_API_KEY=...
KAVACH_TRULENS_MODEL=gpt-5-mini
```

The installation's explicit `model` takes precedence for that run; the
environment model remains the adapter fallback.

## Persistence, Scope, and Restart Behavior

Installations are stored as typed records in Kavach's settings-control store,
including tenant scope, enabled state, versions, timestamps, and update actor.
They survive a restart when `KAVACH_SETTINGS_REPOSITORY` is `sqlite` or
`postgres` and that backend is durable. They do not survive a restart with the
development-only `inmemory` backend.

Installations are **organization-scoped by default**, so all projects in the
organization can select a common evaluator. Choose **Current project** scope
only when a project needs a deliberately different evaluator configuration.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| TruLens is absent from Available Types | Configure `OPENAI_API_KEY` and a judge model, then restart the API/worker deployment. |
| Installation is rejected | Confirm settings is JSON, secret refs are JSON string values, and the provider type is active. |
| Evaluation fails resolving a secret | Confirm the API/worker environment contains the referenced variable. |
| Disabled installation cannot be selected/run | Enable it, then retry. |
| `vault://` or another non-`env://` URI fails | The current runtime resolver implements `env://` only. Other reference schemes are reserved for future resolvers. |

Provider schema resources live in `src/kavach/providers/schemas/`. Adding a
provider means shipping its adapter and schema together; Studio does not need a
vendor-specific form implementation.
