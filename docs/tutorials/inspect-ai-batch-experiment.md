# Run an Inspect AI Batch Experiment

This tutorial runs the packaged Inspect smoke experiment end to end:

```text
REST API → queued job → replay worker → persisted runs and samples → results APIs
```

It uses two solver scaffolds and two repetitions. It is an operational smoke
test of the integration, not evidence that one scaffold is generally better.

## What You Will Run

One provider installation holds the fixed conditions. The candidates hold the
only experimental difference: their solver.

| Candidate | Solver | Repetitions |
| --- | --- | --- |
| `generate` | Inspect `generate` | 2 |
| `plan_then_generate` | `ai_governance.inspect_tasks:plan_then_generate` | 2 |

The bundled task, `ai_governance.inspect_tasks:scaffold_smoke`, has ten short,
deterministic samples with exact answers. The expected execution shape is:

```text
2 candidates × 2 repetitions = 4 runner invocations
4 runner invocations × 10 samples = 40 persisted sample results
```

Inspect is a `BATCH` provider: one invocation produces several sample results.
The platform stores one evaluation run for each candidate/repetition and ten
child results beneath each run. Do not submit the task once per sample.

## Prerequisites

1. Install the optional dependency for local commands:

   ```bash
   uv sync --extra inspect
   ```

2. Make `OPENAI_API_KEY` available to both API and worker. For the Docker
   stack, place it in `.env.platform`. Do not put it in provider installation
   settings, candidate metadata, requests, or provenance.

3. Build and start the API and worker from the current checkout:

   ```bash
   docker compose up -d --build ai-governance-platform ai-governance-replay-worker
   ```

4. Verify that both runtime containers load the same packaged task:

   ```bash
   docker compose exec -T ai-governance-platform \
     /opt/ai-governance-venv/bin/python -c \
     "from ai_governance.inspect_tasks import scaffold_smoke; print(scaffold_smoke)"

   docker compose exec -T ai-governance-replay-worker \
     /opt/ai-governance-venv/bin/python -c \
     "from ai_governance.inspect_tasks import scaffold_smoke; print(scaffold_smoke)"
   ```

   Both commands must print a callable from `ai_governance.inspect_tasks`.
   `path/to/task.py` is intentionally rejected: a host-local path is not
   reproducible evidence in an API/worker deployment.

## Authenticate the CLI Session

The local Docker stack uses Keycloak. `./servers.sh` creates
`.env.oauth.generated`; use it to hold a short-lived token only in your shell:

```bash
set -a
source .env.oauth.generated
set +a

ACCESS_TOKEN="$(uv run python -c '
from ai_governance.oauth.client_credentials import access_token_from_environment
print(access_token_from_environment())
')"

API=http://127.0.0.1:8000
SCOPE=(
  -H "Authorization: Bearer $ACCESS_TOKEN"
  -H 'X-AI-Governance-Organization-Id: org_default'
  -H 'X-AI-Governance-Project-Id: project_default'
  -H 'Content-Type: application/json'
)
```

Use your own organization and project IDs outside the local stack. Clear the
token when finished:

```bash
unset ACCESS_TOKEN
```

## Create and Validate the Shared Installation

Save the fixed configuration in a shell variable. It has no `solver` field.
The solver is a candidate-level experimental variable.

```bash
INSPECT_SETTINGS='{
  "model": "openai/gpt-5.6-luna",
  "tasks": ["ai_governance.inspect_tasks:scaffold_smoke"],
  "task_version": "smoke-v1",
  "scorer": "exact",
  "scorer_version": "1",
  "task_limit": 10,
  "timeout_seconds": 60,
  "max_connections": 2
}'

curl --fail-with-body -X POST "${SCOPE[@]}" \
  "$API/api/v1/provider-installations/validate" \
  --data "{
    \"provider_type\": \"inspect_ai\",
    \"display_name\": \"Inspect smoke runner\",
    \"settings\": $INSPECT_SETTINGS,
    \"secret_refs\": {},
    \"enabled\": true,
    \"scope\": \"PROJECT\"
  }"
```

If validation succeeds, create it once and retain its ID:

```bash
INSTALLATION="$(curl --fail-with-body -X POST "${SCOPE[@]}" \
  "$API/api/v1/provider-installations" \
  --data "{
    \"provider_type\": \"inspect_ai\",
    \"display_name\": \"Inspect smoke runner\",
    \"settings\": $INSPECT_SETTINGS,
    \"secret_refs\": {},
    \"enabled\": true,
    \"scope\": \"PROJECT\"
  }")"
INSTALLATION_ID="$(printf '%s' "$INSTALLATION" | jq -r .installation_id)"
```

