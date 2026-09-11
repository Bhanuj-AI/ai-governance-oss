# Inspect AI prompt-length sweep

This experiment measures a direct JSON decision against a genuine two-call
planner–executor decision under the same model, scorer, task set, limits and
repetitions. It is a bounded workload study, not a general claim about
planning.

The packaged task is `ai_governance.inspect_tasks:incident_prompt_length_sweep`.
It contains eight deterministic data-pipeline release incidents represented at
six evidence lengths: short, medium, long, extended, xlong (~4,600) and xxlong
(~10,000). The metadata records a
whitespace-token estimate because a model-specific tokenizer is not bundled;
the provider-reported per-call usage is the authoritative measurement.

Use one Inspect installation with the fixed conditions:

```json
{
  "model": "openai/gpt-5.6-luna",
  "tasks": ["ai_governance.inspect_tasks:incident_prompt_length_sweep"],
  "task_version": "incident-prompt-length-sweep-v4",
  "scorer": "ai_governance.inspect_tasks:governed_release_decision",
  "scorer_version": "1",
  "task_limit": 48,
  "token_limit": 32768,
  "timeout_seconds": 120,
  "max_connections": 2
}
```

Register two candidates using that same installation. Direct generation uses
one call per sample:

```json
{
  "evaluation_runner_config": {
    "solver": "generate",
    "solver_config": {},
    "model_args": {}
  }
}
```

Planner–executor uses an explicit JSON plan and then a final decision call:

```json
{
  "evaluation_runner_config": {
    "solver": "ai_governance.inspect_tasks:incident_planner_executor_generate",
    "solver_config": {
      "plan_schema_version": "planner-executor-plan/v1",
      "prompt_version": "planner-executor-prompts/v1",
      "executor_context_policy": "retained"
    },
    "model_args": {}
  }
}
```

Run a six-sample preflight first (`task_limit: 6` selects one incident in each
length band, including xlong and xxlong), then restore `task_limit: 48` and
submit two repetitions. The full experiment contains 192 sample results and
288 expected model calls.

`token_limit: 32768` is the fixed Inspect per-sample total-token bound. It is
shared by both candidates and is sized for the xxlong task appearing in both
the planning and retained-context execution calls, plus their bounded outputs.
It is used instead of OpenAI GPT-5's unsupported `max_tokens` request parameter.
This configured GPT-5 transport also requires the provider-default temperature,
so both candidates omit `temperature` rather than claiming an unsupported
zero-temperature condition. The provider rejects either unsupported option
during validation or run submission, before a worker job is dispatched.

Retrieve the durable, machine-readable report:

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/experiments/$EXPERIMENT_ID/report
```

The Studio **Results Report** tab presents the same data. It groups by
`length_band` when supplied and remains available for every evaluation provider.
It reports missing cost as `Unavailable`, not as a model-registry estimate.

For planner–executor samples, each persisted call explicitly records its role,
provider-reported input/output/total tokens, duration, whether it contains the
original task, and whether prior conversation was retained. Other providers or
scaffolds return `null` for facts they cannot reliably declare.

## Persistent review seed

The repository includes an idempotent local-review seed at
[`scripts/seed_inspect_prompt_length_sweep.sh`](../../scripts/seed_inspect_prompt_length_sweep.sh).
It prepares one named installation and one named experiment, but never removes,
rewrites, or backfills existing evidence.
When an installation is missing, the command validates its fixed settings
before saving it.

Before using it, start the current API and replay worker, obtain a short-lived
token as described in [Run an Inspect AI Batch Experiment](inspect-ai-batch-experiment.md),
and ensure the local demo assets are present. The normal local demo seed only
creates governed prompt/model/dataset references; it does not fabricate any
Inspect result.

```bash
curl --fail-with-body -X POST "${SCOPE[@]}" "$API/api/v1/local/demo/seed"

# Creates or retrieves the fixed installation, experiment and two candidates.
./scripts/seed_inspect_prompt_length_sweep.sh --prepare
```

The exact durable identifiers are intentionally stable:

```text
experiment name: inspect-prompt-length-sweep-v8
installation name: Inspect prompt-length sweep runner v8
request ID: inspect-prompt-length-sweep-v8
idempotency key: inspect-prompt-length-sweep-v8
```

First, submit and retain the small, six-sample preflight. It uses a separate
named installation with `task_limit: 6`, so it cannot change the immutable
conditions of the full seed. It checks one incident at each prompt-length band,
including both new bands, for both candidates.

```bash
./scripts/seed_inspect_prompt_length_sweep.sh --preflight
```

To spend the full model budget once, submit the 192-sample seed explicitly:

```bash
./scripts/seed_inspect_prompt_length_sweep.sh --submit
```

Running `--preflight` or `--submit` again sends the same immutable input and
returns the same job ID. It creates no additional worker job, evaluation run,
or sample result.
If an experiment with this name already exists, the script retrieves it rather
than changing its candidates; create a new versioned seed name for a changed
task, model, scorer, or solver configuration.

After completion, retain the returned `experiment_id` and inspect it at any
time. API/worker restarts preserve the SQLite or PostgreSQL records:

```bash
curl --fail-with-body "${SCOPE[@]}" \
  "$API/api/v1/experiments/$EXPERIMENT_ID/report" | jq .

curl --fail-with-body "${SCOPE[@]}" \
  "$API/api/v1/experiments/$EXPERIMENT_ID/runs" | jq .
```

Do not use `docker compose down -v` when the seed should remain reviewable: it
removes the named local volumes. `docker compose restart` and image rebuilds
preserve the durable records.
