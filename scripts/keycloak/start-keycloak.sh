#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
KEYCLOAK_URL="${KEYCLOAK_URL:-http://keycloak.localhost:18080}"
cd "$ROOT_DIR/keycloak-postgres"

echo "[keycloak] Starting Keycloak and PostgreSQL..."

docker compose \
  --env-file .env.keycloak \
  up --build -d

echo "[keycloak] Waiting for the ai-governance realm endpoint..."
for attempt in $(seq 1 60); do
  if curl --silent --fail \
    "$KEYCLOAK_URL/realms/ai-governance/.well-known/openid-configuration" \
    >/dev/null; then
    echo "[keycloak] Ready after ${attempt} attempt(s)."
    break
  fi
  if [ "$attempt" -eq 60 ]; then
    echo "[keycloak] Timed out waiting for Keycloak readiness." >&2
    docker compose --env-file .env.keycloak logs --tail=80 keycloak >&2 || true
    exit 1
  fi
  sleep 2
done

"$ROOT_DIR/scripts/keycloak/provision-mcp-vscode-client-scopes.sh"
"$ROOT_DIR/scripts/keycloak/reconcile-mcp-resource-audience.sh"
"$ROOT_DIR/scripts/keycloak/reconcile-synthetic-agent-runtime-client.sh"

docker compose --env-file .env.keycloak ps
