#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$ROOT_DIR"

if [ -f .env.local ]; then
  set -a
  . ./.env.local
  set +a
fi

MCP_URL="${KAVACH_MCP_INSPECTOR_URL:-http://127.0.0.1:8002/mcp}"

cat <<EOF
Starting the official MCP Inspector UI.

When the Inspector opens:
  1. Select the Streamable HTTP transport.
  2. Set the server URL to: ${MCP_URL}
  3. In Request Headers, add: Authorization: Bearer <access-token>
  4. Connect, initialize, list tools, and call a tool.

For local Keycloak testing, obtain a short-lived access token for the
kavach-mcp client using the documented MCP_USAGE.md example. Do not enter a
client secret into the Inspector.
EOF

exec npx --yes @modelcontextprotocol/inspector
