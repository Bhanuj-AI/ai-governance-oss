# MCP Usage and MCPO

> Start with native MCP at `http://localhost:8002/mcp`. It is the recommended
> endpoint for MCP-aware clients and supports both the new stateless protocol
> and compatible older clients. Use `8001` only when an HTTP/OpenAPI-only tool
> needs MCPO.

## Start here

| Your goal | Use this |
| --- | --- |
| Connect an MCP-aware desktop app, agent, or gateway | Native MCP: `http://localhost:8002/mcp` |
| Test the new stateless protocol locally | The [authenticated smoke test](#testing-levels) below |
| Use a conventional HTTP/OpenAPI client | MCPO: `http://localhost:8001` |
| Integrate application code directly | The REST API |

For a local smoke test, start the stack, obtain a short-lived MCP token, and
run the documented curl request:

```bash
./servers.sh up
( unset VIRTUAL_ENV; uv run python scripts/mcp/fetch-access-token.py )
```

The token is copied to the macOS clipboard. The complete request, including
the modern MCP headers, appears in [Testing levels](#testing-levels).

## What changed in MCP `2026-07-28`

MCP used to begin with `initialize` and use a server-issued session ID. The
new protocol makes each HTTP request self-contained instead. In practice this
means the native endpoint can run behind ordinary load balancing without sticky
sessions or a shared MCP session store.

This does **not** change the governance product model. Jobs, replay
executions, decisions, evaluations, and audit records remain durable resources;
later calls use their explicit IDs. Both protocol eras use the same tool,
authorization, audit, and REST-control-plane path.

## How MCP fits the control plane

The Model Context Protocol (MCP) is a standard way for an AI client to
discover and call tools exposed by an application. An MCP server publishes
tool names, descriptions, and input schemas. The AI client sends a structured
tool request, and the server returns structured content or an error.

In AI Governance Control Plane, MCP is an adapter over the REST control plane. It does not contain a
second copy of policy, tenancy or governance logic:

```text
MCP-aware client ──────────────► Native MCP server (`8002`)
HTTP/OpenAPI-only client ──────► MCPO (`8001`) ─► MCP server
                                                     │
                                                     ▼
                           REST control plane: identity, permissions, audit, persistence
```

The MCP server maps each tool to the existing REST API. REST remains the
source of truth for identity, tenant scope, permissions, audit records, and
persistence.

Native Streamable HTTP is MCP, not a conventional REST endpoint; use an MCP
client library for discovery and tool calls. The supported MCP Python v2 client
automatically prefers `2026-07-28` and falls back to `initialize` for an older
server. In Keycloak mode supply the caller's bearer token to the MCP client. AI Governance Control Plane forwards that
same token to REST, so tenant membership and roles are evaluated for the user
rather than the MCPO service account.

```python
import httpx2
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

headers = {"Authorization": "Bearer <access-token>"}
async with httpx2.AsyncClient(headers=headers) as http:
    async with Client(
        streamable_http_client("http://localhost:8002/mcp", http_client=http)
    ) as client:
        tools = await client.list_tools()
```

### Protocol-era Compatibility

The native endpoint at `8002` supports the stateless `2026-07-28` revision and
legacy handshake clients through the same canonical tool registry. Port `8001`
is MCPO's compatibility/OpenAPI wrapper, not the native stateless endpoint.

For `2026-07-28`, the caller sends `MCP-Protocol-Version`, `Mcp-Method`, and
for tool calls `Mcp-Name`, on every request. The matching protocol version,
client information, and capabilities also appear in `params._meta`. Servers
reject mismatched routing headers and request bodies. No `initialize` request
or `Mcp-Session-Id` is sent on this path.

## Authentication, Tokens & Identity

### Brief

With `AI_GOVERNANCE_AUTH_MODE=keycloak`, a remote client needs an access token before
it can use the native MCP endpoint. It sends that token on every connection or
request as:

```http
Authorization: Bearer <access-token>
```

AI Governance Control Plane does **not** replace that token with a shared MCP service-account token.
It validates the incoming credential at `/mcp` and forwards the same credential
to the REST control plane. The token's `sub` claim is the runtime actor used
for authorization and audit attribution.

```text
Client obtains an access token from Keycloak
        │
        │ Authorization: Bearer <access-token>
        ▼
AI Governance Control Plane MCP HTTP service (/mcp)
        │ validates token and preserves it
        ▼
AI Governance Control Plane REST control plane
        │ derives actor from JWT sub
        ▼
Tenant membership, role, permission, and audit decisions
```

The `context.organization_id` and `context.project_id` in a tool call select
the requested tenant scope. They never establish identity or grant access. An
actor may use a scope only when the REST control plane confirms its membership
and permission for that scope.

### Client Token Flow

| Situation | Who obtains the token? | Appropriate Keycloak flow | Identity recorded by AI Governance Control Plane |
| --- | --- | --- | --- |
| Local developer smoke test | The test script | Client credentials for `ai-governance-mcp` | MCP service account |
| Human using an AI desktop/web client | The user signs in | Authorization Code with PKCE / the organization's normal OIDC login | The signed-in user |
| Automated backend, agent, or scheduled job | The workload | Client credentials for that workload's own confidential client | That workload's service account |

Do not put a confidential-client secret into a browser, desktop AI client, or
prompt. A user-facing client should receive an access token through its normal
login flow. A backend workload may hold its own secret in a secrets manager and
use it only to obtain short-lived tokens.

### 1. Local developer smoke test: `ai-governance-mcp` service account

For a local Keycloak smoke test, load `.env.local`, obtain a short-lived token
for the existing `ai-governance-mcp` confidential client, and use it for the native
MCP connection. This represents the MCP service account; production remote
clients should instead send the individual caller's access token.

```bash
uv run python scripts/mcp/fetch-access-token.py
```

On macOS, this helper obtains a short-lived token from the dedicated
`ai-governance-mcp` Keycloak client and copies it to the clipboard without
printing or saving the token. The local Keycloak configuration grants that
client the native MCP resource audience, `http://localhost:8002/mcp`.
Paste it into a client as `Bearer <token>`. Clear the clipboard when finished.

This is the right option when validating a local installation. It is not a
user-login implementation: every call made with this token is attributed to
the `ai-governance-mcp` service account. The service account must have an active
membership and an assigned role in the selected organization/project.

### 2. User-facing AI Client: Signed-in User's Token

For an AI desktop application, web application, or an agent acting on behalf
of a person, authenticate the person with the organization's Keycloak/OIDC
login flow. Give the resulting short-lived **access token** to the MCP client;
do not give it a client secret.

```python
# access_token is obtained by the application's existing OIDC login flow.
headers = {"Authorization": f"Bearer {access_token}"}

async with httpx2.AsyncClient(headers=headers) as http:
    async with Client(
        streamable_http_client("https://mcp.example.com/mcp", http_client=http)
    ) as client:
        result = await client.call_tool(
            "context.current",
            {
                "context": {
                    "organization_id": "org_acme",
                    "project_id": "project_risk",
                }
            },
        )
```

`Client` uses `server/discover` and selects the stateless `2026-07-28`
protocol when the server supports it. It falls back to the legacy
`initialize` handshake for an older endpoint, so callers should not issue the
handshake themselves.

AI Governance Control Plane records the user's Keycloak subject as the actor. If that user lacks a
membership, role, or permission, the tool returns an authorization error even
if the token itself is valid. The client should renew expired access tokens
through its OIDC library and reconnect/retry with the new token; never send a
refresh token to AI Governance Control Plane.

### 3. Automated Client: Dedicated Workload Identity

For a CI job, backend service, or unattended agent, create a dedicated
confidential Keycloak client for that workload. Store its client secret in the
workload's secret manager, exchange it for a short-lived token using client
credentials, and supply the token to the MCP client exactly as in the local
example. Provision that service-account subject into AI Governance Control Plane with only the
organization/project roles it needs.

Do not reuse the local `ai-governance-mcp` client for unrelated production workloads.
Dedicated client identities make audit records understandable and make it
possible to revoke one integration without affecting another.

### Common Authentication Results

| Result | Meaning | What to check |
| --- | --- | --- |
| HTTP `401` from `/mcp` | No valid bearer token reached the MCP boundary. | Token present, not expired, correct issuer/signature, and MCP process configured for Keycloak mode. |
| MCP tool error containing REST `401` | The MCP process did not forward a valid token to REST, or REST rejected it. | Restart `ai-governance-mcp` after loading `.env.local`; ensure the client supplies `Authorization`. |
| MCP tool error derived from REST `403` | The token is valid, but the actor cannot use the requested tenant or operation. | AI Governance Control Plane membership, project scope, role assignment, and required permission. |

Development mode (`AI_GOVERNANCE_AUTH_MODE=development`) is intentionally different:
it does not validate JWTs and resolves the local development actor through the
existing development identity mechanism. Use it only for isolated local work,
not for a shared or internet-accessible MCP endpoint.

## Browser UI: MCP Inspector (development only)

The native endpoint deliberately does not expose Swagger/OpenAPI because MCP
is not an OpenAPI service. Use the official MCP Inspector when a visual tool
browser is useful during development.

Start the AI Governance Control Plane local stack and native HTTP service in separate terminals:

```bash
./ai-governance-local.sh
```

```bash
uv run ai-governance-mcp --transport streamable-http --host 127.0.0.1 --port 8002
```

Then start the Inspector from the repository root:

```bash
./scripts/mcp/start-inspector.sh
```

The launcher starts the official Inspector with `npx`. Open the complete local
URL printed by the launcher, including its `MCP_PROXY_AUTH_TOKEN` query
parameter. Opening plain `http://localhost:6274` omits that Inspector-local
proxy credential and results in a connection error.

In its browser UI:

1. Select **Streamable HTTP** and **Direct** connection type.
2. Set the server URL to `http://127.0.0.1:8002/mcp`.
3. Run `uv run python scripts/mcp/fetch-access-token.py` in another terminal.
4. Under **Custom Headers**, enable the header toggle and enter:

```text
Authorization: Bearer <access-token>
```

5. Leave the Inspector's OAuth fields empty and click **Connect**.
6. After connecting, select `context.current` from **Tools** and enter this in
   its tool-arguments JSON editor:

```json
{
  "context": {
    "organization_id": "org_default",
    "project_id": "project_default"
  }
}
```

The local helper obtains the `ai-governance-mcp` service-account token and
copies it to the clipboard. Its audience is the native MCP resource
`http://localhost:8002/mcp`; do not paste `AI_GOVERNANCE_MCP_CLIENT_SECRET`
into a browser UI. The Inspector can then initialize the connection, browse the
tools, inspect schemas, and invoke the selected tool.

The local `.env.local` permits the Inspector browser origins on port `6274`.
Restart `ai-governance-mcp` after changing `AI_GOVERNANCE_MCP_HTTP_ALLOWED_ORIGINS`. For a
shared deployment, replace those local origins with the explicit origin of the
approved browser client; do not use a wildcard origin. Browser MCP clients
also send MCP-specific headers after initialization; AI Governance Control Plane explicitly permits
the required protocol, session, and event-ID headers in the local CORS policy.

### Reading the native MCP server log

| Log entry | Meaning |
| --- | --- |
| `OPTIONS /mcp ... 200` | The browser's CORS preflight was accepted. |
| `jwt_authenticated` and `POST /mcp ... 200` | The bearer token was accepted and an MCP request completed. |
| `Terminating session: None` | Expected in AI Governance Control Plane's stateless HTTP mode; the next request may use any replica. |
| `POST /mcp ... 401` | The request did not include a valid bearer token. |
| Tool result with REST-derived `403` | The token is valid, but the tenant membership, role, or permission is insufficient. |

## What MCPO is

MCPO is a transport adapter. It starts a normal stdio MCP server as a child
process and exposes that server through an HTTP service with generated
OpenAPI-compatible endpoints.

This distinction is important:

- **MCP server**: AI Governance Control Plane's tool implementation and JSON-RPC behavior.
- **stdio**: The process transport where JSON-RPC messages are exchanged over
  standard input/output. This is useful when an AI desktop client launches the
  server directly.
- **MCPO**: The optional HTTP wrapper around the stdio server. It listens on
  port `8001`, discovers the MCP tools, and makes them available to HTTP-based
  clients.

MCPO does not replace AI Governance Control Plane authentication or authorization. In Keycloak mode,
MCP must forward a valid bearer token to the REST API. It normally obtains a
client-credentials token from Keycloak; `AI_GOVERNANCE_API_TOKEN` is an explicit
override for testing. The token's `sub` remains the runtime actor, and tenant
authorization still requires an active AI Governance Control Plane membership and role.

The local realm defines a separate confidential client named `ai-governance-mcp`. It
uses the client-credentials grant and is independent from the public
`ai-governance-studio` browser client and the general `ai-governance-service` client. Its
secret belongs only to the MCPO process. The MCP service account must also have
an active AI Governance Control Plane membership and the required role assignment for the target
organization/project; a Keycloak client role alone is not sufficient.

## Recommended local developer flow

Use the one-command local launcher:

```bash
./ai-governance-local.sh
```

It starts Keycloak, discovers the MCP and walkthrough service-account subjects,
writes `.env.service-accounts.generated` and `.env.oauth.generated`,
starts MCPO, and starts the REST API. Start
Studio separately with `cd console && pnpm dev`.

For a two-terminal flow, run `./scripts/keycloak/start-keycloak.sh`, then
`./scripts/keycloak/get-service-account-actorids.sh`, load `.env.local`,
`.env.service-accounts.generated`, and `.env.oauth.generated`, and start
Uvicorn. Run `./scripts/mcp/start-mcp.sh` in the second
terminal.

The generated actor ID is the Keycloak service-account user's stable `sub`,
not an access token. Backend startup uses it to provision AI Governance Control Plane membership
and roles. Access tokens are short-lived and refreshed automatically by the
MCP REST client.

## Start MCPO locally

Start Keycloak and the REST API first:

```bash
./scripts/keycloak/start-keycloak.sh
cd ..
uvicorn ai_governance.api.app:app --reload --env-file .env.local
```

In a second terminal, start the HTTP adapter. When the MCP client secret is
configured, the launcher obtains a short-lived service-account token
automatically:

```bash
export AI_GOVERNANCE_MCP_CLIENT_ID=ai-governance-mcp
export AI_GOVERNANCE_MCP_CLIENT_SECRET=mcp-secret
./scripts/mcp/start-mcp.sh
```

When run from the repository root, `scripts/mcp/start-mcp.sh` automatically loads the
ignored `.env.local` file. Docker does not need that file because Compose
injects the MCP settings into the container.

You can alternatively provide `AI_GOVERNANCE_API_TOKEN` directly for a user token; it
takes precedence over client-credentials token generation.

MCPO listens on:

```text
http://127.0.0.1:8001
```

The launcher uses `uvx` to obtain MCPO and runs:

```text
uv run python -c \
  'from ai_governance import create_mcp_server; create_mcp_server().run_stdio()'
```

The child command must use the public `create_mcp_server` export. Importing the
internal `create_server` symbol from `ai-governance` will fail.

## Start MCPO with Docker

The root Compose file starts `ai-governance-mcp` alongside `ai-governance-platform` and
Studio:

```bash
export AI_GOVERNANCE_API_TOKEN="<keycloak-access-token>"
docker compose up --build -d
```

Inside Docker, MCPO calls the REST API at
`http://ai-governance-platform:8000` and is exposed to the host at port `8001`.
Verify the generated API is available:

```bash
curl http://localhost:8001/openapi.json
```

The Docker service shares the platform SQLite volume for MCP audit persistence
and waits for the REST API healthcheck before starting. The Keycloak realm and
platform still need to be started according to the local setup documentation.

## Keycloak and token handling

The browser Studio token is not automatically available to an independently
started MCPO process. For user-based testing, pass a current access token
through `AI_GOVERNANCE_API_TOKEN` before launching MCPO. Do not commit tokens or
client secrets.

Client-credentials tokens are short-lived and are refreshed automatically by
the MCP REST client. A missing, expired, or unauthorized token produces REST
`401`/`403` responses even though the MCPO HTTP process itself may be healthy.

The realm JSON is imported only when the Keycloak PostgreSQL volume is new. If
the realm already exists, create the `ai-governance-mcp` client and its secret through
the Keycloak Admin Console, or recreate the disposable local realm with:

```bash
cd keycloak-postgres
docker compose down -v
cd ..
./scripts/keycloak/start-keycloak.sh
```

## Troubleshooting

### Nested `401` from MCPO

Check that the API issuer and token endpoint use the same hostname:

```env
AI_GOVERNANCE_OIDC_ISSUER=http://keycloak.localhost:8080/realms/ai-governance
AI_GOVERNANCE_MCP_TOKEN_URL=http://keycloak.localhost:8080/realms/ai-governance/protocol/openid-connect/token
```

Rebuild after configuration changes:

```bash
docker compose up --build -d ai-governance-platform ai-governance-mcp
```

### `ACTOR_NOT_MEMBER` or `TENANT_SCOPE_MISMATCH`

The token is valid, but its `sub` is not provisioned for the selected tenant.
Run the actor discovery flow before starting the API and confirm that the
subject in `.env.service-accounts.generated` matches the Keycloak service-account user.

### `PERMISSION_NOT_GRANTED`

Each tool maps to a REST permission. `platform_operator` covers operational
permissions such as `mcp_audit.read` and `job.read`. Membership and role
administration require their specific permissions; use `organization_admin`
only when that elevated access is intentional.

### `TenantScopeMismatch: string`

MCPO's generated examples contain placeholders. Replace them with real values:

```json
{"organization_id":"org_default","project_id":"project_default"}
```

### Platform unhealthy or port conflicts

Inspect the application logs:

```bash
docker logs ai-governance-platform --tail=200
lsof -nP -iTCP:3000 -sTCP:LISTEN
lsof -nP -iTCP:8001 -sTCP:LISTEN
```

For a disposable local reset:

```bash
docker compose down -v
./servers.sh
```

MCPO may wrap REST `401`/`403` responses as HTTP `500`; inspect the nested
`status_code`, `permission`, and `reason_code` fields.

## Testing levels

You can test MCP at 5 levels.

**1. Automated tests**

```bash
uv run pytest tests/mcp
```

**2. Native `2026-07-28` authenticated smoke test**

Start the full local stack and wait for the native endpoint:

```bash
./servers.sh up
until curl -fsS http://127.0.0.1:8002/health; do sleep 2; done
```

Fetch a short-lived local MCP service-account token. The helper copies it to
the macOS clipboard without printing it:

```bash
( unset VIRTUAL_ENV; uv run python scripts/mcp/fetch-access-token.py )
TOKEN="$(pbpaste)"
```

Then make a self-contained tool call. This test exercises Keycloak audience
validation, the stateless protocol envelope and headers, the canonical tool
registry, and the downstream REST control plane:

```bash
curl -sS http://127.0.0.1:8002/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  -H 'MCP-Protocol-Version: 2026-07-28' \
  -H 'Mcp-Method: tools/call' \
  -H 'Mcp-Name: provider_list' \
  --data '{
    "jsonrpc":"2.0",
    "id":1,
    "method":"tools/call",
    "params":{
      "name":"provider_list",
      "arguments":{},
      "_meta":{
        "io.modelcontextprotocol/protocolVersion":"2026-07-28",
        "io.modelcontextprotocol/clientInfo":{"name":"manual-curl-test","version":"1.0"},
        "io.modelcontextprotocol/clientCapabilities":{}
      }
    }
  }' | jq '{isError: .result.isError, status: .result.structuredContent.status}'
```

Expected output:

```json
{"isError": false, "status": "ok"}
```

**3. In Python, without running REST separately**

This uses the MCP server object directly with its configured REST client.

```python
from ai_governance import create_mcp_server

server = create_mcp_server()

print([tool.name for tool in server.list_tools()])

result = server.call_tool("provider.list")
print(result.model_dump())
```

This expects `AI_GOVERNANCE_API_URL` to point to a running AI Governance Control Plane REST API. Default:

```text
http://127.0.0.1:8000
```

**4. With the REST API running**

Start REST:

```bash
uvicorn ai_governance.api.app:app --reload
```

Then in another shell:

```bash
python - <<'PY'
from ai_governance import create_mcp_server

server = create_mcp_server()

print(server.call_tool("provider.list").model_dump())
print(server.call_tool("job.list", {"limit": 10}).model_dump())
PY
```

Example tool calls:

```python
server.call_tool("provider.list")
server.call_tool("registry.list_models")
server.call_tool("evaluation.history", {"execution_id": "exec-1"})
server.call_tool("experiment.candidates", {"experiment_id": "experiment-1"})
server.call_tool("experiment.runs", {"experiment_id": "experiment-1"})
server.call_tool(
    "experiment.compare_candidates",
    {
        "experiment_id": "experiment-1",
        "baseline_candidate_id": "candidate-a",
        "comparison_candidate_id": "candidate-b",
    },
)
server.call_tool("job.status", {"job_id": "job-1"})
```

For JSON-RPC style testing:

```python
server.handle_json_rpc({
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/list",
})
```

And:

```python
server.handle_json_rpc({
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
        "name": "provider.list",
        "arguments": {}
    }
})
```

**5. Legacy stdio compatibility**

You can test `run_stdio()` by piping line-delimited JSON-RPC messages into a tiny Python runner.

**List tools, no REST required:**

```bash
printf '%s\n' \
'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
'{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
| uv run python -c 'from ai_governance import create_mcp_server; create_mcp_server().run_stdio()'
```

**Call a tool through stdio:**

First start REST:

```bash
uvicorn ai_governance.api.app:app --reload
```

Then in another terminal:

```bash
printf '%s\n' \
'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"provider.list","arguments":{}}}' \
| AI_GOVERNANCE_API_URL=http://127.0.0.1:8000 uv run python -c 'from ai_governance import create_mcp_server; create_mcp_server().run_stdio()'
```

Example with arguments:

```bash
printf '%s\n' \
'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"job.list","arguments":{"limit":10}}}' \
| AI_GOVERNANCE_API_URL=http://127.0.0.1:8000 uv run python -c 'from ai_governance import create_mcp_server; create_mcp_server().run_stdio()'
```

It expects one JSON-RPC message per line and writes one JSON-RPC response per line. `notifications/initialized` intentionally returns no output.
