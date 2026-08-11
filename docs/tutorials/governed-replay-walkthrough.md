# Governed Replay Walkthrough

`ai-governance walkthrough governed-replay` is the first guided AI Governance Control Plane product
experience. It demonstrates one governed lifecycle using only the public REST
API that Studio and external producers use. It is not a second application
layer, a repository client, or a privileged demo path.

The walkthrough is intentionally narrow and deterministic:

```text
Observed prompt and model evidence
        ↓
Registered evaluation dataset + replayable source execution
        ↓
Baseline evaluation + governance decision evidence
        ↓
Prepared replay → optional durable replay job
        ↓
Ontology and Studio inspection links + run manifest
```

It does not claim that a replay, evaluation, comparison, or drift result exists
until the normal worker lifecycle has created it.

## Prerequisites

Start the local stack and wait until the seeded demo data is available:

```bash
./servers.sh
```

The initial scenario selects the seeded `demo-dataset-evaluation` dataset and a
tenant-scoped replayable source execution. It records two observed assets with
stable walkthrough identities, so repeat runs are idempotent at the public API
boundary.

For a Keycloak-enabled local stack, the walkthrough automatically obtains a
short-lived token in memory using its configured `AI_GOVERNANCE_OAUTH_*` client
credentials. No bearer token export is required. Existing local stacks can
temporarily use their `AI_GOVERNANCE_MCP_*` credentials through the compatibility
fallback. For a development-mode API, no token is required.

```bash
export AI_GOVERNANCE_API_URL=http://localhost:8000
export AI_GOVERNANCE_STUDIO_URL=http://localhost:3000
```

For a production or CI workload, provision a dedicated least-privilege
confidential client and configure its client credentials in a secret manager or
protected CI environment. The CLI exchanges them itself; do not create or
export a bearer token:

```bash
export AI_GOVERNANCE_OAUTH_TOKEN_URL=https://keycloak.example/realms/ai-governance/protocol/openid-connect/token
export AI_GOVERNANCE_OAUTH_CLIENT_ID=ai-governance-walkthrough
export AI_GOVERNANCE_OAUTH_CLIENT_SECRET=replace-with-a-client-secret
```

The resulting token represents the walkthrough service account, not an
organization administrator or an impersonated human user. AI Governance Control Plane still checks
that subject's membership and RBAC permissions in the selected tenant. The CLI
never writes the token to the manifest, a file, or terminal output.

If a caller must use a pre-obtained bearer token, supply it deliberately with
`--token`. The CLI does not read `AI_GOVERNANCE_TOKEN` from the shell, so a stale
global export cannot override the configured workload identity.

The local Keycloak realm declares this client as `ai-governance-walkthrough`. Its
service-account subject is discovered during `./servers.sh` and provisioned as a
separate AI Governance Control Plane actor. Keycloak imports a realm JSON file only when the realm is
created. After changing `keycloak-postgres/keycloak/ai-governance-realm.json`, an
existing local Keycloak volume must either be updated through the Keycloak
Admin Console or recreated before the new client appears:

```bash
# Local Keycloak data only — removes local Keycloak users and realm state.
cd keycloak-postgres
docker compose --env-file .env.keycloak down -v
cd ..
./servers.sh
```

The defaults are `org_default` and `project_default`. Override them if you are
running the scenario in another permitted tenant:

```bash
export AI_GOVERNANCE_ORGANIZATION_ID=org_default
export AI_GOVERNANCE_PROJECT_ID=project_default
```

## Run Golden Path

Install the project dependencies first if you are running from a source clone:

```bash
uv sync
uv run ai-governance walkthrough governed-replay
```

The command prints an operator-oriented list of completed, pending, and
skipped steps. Each completed item includes a Studio URL. It also writes a
machine-readable manifest below the current directory:

```text
.ai-governance/walkthroughs/governed-replay-20260720T000000Z-walkthrough-abc123.json
```

The manifest captures exactly what happened, including the API contract version,
tenant, prompt/model/dataset/execution/evaluation/decision/replay IDs,
API-derived step states, and inspection URLs. Keep it with demo, CI, or
release-validation output instead of copying IDs out of terminal logs.

## Deterministic & CI Use

The first walkthrough does not prompt for input. Pass `--non-interactive` to
make that intention explicit in scripts, and `--output-json` to emit the full
manifest on stdout:

```bash
uv run ai-governance walkthrough governed-replay \
  --non-interactive \
  --output-json \
  --manifest artifacts/governed-replay-manifest.json
```

To choose a known source execution rather than using the first replayable one:

```bash
uv run ai-governance walkthrough governed-replay \
  --source-execution-id demo-source-execution-01
```

## Restart & Cleanup Behaviour

Every completed public-API step checkpoints the manifest. If a request fails,
the command exits non-zero and the manifest is marked `FAILED` with the exact
resource IDs safely recorded before the failure. Re-run the same walkthrough to
continue through the normal idempotent public contracts: the stable observed
prompt/model identities and replay idempotency key are reused rather than
creating duplicate records.

Walkthrough manifests are local diagnostics only; they never delete governed
assets. Preview aged local manifests before removing them:

```bash
uv run ai-governance walkthrough cleanup --older-than-days 14
uv run ai-governance walkthrough cleanup --older-than-days 14 --apply
```

`--apply` is required for deletion and the command only considers direct JSON
files under `.ai-governance/walkthroughs/` in the current directory.

## Release Smoke Testing

The release smoke script invokes the installed CLI twice against a running API,
validates the v1 response contract, asserts the final manifest's resource IDs
and Studio deep links, and verifies that both runs resolve the same resources.
It does not know or care whether the running stack uses SQLite or PostgreSQL.

```bash
AI_GOVERNANCE_SMOKE_API_URL=http://localhost:8000 \
AI_GOVERNANCE_SMOKE_STUDIO_URL=http://localhost:3000 \
uv run python smoke_tests/smoke_governed_replay_walkthrough.py
```

In Keycloak mode the smoke command uses `AI_GOVERNANCE_OAUTH_*` automatically. Pass
`AI_GOVERNANCE_SMOKE_TOKEN` only when release infrastructure intentionally supplies
an explicit bearer token; `AI_GOVERNANCE_TOKEN` is ignored. Development-mode stacks
need neither client credentials nor a token.

Run the same command against a fresh SQLite deployment and a fresh PostgreSQL
deployment in release validation. The test uses only the normal `ai-governance` CLI
and public REST API. A changed or incompatible API response fails clearly via
the scenario's declared `api_version: v1` contract; a new API version should
receive its own scenario adapter instead of silently changing this walkthrough.

## Submit Replay Deliberately

By default the walkthrough prepares the replay only. This makes the first run
safe for onboarding and keeps long-running work explicit. To queue the normal
replay job, opt in:

```bash
uv run ai-governance walkthrough governed-replay --submit-replay
```

The command reports the job as queued and links to the replay detail page. The
worker then executes the ordinary lifecycle. Open the detail page to submit the
evaluation once the replay execution is complete; AI Governance Control Plane will then create the
comparison and drift evidence through the same normal worker contracts.

## Scenario API Calls

The version-controlled declaration is
[`examples/governed-replay/scenario.yaml`](../../examples/governed-replay/scenario.yaml).
Its prompt fixture lives beside it. The runtime calls only these public
endpoints:

- `POST /api/v1/prompts/observations`
- `POST /api/v1/models/observations`
- `GET /api/v1/datasets`
- `GET /api/v1/replay-executions/search`
- `GET /api/v1/evaluations/history/{execution_id}`
- `GET /api/v1/decisions` and `GET /api/v1/decisions/{decision_id}/detail`
- `POST /api/v1/replays` and, only with `--submit-replay`, `POST /api/v1/replays/{replay_id}/submit`
- `GET /api/v1/ontology/entities/PromptVersion/{prompt_id}/neighbourhood`

Ontology projection is eventually consistent. If the observed prompt has not
been projected yet, the walkthrough records `PENDING_PROJECTION` and still
provides the Studio graph URL. This is an honest state, not a failed demo.

## Extennsions

Do not add repository calls, direct SQLite inspection, or custom governance
logic to a scenario. New walkthroughs should be versioned under `examples/`,
orchestrate documented public API contracts, emit an equivalent run manifest,
and have tests that exercise the request sequence through a fake REST client.

As the normal deterministic CLI grows, reusable commands can be extracted from
this experience. The walkthrough remains the integration layer that proves how
the existing product planes compose.
