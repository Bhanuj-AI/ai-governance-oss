# Public API Reference Maintenance

The API reference is generated from the FastAPI OpenAPI document. It is not a
second schema or a set of hand-maintained endpoint pages.

## Visibility

Every core REST router is classified during application composition in
`src/ai_governance/api/app.py`. That classification is emitted on each operation
as `x-ai-governance-visibility`:

- `public` — safe for integration discovery and shown under **Public APIs**.
- `operator` — authenticated control-plane operations, shown under **Operator APIs**.
- `internal` — probes, local/demo helpers, diagnostics, and any other operation
  that must not be published.

Unclassified routes are treated as `internal` by the generator. This includes
plugin routes until the plugin explicitly adds the same OpenAPI extension; no
external documentation allow-list exists.

## Generate and preview

Regenerate the checked-in static contract after a compatible REST contract or
visibility change:

```bash
uv run python -m ai_governance.api.openapi generate
```

Verify that the checked-in document is current and valid:

```bash
uv run python -m ai_governance.api.openapi check
```

The generated contract is committed at
`generated/openapi/ai-governance-v1.json`. The public website consumes this
contract as a generated static asset; it does not maintain a second OpenAPI
definition. Sync the sibling website from a checkout containing this repository:

```bash
cd ../kavach-website
pnpm sync:api-contract -- ../ai-governance-oss/generated/openapi/ai-governance-v1.json
pnpm check:api-contract -- ../ai-governance-oss/generated/openapi/ai-governance-v1.json
```

Open `https://governance.bhanuj.ai/reference/api` (or the equivalent local
website route). The Scalar page is public and has production and local server
choices, native cURL, JavaScript/Fetch, Python/Requests, and other Scalar
request clients. Bearer tokens are held in memory for the page session only.

Production defaults to `https://governance.bhanuj.ai`; override it during a
release build with `AI_GOVERNANCE_PUBLIC_API_URL`. The local server defaults to
`http://localhost:8000` and can be overridden with
`AI_GOVERNANCE_LOCAL_API_URL`. The generator rejects Docker and non-TLS
production addresses.

## CI and versions

OSS CI formally validates the OpenAPI document, checks reference resolution,
checks deterministic regeneration, and rejects internal routes and unsafe
server addresses. Pull requests also publish a readable diff of the generated
public contract without blocking compatible changes. The website validates its
checked-in asset with `pnpm check:api-contract` before building the Scalar page.

The current reference is the canonical FastAPI `v1` contract; its path prefix
remains `/api/v1`. A future incompatible version must be introduced as a new
versioned route and generated reference, rather than silently changing this
document.
