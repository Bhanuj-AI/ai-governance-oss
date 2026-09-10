#!/usr/bin/env bash
# Create (or retrieve) one durable Inspect prompt-length sweep and, when
# requested, submit its one idempotent evaluation job. The script never
# deletes or replaces persisted evidence.
set -euo pipefail

MODE="${1:-}"
if [[ "$MODE" != "--submit" && "$MODE" != "--prepare" && "$MODE" != "--preflight" ]]; then
  echo "Usage: $0 --prepare|--preflight|--submit" >&2
  exit 64
fi

: "${ACCESS_TOKEN:?Set ACCESS_TOKEN to a short-lived control-plane token.}"

API="${AI_GOVERNANCE_API_URL:-http://127.0.0.1:8000}"
ORGANIZATION_ID="${AI_GOVERNANCE_ORGANIZATION_ID:-org_default}"
PROJECT_ID="${AI_GOVERNANCE_PROJECT_ID:-project_default}"
if [[ "$MODE" == "--preflight" ]]; then
  SEED_ID="inspect-prompt-length-sweep-v7-preflight"
  EXPERIMENT_NAME="$SEED_ID"
  INSTALLATION_NAME="Inspect prompt-length sweep preflight runner v7"
  TASK_LIMIT=4
  REPETITIONS=1
else
  SEED_ID="inspect-prompt-length-sweep-v7"
  EXPERIMENT_NAME="$SEED_ID"
  INSTALLATION_NAME="Inspect prompt-length sweep runner v7"
  TASK_LIMIT=32
  REPETITIONS=2
fi
PROMPT_REFERENCE="${AI_GOVERNANCE_SWEEP_PROMPT_REFERENCE:-demo-prompt-support-v1:v1.0}"
MODEL_REFERENCE="${AI_GOVERNANCE_SWEEP_MODEL_REFERENCE:-demo-model-general-v1:2026.01}"
DATASET_REFERENCE="${AI_GOVERNANCE_SWEEP_DATASET_REFERENCE:-demo-dataset-evaluation:v1.0}"

SCOPE=(
  -H "Authorization: Bearer ${ACCESS_TOKEN}"
  -H "X-AI-Governance-Organization-Id: ${ORGANIZATION_ID}"
  -H "X-AI-Governance-Project-Id: ${PROJECT_ID}"
  -H "Content-Type: application/json"
)

request() {
  curl --fail-with-body --silent --show-error "${SCOPE[@]}" "$@"
}

settings='{
  "model": "openai/gpt-5.6-luna",
  "tasks": ["ai_governance.inspect_tasks:incident_prompt_length_sweep"],
  "task_version": "incident-prompt-length-sweep-v3",
  "scorer": "ai_governance.inspect_tasks:governed_release_decision",
  "scorer_version": "1",
  "task_limit": '"$TASK_LIMIT"',
  "token_limit": 8192,
  "timeout_seconds": 120,
  "max_connections": 2
}'

installations="$(request "$API/api/v1/provider-installations")"
installation_matches="$(jq --arg name "$INSTALLATION_NAME" '
  [.[] | select(.display_name == $name and .provider_type == "inspect_ai")]
' <<<"$installations")"
installation_count="$(jq length <<<"$installation_matches")"
if [[ "$installation_count" -gt 1 ]]; then
  echo "More than one '$INSTALLATION_NAME' installation exists; refusing to choose or modify one." >&2
  exit 65
fi
if [[ "$installation_count" -eq 0 ]]; then
  request -X POST "$API/api/v1/provider-installations/validate" --data "{
    \"provider_type\": \"inspect_ai\",
    \"display_name\": \"$INSTALLATION_NAME\",
    \"settings\": $settings,
    \"secret_refs\": {},
    \"enabled\": true,
    \"scope\": \"PROJECT\"
  }" >/dev/null
  installation="$(request -X POST "$API/api/v1/provider-installations" --data "{
    \"provider_type\": \"inspect_ai\",
    \"display_name\": \"$INSTALLATION_NAME\",
    \"settings\": $settings,
    \"secret_refs\": {},
    \"enabled\": true,
    \"scope\": \"PROJECT\"
  }")"
  installation_id="$(jq -r .installation_id <<<"$installation")"
