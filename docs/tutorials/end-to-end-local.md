# End-to-End Local Tutorial

This tutorial follows one governed asset through the local AI Governance Control Plane stack:

1. start the complete local environment;
2. sign in to AI Governance Control Plane Studio;
3. inspect versioned prompt, model, dataset, and evaluation-provider records;
4. inspect the dataset bytes in local S3-compatible storage;
5. follow the exact asset version into ontology lineage; and
6. inspect the associated experiment, evaluation, and governance context.

It uses the deterministic demo data created by the local seed. It does not
deploy a model, label data, or create usage/cost analytics—those are outside
the OSS registry scope.

## What you need

- Docker Desktop with Docker Compose available.
- `uv` and Python 3.12+ if you intend to run tests or the API outside Docker.
- The repository cloned locally.

The local stack uses development-only credentials and volumes. Do not reuse
them in a shared or production environment.

## 1. Start the local stack

From the repository root, provision Keycloak and start AI Governance Control Plane:

```bash
./servers.sh
```

`./servers.sh` validates the Compose configuration and starts the Keycloak, platform,
Studio, Neo4j, SeaweedFS, workers and MCP services. The first build can take
a few minutes.

Confirm the containers are running:

```bash
docker compose ps
```

The important endpoints are:

| Service | URL | Purpose |
| --- | --- | --- |
| AI Governance Control Plane Studio | http://localhost:3000 | Operator UI |
| REST API | http://localhost:8000/docs | OpenAPI and API inspection |
| SeaweedFS Filer | http://localhost:8888 | Browse local dataset objects |
| SeaweedFS Master | http://localhost:9333 | Local storage topology |
| Neo4j Browser | http://localhost:7474 | Low-level graph administration |

If a local container has stale state and you want a fresh demo, remove the
volumes and start again:

```bash
docker compose down -v
./servers.sh
```

This also removes the local SQLite, Neo4j, and SeaweedFS data.

## 2. Sign in to Studio

Open http://localhost:3000. Sign in as `studio` with the password
configured as `AI_GOVERNANCE_STUDIO_PASSWORD` for the local Keycloak environment.

The local realm assigns this user to the default organization and project.
Studio then reads the same tenant-scoped REST APIs that an external client
would use.

## 3. Explore the asset registries

In the left navigation, choose **Assets**. The landing page groups assets into
four registries:

- **Prompts** — immutable prompt configurations and variables.
- **Models** — provider/model definitions and runtime configuration.
- **Datasets** — immutable dataset metadata and references to dataset content.
- **Evaluation Providers** — provider capability and configuration records.

Open the visible name in any registry table or tile. Names are links because
the detail page is version-specific; the surrounding row provides status and
summary context.

Every asset detail view has the same operator workflow:

| Tab | What it answers |
| --- | --- |
| Overview | What exact version is this and who registered it? |
| Versions | Which immutable versions belong to this logical asset? |
| References | Which governed records directly reference this version? |
| Lineage | What bounded ontology neighbourhood connects to this version? |
| Audit History | Which registry lifecycle projection events exist for it? |

For a prompt, open **Overview** to inspect the protected template for the
selected version. Prompt contents are deliberately omitted from prompt list
responses and are fetched only after the operator opens a specific version.

## 4. Inspect the seeded evaluation dataset

Open **Assets → Datasets → Demo Evaluation Set**.

The overview shows two intentionally separate concerns:

- Registry metadata: version, status, owner, schema version, record count, and
  checksum live in the AI Governance Control Plane registry database.
- Dataset content: the seeded JSONL object lives in SeaweedFS and the registry
  stores its `s3://` URI.

Open http://localhost:8888 and browse to:

```text
/buckets/ai-governance-datasets/demo/evaluation/v1.0/dataset.jsonl
```

