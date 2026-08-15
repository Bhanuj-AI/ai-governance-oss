# Configure Runtime Connections

Runtime Connections are tenant-owned operational resources for registered-model
runtime use. They hold a runtime provider, non-sensitive
endpoint configuration, scope, enabled state and **secret references**. They
do not store credentials and are not part of an immutable model version.

This guide is deliberately separate from
[evaluation provider installations](./configure-evaluation-provider-installations.md).
Provider installations configure evaluators such as TruLens; Runtime
Connections configure a user's model runtime.

## Before you begin

- Register a managed model provider that is allowed by
  `model_registry.allowed_runtime_providers` in the selected organization or
  project.
- Make the referenced secret available to the API process. For local OSS,
  `env://` references resolve from that process environment.
- Use a durable settings backend (`sqlite` or `postgres`) if connections must
  survive a restart. The development-only `inmemory` backend does not persist
  them.

For example, set a tenant runtime credential with a purpose-specific variable:

```bash
export OPENAI_DEVELOPMENT_API_KEY='…'
export ANTHROPIC_DEVELOPMENT_API_KEY='…'
```

Do not reuse `OPENAI_API_KEY` merely because it exists. That variable is a
deployment-owned platform credential for internal OpenAI-backed evaluation or
judge flows; it is not a tenant Runtime Connection.

## Create Connection in Studio

1. Open **Settings → Runtime Connections**.
2. Select **New Runtime Connection**.
3. Enter an operator-facing name, such as `OpenAI Development`.
4. Select the runtime provider. OSS provides native model discovery and
   candidate execution for **OpenAI** and **Anthropic**. An
   **OpenAI-compatible custom** endpoint can execute an operator-supplied
   registered model identifier. A provider shown as unavailable is blocked by
   the allowed-managed-model-provider policy.
5. Set the provider configuration:

   | Provider | API key reference | Base URL | Organization |
   | --- | --- | --- | --- |
   | OpenAI | Required | Optional | Optional |
   | Anthropic | Required | Optional | Not used |
   | OpenAI-compatible custom | Optional | Required | Optional |

   For an OpenAI development connection, use
   `env://OPENAI_DEVELOPMENT_API_KEY`; for Anthropic, use a purpose-specific
   reference such as `env://ANTHROPIC_DEVELOPMENT_API_KEY`. Never paste an API
   key into this form.
6. Choose a scope:
   - **Organization**: shared by projects in the organization.
   - **Current project**: visible only in the selected project.
7. Select **Test Connection**. In the current OSS implementation this validates
   provider configuration and confirms that each secret reference can be
   resolved. It does **not** send a request to the provider or invoke a model.
8. Leave **Active** selected and create the connection. Active connections must
   pass validation before Studio permits saving; the API validates again.

The list records Active/Disabled state and the last validation result. Use
**Edit** to rotate a secret reference or update a base URL. This updates the
connection; it never creates a new model version.

## Use the REST API

First inspect the OSS connection types and their tenant policy:

```bash
curl "$AI_GOVERNANCE_API_URL/api/v1/runtime-connections/providers" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "X-AI-Governance-Organization-Id: org_example" \
  -H "X-AI-Governance-Project-Id: project_example"
```

Validate an unsaved OpenAI connection:

```bash
curl -X POST "$AI_GOVERNANCE_API_URL/api/v1/runtime-connections/validate" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -H "X-AI-Governance-Organization-Id: org_example" \
  -H "X-AI-Governance-Project-Id: project_example" \
  -d '{
    "display_name": "OpenAI Development",
    "provider": "openai",
    "settings": {"organization": "org_example"},
    "secret_refs": {"api_key": "env://OPENAI_DEVELOPMENT_API_KEY"},
    "enabled": true,
    "scope": "PROJECT"
  }'
```

Create the validated connection with the same payload, using
`POST /api/v1/runtime-connections`. The response contains a
`runtime_connection_id`, status, scope, timestamps, and test state—but never a
resolved secret.

To test a saved connection, call:

```bash
curl -X POST "$AI_GOVERNANCE_API_URL/api/v1/runtime-connections/<connection-id>/test" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "X-AI-Governance-Organization-Id: org_example" \
  -H "X-AI-Governance-Project-Id: project_example"
```

Use `PATCH /api/v1/runtime-connections/<connection-id>` to change
`display_name`, `settings`, `secret_refs`, or `enabled`. Provider and scope are
fixed at creation so the connection identity and tenant ownership remain
clear.

## Bind a connection to an experiment candidate

