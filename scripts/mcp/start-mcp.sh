#!/bin/sh
set -eu

provided_api_token="${KAVACH_API_TOKEN:-}"
if [ -f .env.local ]; then
  set -a
  . ./.env.local
  set +a
fi
if [ -n "$provided_api_token" ]; then
  export KAVACH_API_TOKEN="$provided_api_token"
fi

if [ -z "${KAVACH_API_TOKEN:-}" ] && [ -n "${KAVACH_MCP_CLIENT_SECRET:-}" ]; then
  if ! token="$(python3 -c 'import json, os, urllib.parse, urllib.request; url=os.environ["KAVACH_MCP_TOKEN_URL"]; body=urllib.parse.urlencode({"grant_type":"client_credentials", "client_id":os.environ["KAVACH_MCP_CLIENT_ID"], "client_secret":os.environ["KAVACH_MCP_CLIENT_SECRET"]}).encode(); response=urllib.request.urlopen(urllib.request.Request(url, data=body, headers={"Content-Type":"application/x-www-form-urlencoded"})); print(json.load(response)["access_token"])' 2>/dev/null)"; then
    echo "Unable to obtain a Keycloak token for ${KAVACH_MCP_CLIENT_ID:-kavach-mcp}. Verify the client exists in the kavach realm and that KAVACH_MCP_CLIENT_SECRET matches Keycloak." >&2
    exit 1
  fi
  [ -n "$token" ] || { echo "Keycloak returned an empty access_token." >&2; exit 1; }
  export KAVACH_API_TOKEN="$token"
fi

# mcpo 0.0.20 imports streamablehttp_client, which MCP 2.0 removed. Pin the
# compatible pair so the legacy MCP-to-OpenAPI proxy is reproducible.
exec uvx --from "mcpo==0.0.20" --with "mcp==1.29.0" mcpo \
  --host "${KAVACH_MCP_HOST:-127.0.0.1}" \
  --port "${KAVACH_MCP_PORT:-8001}" \
  -- \
  uv run python -c 'from kavach import create_mcp_server; create_mcp_server().run_stdio()'