else
  installation_id="$(jq -r '.[0].installation_id' <<<"$installation_matches")"
fi

experiments="$(request "$API/api/v1/experiments")"
experiment_matches="$(jq --arg name "$EXPERIMENT_NAME" '
  [.[] | select(.name == $name)]
' <<<"$experiments")"
experiment_count="$(jq length <<<"$experiment_matches")"
if [[ "$experiment_count" -gt 1 ]]; then
  echo "More than one '$EXPERIMENT_NAME' experiment exists; refusing to choose or modify one." >&2
  exit 65
fi
create_candidates=false
if [[ "$experiment_count" -eq 0 ]]; then
  experiment="$(request -X POST "$API/api/v1/experiments" --data "{
    \"name\": \"$EXPERIMENT_NAME\",
    \"description\": \"Durable prompt-length sweep: direct generation versus planner-executor.\",
    \"metadata\": {\"owner\": \"local-review-seed\", \"seed_version\": \"$SEED_ID\"}
  }")"
  experiment_id="$(jq -r .experiment_id <<<"$experiment")"
  create_candidates=true
else
  experiment_id="$(jq -r '.[0].experiment_id' <<<"$experiment_matches")"
  existing_candidates="$(request "$API/api/v1/experiments/$experiment_id/candidates")"
  candidate_count="$(jq length <<<"$existing_candidates")"
  if [[ "$candidate_count" -eq 0 ]]; then
    create_candidates=true
  elif [[ "$candidate_count" -ne 2 ]] || ! jq -e --arg installation "$installation_id" '
    ([.[].candidate_name] | sort) == ["direct-generation", "planner-executor"]
    and all(.[]; .provider_installation_id == $installation)
  ' >/dev/null <<<"$existing_candidates"; then
    echo "Existing seed experiment does not match the expected immutable candidates; refusing to alter evidence." >&2
    exit 65
  fi
fi

if [[ "$create_candidates" == true ]]; then

  request -X POST "$API/api/v1/experiments/$experiment_id/candidates" --data "{
    \"candidate_name\": \"direct-generation\",
    \"prompt_version\": \"$PROMPT_REFERENCE\",
    \"model_version\": \"$MODEL_REFERENCE\",
    \"dataset_version\": \"$DATASET_REFERENCE\",
    \"provider_installation_id\": \"$installation_id\",
    \"metadata\": {\"evaluation_runner_config\": {
      \"solver\": \"generate\", \"solver_config\": {},
      \"model_args\": {}
    }}
  }" >/dev/null
  request -X POST "$API/api/v1/experiments/$experiment_id/candidates" --data "{
    \"candidate_name\": \"planner-executor\",
    \"prompt_version\": \"$PROMPT_REFERENCE\",
    \"model_version\": \"$MODEL_REFERENCE\",
    \"dataset_version\": \"$DATASET_REFERENCE\",
    \"provider_installation_id\": \"$installation_id\",
    \"metadata\": {\"evaluation_runner_config\": {
      \"solver\": \"ai_governance.inspect_tasks:incident_planner_executor_generate\",
      \"solver_config\": {
        \"plan_schema_version\": \"planner-executor-plan/v1\",
        \"prompt_version\": \"planner-executor-prompts/v1\",
        \"executor_context_policy\": \"retained\"
      },
      \"model_args\": {}
    }}
  }" >/dev/null
fi

echo "experiment_id=$experiment_id"
echo "installation_id=$installation_id"
echo "report=$API/api/v1/experiments/$experiment_id/report"

if [[ "$MODE" != "--prepare" ]]; then
  job="$(request -X POST "$API/api/v1/experiments/$experiment_id/run" --data "{
    \"repetitions\": $REPETITIONS,
    \"request_id\": \"$SEED_ID\",
    \"idempotency_key\": \"$SEED_ID\",
    \"submitted_by\": \"local-review-seed\",
    \"requested_by\": \"local-review-seed\",
    \"reason\": \"Persist the prompt-length sweep for later review.\",
    \"max_attempts\": 1
  }")"
  echo "job_id=$(jq -r .job_id <<<"$job")"
fi