When adding a candidate in **Experiments → Candidates**, choose its **Runtime
connection** after selecting the model version. An enabled, provider-compatible
connection is required when that candidate is run; the API performs the same
operation with `runtime_connection_id`:

```bash
curl -X POST "$AI_GOVERNANCE_API_URL/api/v1/experiments/<experiment-id>/candidates" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -H "X-AI-Governance-Organization-Id: org_example" \
  -H "X-AI-Governance-Project-Id: project_example" \
  -d '{
    "candidate_name": "OpenAI candidate",
    "prompt_version": "<prompt-id>:v1",
    "model_version": "<model-id>:v1",
    "dataset_version": "<dataset-id>:v1",
    "provider_name": "mock",
    "runtime_connection_id": "<connection-id>",
    "runtime_parameters": {"temperature": 0.2, "top_p": 1, "max_tokens": 512}
  }'
```

At creation, AI Governance Control Plane verifies the connection is visible in
the selected tenant scope, enabled, and compatible with the managed model's
provider. It stores only the ID on the immutable candidate configuration. At
experiment execution, the Candidate Execution Runtime resolves the current
secret reference in memory, renders the immutable prompt against every record
in the immutable dataset version, invokes the registered model, and persists a
secret-free `WorkflowExecution` record for each dataset item. Evaluators consume
those persisted records; they do not reconstruct prompts or call the candidate
model themselves. The run is marked `EXECUTION_FAILED` if any candidate
invocation fails, and evaluation does not proceed for that candidate.

All candidates in one experiment must use the same dataset identity and version.
This makes the evaluated item set identical before scores are compared. Per-item
evaluation results are retained as evidence and the experiment result uses the
mean of each metric across that shared item set.

The same rule applies when an experiment is submitted as an asynchronous job:
the worker reconstructs the tenant context captured on the job, then resolves
the candidate's connection in that scope, executes and persists the same
per-item evidence, then evaluates that evidence. The job payload carries no
credential and does not need a copied connection configuration.

## Operational Signals

Candidate execution emits structured application log messages for resolution,
model invocation, durable evidence persistence, evaluator aggregation, and
failure. Correlate them with `experiment_id`, `candidate_id`, `run_id`, and
`execution_id`. The logs deliberately omit prompt text, dataset contents,
model output, and credentials. Completion logs include provider request ID,
latency, token counts, and finish reason when the runtime returns them.

The same lifecycle is available to extensions through the generic
`ResourceLifecycleEvent` contract with `resource_kind="candidate_execution"`
and `started`, `completed`, or `failed` states. Its payload is likewise
secret-free and contains only stable IDs and runtime telemetry.

## Credential rotation and Isolation

- Rotate a credential by updating only `secret_refs`, for example from
  `env://OPENAI_DEVELOPMENT_API_KEY_V1` to
  `env://OPENAI_DEVELOPMENT_API_KEY_V2`.
- Re-test after rotation, then keep the connection Active.
- A project-scoped connection cannot be read or changed from another project or
  organization. Organization-scoped connections are visible to the projects in
  that organization.
- The `runtime_connection.manage` permission is required for writes. Read
  access follows the evaluation-read capability.

## Current OSS Boundary

Runtime Connections are the governed execution path for native OpenAI and
Anthropic models. Candidate creation verifies the selected connection is
tenant-visible, active, and compatible with the registered model provider.
During experiment execution, the runtime resolves the current secret reference
only in memory, invokes the registered provider model, and writes secret-free
execution evidence. No resolved value is persisted in a candidate, run, API
response, job payload, or log.

For a provider that is not OpenAI-compatible, implement and test a native
runtime adapter, model-catalog discovery path, and immutable capability profile
in an OSS contribution or a maintained fork. Adding a value to
`model_registry.allowed_runtime_providers` changes tenant policy only; it does
not add a provider implementation.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Provider is absent or unavailable | Check `model_registry.allowed_runtime_providers` for the selected tenant scope. OSS exposes only OpenAI, Anthropic, and OpenAI-compatible custom connection types. |
| Test fails | Confirm the API process—not only your shell—has the referenced environment variable. The response intentionally does not reveal a secret or its value. |
| OpenAI/Anthropic cannot be saved as Active | Supply an `api_key` secret reference using an allowed scheme such as `env://NAME`. |
| Custom connection cannot be saved | Supply an absolute `http://` or `https://` `base_url`. |
| Connection disappears after restart | Configure `AI_GOVERNANCE_SETTINGS_REPOSITORY=sqlite` or `postgres`; `inmemory` is ephemeral. |
