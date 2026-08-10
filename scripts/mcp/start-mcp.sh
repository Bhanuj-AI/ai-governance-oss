#!/bin/sh
set -eu

provided_api_token="${AI_GOVERNANCE_API_TOKEN:-}"
if [ -f .env.local ]; then
  set -a
  . ./.env.local
  set +a
fi
if [ -n "$provided_api_token" ]; then
  export AI_GOVERNANCE_API_TOKEN="$provided_api_token"
fi

if [ -z "${AI_GOVERNANCE_API_TOKEN:-}" ] && [ -n "${AI_GOVERNANCE_MCP_CLIENT_SECRET:-}" ]; then
  if ! token="$(python3 -c 'import json, os, urllib.parse, urllib.request; url=os.environ["AI_GOVERNANCE_MCP_TOKEN_URL"]; body=urllib.parse.urlencode({"grant_type":"client_credentials", "client_id":os.environ["AI_GOVERNANCE_MCP_CLIENT_ID"], "client_secret":os.environ["AI_GOVERNANCE_MCP_CLIENT_SECRET"]}).encode(); response=urllib.request.urlopen(urllib.request.Request(url, data=body, headers={"Content-Type":"application/x-www-form-urlencoded"})); print(json.load(response)["access_token"])' 2>/dev/null)"; then
    echo "Unable to obtain a Keycloak token for ${AI_GOVERNANCE_MCP_CLIENT_ID:-ai-governance-mcp}. Verify the client exists in the ai-governance realm and that AI_GOVERNANCE_MCP_CLIENT_SECRET matches Keycloak." >&2
    exit 1
  fi
  [ -n "$token" ] || { echo "Keycloak returned an empty access_token." >&2; exit 1; }
  export AI_GOVERNANCE_API_TOKEN="$token"
fi

# mcpo 0.0.20 imports streamablehttp_client, which MCP 2.0 removed. Pin the
# compatible pair so the legacy MCP-to-OpenAPI proxy is reproducible.
exec uvx --from "mcpo==0.0.20" --with "mcp==1.29.0" mcpo \
  --host "${AI_GOVERNANCE_MCP_HOST:-127.0.0.1}" \
  --port "${AI_GOVERNANCE_MCP_PORT:-8001}" \
  -- \
  uv run python -c 'from ai_governance import create_mcp_server; create_mcp_server().run_stdio()'