## Tool-Enabled Runner Safety Gate

Only declare `requires_tools: true` on a candidate whose packaged solver really
calls function tools. This tells the adapter to check the resolved model and
transport before any job is queued. The known unsupported OpenAI GPT-5 +
Inspect Chat Completions tool path is rejected by both installation validation
and run submission; a rejection means no worker invocation was created.

Every Inspect `timeout_seconds` is also a worker deadline, not merely a hint to
the provider. If the provider does not return before that deadline, the worker
records a failed evaluation run with the timeout reason and can continue with
other jobs.

Before operating a tool-enabled run, set up a separate emergency operator. The
identity needs an active membership and `PLATFORM_OPERATOR` in the experiment's
organization or project. An organization administrator can assign that role:

```bash
EMERGENCY_ACTOR_ID="inspect-emergency-operator"
PROJECT_ID="project_default"

curl --fail-with-body -X POST "${SCOPE[@]}" \
  "$API/api/v1/organizations/org_default/role-assignments" \
  --data "{
    \"actor_id\": \"$EMERGENCY_ACTOR_ID\",
    \"role\": \"PLATFORM_OPERATOR\",
    \"project_id\": \"$PROJECT_ID\"
  }"
```

Authenticate as that identity and verify the emergency brake before dispatch:

```bash
curl --fail-with-body "${SCOPE[@]}" "$API/api/v1/context" \
  | jq '.permissions | index("job.cancel")'
# Expected output: a number (not null)
```

Use that identity, not the normal worker, to issue
`POST /api/v1/jobs/{job_id}/cancel` when an operator must stop a run.

## Choose Comparable Assets

Candidates must use the same prompt, model, dataset, runtime conditions, and
provider installation. List the assets available to the selected tenant:

```bash
curl --fail-with-body "${SCOPE[@]}" "$API/api/v1/prompts" | jq .
curl --fail-with-body "${SCOPE[@]}" "$API/api/v1/models" | jq .
curl --fail-with-body "${SCOPE[@]}" "$API/api/v1/datasets" | jq .
```

The current experiment API accepts these candidate references in
`id:version` form, despite the request field names ending in `_version`:

```text
prompt_version:  prompt-id:prompt-version
model_version:   model-id:model-version
dataset_version: dataset-id:dataset-version
```

For the local seeded stack, the references are:

```text
demo-prompt-support-v1:v1.0
demo-model-general-v1:2026.01
demo-dataset-evaluation:v1.0
```

## Create Experiment and Candidates

Use a unique name for each run of this tutorial.

```bash
REQUEST_ID="inspect-smoke-$(date +%s)"

EXPERIMENT="$(curl --fail-with-body -X POST "${SCOPE[@]}" \
  "$API/api/v1/experiments" \
  --data "{
    \"name\": \"$REQUEST_ID\",
    \"description\": \"Inspect batch smoke experiment\",
    \"metadata\": {\"owner\": \"operator\"}
  }")"
EXPERIMENT_ID="$(printf '%s' "$EXPERIMENT" | jq -r .experiment_id)"
```

Add the `generate` candidate:

```bash
curl --fail-with-body -X POST "${SCOPE[@]}" \
  "$API/api/v1/experiments/$EXPERIMENT_ID/candidates" \
  --data "{
    \"candidate_name\": \"generate\",
    \"prompt_version\": \"demo-prompt-support-v1:v1.0\",
    \"model_version\": \"demo-model-general-v1:2026.01\",
    \"dataset_version\": \"demo-dataset-evaluation:v1.0\",
    \"provider_installation_id\": \"$INSTALLATION_ID\",
    \"metadata\": {
      \"evaluation_runner_config\": {
        \"solver\": \"generate\",
        \"solver_config\": {}
      }
    }
  }"
```

Add the packaged planning variant. Change only the solver fields:

```bash
curl --fail-with-body -X POST "${SCOPE[@]}" \
  "$API/api/v1/experiments/$EXPERIMENT_ID/candidates" \
  --data "{
    \"candidate_name\": \"plan_then_generate\",
    \"prompt_version\": \"demo-prompt-support-v1:v1.0\",
    \"model_version\": \"demo-model-general-v1:2026.01\",
    \"dataset_version\": \"demo-dataset-evaluation:v1.0\",
    \"provider_installation_id\": \"$INSTALLATION_ID\",
    \"metadata\": {
      \"evaluation_runner_config\": {
        \"solver\": \"ai_governance.inspect_tasks:plan_then_generate\",
        \"solver_config\": {\"planning_prompt_version\": \"v1\"}
      }
    }
  }"
```

## Submit Queued Experiment

