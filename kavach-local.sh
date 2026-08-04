#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

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
  if uv run python -m kavach.ontology.cli initialize-schema; then
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

echo "[local] Starting MCPO on ${KAVACH_MCP_HOST:-127.0.0.1}:${KAVACH_MCP_PORT:-8001}..."
./scripts/mcp/start-mcp.sh &
MCP_PID=$!

echo "[local] Starting Kavach API on ${KAVACH_API_HOST:-127.0.0.1}:${KAVACH_API_PORT:-8000}..."
exec uvicorn kavach.api.app:app --reload
