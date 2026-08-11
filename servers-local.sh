#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"
# A shell activated for another checkout must not influence this project's
# dependency resolution or emit an irrelevant virtual-environment warning.
unset VIRTUAL_ENV

echo "[local] Starting Keycloak..."
./scripts/keycloak/start-keycloak.sh

echo "[local] Discovering service-account identities..."
./scripts/keycloak/get-service-account-actorids.sh

set -a
. "$ROOT_DIR/.env.local"
. "$ROOT_DIR/.env.service-accounts.generated"
. "$ROOT_DIR/.env.oauth.generated"
set +a

echo "[local] Starting Neo4j..."
docker compose up -d neo4j

echo "[local] Initializing Neo4j ontology schema..."
for attempt in {1..20}; do
  if uv run python -m ai_governance.ontology.cli initialize-schema; then
    break
  fi
  if [ "$attempt" -eq 20 ]; then
    echo "[local] Neo4j schema initialization failed." >&2
    exit 1
  fi
  sleep 1
done

cleanup() {
  if [ -n "${MCP_PID:-}" ]; then
    echo "[local] Stopping MCPO..."
    kill "$MCP_PID" 2>/dev/null || true
    wait "$MCP_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

MCP_HOST="${AI_GOVERNANCE_MCP_HOST:-127.0.0.1}"
MCP_PORT="${AI_GOVERNANCE_MCP_PORT:-8001}"
if lsof -nP -iTCP:"$MCP_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "[local] Reusing existing MCP listener on ${MCP_HOST}:${MCP_PORT}."
else
  echo "[local] Starting MCPO on ${MCP_HOST}:${MCP_PORT}..."
  ./scripts/mcp/start-mcp.sh &
  MCP_PID=$!
fi

echo "[local] Starting AI Governance Control Plane API on ${AI_GOVERNANCE_API_HOST:-127.0.0.1}:${AI_GOVERNANCE_API_PORT:-8000}..."
exec uv run python -m uvicorn ai_governance.api.app:app --reload