An `idempotency_key` makes this asynchronous. Set `max_attempts` to one for a
controlled smoke run.

```bash
RUN_REQUEST="{
  \"repetitions\": 2,
  \"request_id\": \"$REQUEST_ID\",
  \"idempotency_key\": \"$REQUEST_ID\",
  \"submitted_by\": \"operator\",
  \"max_attempts\": 1
}"

JOB="$(curl --fail-with-body -X POST "${SCOPE[@]}" \
  "$API/api/v1/experiments/$EXPERIMENT_ID/run" \
  --data "$RUN_REQUEST")"
JOB_ID="$(printf '%s' "$JOB" | jq -r .job_id)"
```

Submit the identical request once more. The returned `job_id` must be the same;
do not submit a new key to test idempotency.

```bash
curl --fail-with-body -X POST "${SCOPE[@]}" \
  "$API/api/v1/experiments/$EXPERIMENT_ID/run" \
  --data "$RUN_REQUEST" | jq '{job_id, status}'
```

Poll until the real worker reports a terminal state:

```bash
while true; do
  JOB_STATUS="$(curl --fail-with-body "${SCOPE[@]}" \
    "$API/api/v1/jobs/$JOB_ID")"
  printf '%s\n' "$JOB_STATUS" | jq '{job_id, status, result_ref, failure_reason}'
  STATUS="$(printf '%s' "$JOB_STATUS" | jq -r .status)"
  case "$STATUS" in SUCCEEDED|FAILED|CANCELLED) break ;; esac
  sleep 5
done
```

## Verify Results and Durability

List the four runs. All must be `COMPLETED`, with ten total, completed, and
evaluated items each.

```bash
RUNS="$(curl --fail-with-body "${SCOPE[@]}" \
  "$API/api/v1/experiments/$EXPERIMENT_ID/runs")"
printf '%s' "$RUNS" | jq '[.[] | {
  run_id, candidate_id, status,
  total_item_count, completed_item_count, evaluated_item_count,
  fingerprint: .runner_provenance.configuration_fingerprint
}]'
```

Inspect one run's child results:

```bash
RUN_ID="$(printf '%s' "$RUNS" | jq -r '.[0].run_id)"
curl --fail-with-body "${SCOPE[@]}" \
  "$API/api/v1/experiments/$EXPERIMENT_ID/runs/$RUN_ID/evaluations?page=1&page_size=20" \
  | jq '{total_items, item_count: (.items | length), items}'
```

Read the aggregate views:

```bash
curl --fail-with-body "${SCOPE[@]}" \
  "$API/api/v1/experiments/$EXPERIMENT_ID/leaderboard" | jq .

# Substitute the two candidate IDs returned when they were created.
curl --fail-with-body "${SCOPE[@]}" \
  "$API/api/v1/experiments/$EXPERIMENT_ID/comparison?baseline_candidate_id=<generate-id>&comparison_candidate_id=<plan-id>" \
  | jq .
```

Finally, restart the API and worker without deleting the named SQLite volume:

```bash
docker compose restart ai-governance-platform ai-governance-replay-worker
```

Repeat the run, child-result, leaderboard, and comparison reads. The records
must still be present. Resubmit the *same* `RUN_REQUEST`: it must return the
same completed `JOB_ID`, and `/runs` must still contain exactly four runs.

## Studio Workflow

1. Open **Assets → Evaluation Providers** and create one enabled `inspect_ai`
   installation using the fixed settings above. Select **Validate Connection**
   before saving.
2. Open **Experiments**, create an experiment, and add two candidates with the
   same prompt, model, dataset, and provider installation.
3. In each candidate's **Inspect runner variant JSON** field, enter one of the
   two `evaluation_runner_config` values above.
4. Set **Repetitions** to `2`, then start the experiment. The confirmation
   should describe four runner invocations and forty sample results.
5. In the completed experiment, open each run to inspect the child results and
   runner fingerprint; then inspect the leaderboard and candidate comparison.

## Interpret Smoke Result

The smoke samples are intentionally easy. Equal accuracy only proves that both
scaffolds and the persistence path work. Compare tokens and latency as an
efficiency signal, but do not claim scaffold superiority until representative
agent tasks exercise planning or tool behavior under the same controlled setup.

## Studio Build Note

Run the repository checks before releasing Studio changes:

```bash
pnpm typecheck
pnpm build
```

If the pnpm/Turbopack path stalls, capture its process CPU and memory, then run
the underlying diagnostics:

```bash
./node_modules/.bin/tsc --noEmit --extendedDiagnostics
./node_modules/.bin/next build --webpack
```

Those direct commands isolate a toolchain problem, but they do not make a
required CI `pnpm build` check optional.
