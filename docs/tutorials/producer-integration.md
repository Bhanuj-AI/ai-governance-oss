# Producer Integration Guide

AI Governance Control Plane catalogs prompt and model identities reported by your runtime or
evaluation code. It does not author prompt text, choose model settings, or
serve inference. This guide shows how a producer reports the exact evidence it
used so operators can trace it through the asset catalog and ontology.

## Before you start

Set the API base URL and an access token for your environment:

```bash
export AI_GOVERNANCE_API_URL=http://localhost:8000
export AI_GOVERNANCE_TOKEN=replace-with-a-bearer-token
```

The default Docker stack requires a Keycloak bearer token. For local
development-mode API deployments, use the configured development identity
instead. See [Configuration](../reference/CONFIGURATION.md) for authentication
and tenancy configuration.

Each observation needs:

- `source_system` — a stable producer name, such as `support-api` or
  `batch-evaluator`.
- `source_reference` — an optional immutable reference to the execution,
  evaluation run, or deployment evidence.
- A logical identity and version supplied by your runtime.

AI Governance Control Plane treats the same logical name/version with the same evidence as
idempotent. Different evidence under that identity returns `409 Conflict`; use
a new version rather than overwriting recorded history.

## Observe a prompt

If the producer can submit prompt content, send it directly. AI Governance Control Plane derives
and stores the SHA-256 content hash.

```bash
curl -X POST "$AI_GOVERNANCE_API_URL/api/v1/prompts/observations" \
  -H "Authorization: Bearer $AI_GOVERNANCE_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "support-assistant",
    "version": "v7",
    "source_system": "support-api",
    "source_reference": "evaluation-run-123",
    "template": "Answer using only the supplied context.\\nQuestion: {{question}}",
    "variables": ["question", "context"]
  }'
```

If prompt content must stay in the runtime, omit `template` and provide its
SHA-256 hash instead. Studio will display **Prompt content unavailable** while
still showing its provenance, hash, references, and lineage.

```json
{
  "name": "support-assistant",
  "version": "v7",
  "source_system": "support-api",
  "source_reference": "evaluation-run-123",
  "content_hash": "sha256:replace-with-the-runtime-hash",
  "variables": ["question", "context"]
}
```

## Observe a model runtime configuration

Report the provider-native model identity and the configuration observed at
execution time. The `parameters` object can include provider-specific fields;
AI Governance Control Plane records it without interpreting or changing it.

```bash
curl -X POST "$AI_GOVERNANCE_API_URL/api/v1/models/observations" \
  -H "Authorization: Bearer $AI_GOVERNANCE_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "provider": "OpenAI",
    "model_name": "gpt-5",
    "version": "2026-06",
    "source_system": "support-api",
    "source_reference": "evaluation-run-123",
    "context_window": 128000,
    "parameters": {
      "temperature": 0.2,
      "max_tokens": 800,
      "top_p": 1.0
    }
  }'
```

## Python example

Use the observed values from the same code path that invokes your model. Do
not reconstruct them later from defaults or environment variables.

```python
import hashlib
import os

import httpx

base_url = os.environ["AI_GOVERNANCE_API_URL"]
token = os.environ["AI_GOVERNANCE_TOKEN"]
template = "Answer using only the supplied context.\nQuestion: {{question}}"

prompt_payload = {
    "name": "support-assistant",
    "version": "v7",
    "source_system": "support-api",
    "source_reference": "evaluation-run-123",
    "content_hash": f"sha256:{hashlib.sha256(template.encode()).hexdigest()}",
    "variables": ["question", "context"],
}
model_payload = {
    "provider": "OpenAI",
    "model_name": "gpt-5",
    "version": "2026-06",
    "source_system": "support-api",
    "source_reference": "evaluation-run-123",
    "context_window": 128000,
    "parameters": {"temperature": 0.2, "max_tokens": 800},
}

headers = {"Authorization": f"Bearer {token}"}
with httpx.Client(base_url=base_url, headers=headers, timeout=10) as client:
    prompt = client.post("/api/v1/prompts/observations", json=prompt_payload)
    prompt.raise_for_status()
    model = client.post("/api/v1/models/observations", json=model_payload)
    model.raise_for_status()
```

## Node.js example

```ts
import { createHash } from "node:crypto";

const template = "Answer using only the supplied context.\nQuestion: {{question}}";
const contentHash = `sha256:${createHash("sha256").update(template).digest("hex")}`;

const response = await fetch(`${process.env.AI_GOVERNANCE_API_URL}/api/v1/prompts/observations`, {
  method: "POST",
  headers: {
    Authorization: `Bearer ${process.env.AI_GOVERNANCE_TOKEN}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    name: "support-assistant",
    version: "v7",
    source_system: "support-api",
    source_reference: "evaluation-run-123",
    content_hash: contentHash,
    variables: ["question", "context"],
  }),
});

if (!response.ok) throw new Error(await response.text());
```

## Verify the observation

Open **Assets → Prompt Catalog** or **Assets → Model Catalog** in Studio. The
new version shows an **Observed** provenance badge, its source metadata, and
an **Open ontology** action. The graph is populated by backend ontology
synchronization; the browser does not infer the lineage.

For full request/response contracts, see the [REST API reference](../reference/REST_API.md).