SeaweedFS is only the local development implementation. AI Governance Control Plane talks to it
through the standard S3 API, so production can use AWS S3 by leaving
`AI_GOVERNANCE_DATASET_S3_ENDPOINT_URL` unset and configuring the normal S3 bucket,
region, and credentials. See [Configuration](../reference/CONFIGURATION.md#repository-backends).

## 5. Register your own dataset

From **Assets → Datasets**, select **Register Dataset**. Provide a logical
name, immutable version, description, schema version, and one UTF-8 CSV or
JSONL/NDJSON file.

AI Governance Control Plane validates the file, counts records, computes a SHA-256 checksum, writes
the bytes to the configured object store, and creates a **DRAFT** dataset
version. The registry stores the resulting `s3://` URI, checksum, record count,
and owner; it does not store the file body in SQLite.

The local default upload limit is 10 MiB. Parsing is streamed from the spooled
upload file and also enforces record-size and field-count limits. Adjust
`AI_GOVERNANCE_DATASET_MAX_UPLOAD_BYTES`, `AI_GOVERNANCE_DATASET_MAX_RECORD_BYTES`, and
`AI_GOVERNANCE_DATASET_MAX_FIELDS` when needed. A repeated checksum for the same
logical dataset is rejected even under a new version; use a new version only
when the content changes.

## 6. Submit observed runtime evidence (optional)

AI Governance Control Plane is not a prompt-authoring or model-serving tool. A producer can instead
report exactly what it used and let AI Governance Control Plane catalog the immutable identity. This
example deliberately withholds prompt content while retaining a hash:

```bash
curl -X POST http://localhost:8000/api/v1/prompts/observations \
  -H 'Content-Type: application/json' \
  -d '{
    "name":"support-assistant",
    "version":"v7",
    "source_system":"local-evaluation",
    "source_reference":"run-123",
    "content_hash":"sha256:replace-with-the-producer-hash",
    "variables":["question","context"]
  }'
```

The record appears in **Assets → Prompt Catalog** as **Observed**. Its detail
page displays source metadata and says that content is unavailable, while its
ontology node still retains the hash and lineage. Submitting the exact same
payload is idempotent; a different payload for the same prompt name/version is
rejected to protect historical evidence.

## 7. Follow an asset into ontology lineage

Return to an asset detail page and select **Lineage**. This is not an
analytics view: it is a bounded neighbourhood of governed records around the
selected *version*.

For the seeded prompt, the sequence commonly includes:

```text
Prompt version → Experiment candidate → Evaluation run → Governance decision
```

Select **Open ontology**. Studio opens Graph Explorer with the entity type,
entity ID, and depth prefilled from the selected asset version. Press **Load**
only if you change the query; the initial graph is already requested from the
URL parameters.

The graph is sourced by the backend ontology query API and, in the Docker
stack, by Neo4j. The browser renders nodes and edges but does not invent
relationships or calculate lineage itself. Use **Reset layout** after manually
moving nodes to return to the generated directional layout.

## 8. Inspect the governed outcome

Use the left navigation to open **Experiments** or **Governance Decisions**.
The demo seed contains experiments, candidates, evaluation runs, policy
outcomes, jobs, replay records, and governance decisions that share stable
references with the registry assets.

This is the operational loop to verify:

```text
Versioned asset
  → experiment candidate
  → evaluation evidence
  → policy/governance decision
  → ontology lineage and audit history
```

The registry preserves the versioned inputs; experiments and evaluations
produce evidence; governance decisions explain the outcome; and the ontology
connects them for inspection.

## 8. Verify the REST contracts (optional)

Open http://localhost:8000/docs and inspect the registry endpoints. The key
read APIs are:

```text
GET /api/v1/prompts
GET /api/v1/prompts/{name}
GET /api/v1/prompts/versions/{prompt_id}
GET /api/v1/models
GET /api/v1/datasets
POST /api/v1/datasets/upload
GET /api/v1/providers
```

`GET /api/v1/prompts` returns prompt metadata without the template.
`GET /api/v1/prompts/versions/{prompt_id}` returns one explicit version,
including its template. Requests to the default local stack require the
Keycloak bearer token established by Studio; use the OpenAPI authorization
flow or a development-mode API when exercising them manually.

## Where to go next

- [AI Governance Control Plane Studio and Graph Explorer](../ontology/governance-graph-console.md)
- [REST API reference](../reference/REST_API.md)
- [Producer integration guide](producer-integration.md)
- [Configuration reference](../reference/CONFIGURATION.md)
- [Governance ontology](../architecture/GOVERNANCE_ONTOLOGY.md)
