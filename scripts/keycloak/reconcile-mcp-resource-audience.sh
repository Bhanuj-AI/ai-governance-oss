#!/usr/bin/env bash

set -euo pipefail

# Realm import applies only to a newly created Keycloak volume. Reconcile the
# confidential MCP client at every local startup so service-account tokens are
# explicitly intended for the native MCP resource, without widening any other
# client or resource audience.

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
KEYCLOAK_ENV="$ROOT_DIR/keycloak-postgres/.env.keycloak"
REALM="ai-governance"
CLIENT_ID="${AI_GOVERNANCE_MCP_CLIENT_ID:-ai-governance-mcp}"
MCP_RESOURCE_AUDIENCE="${AI_GOVERNANCE_MCP_RESOURCE_AUDIENCE:-http://localhost:8002/mcp}"
MAPPER_NAME="mcp-resource-audience"

if [[ ! -f "$KEYCLOAK_ENV" ]]; then
  echo "Keycloak environment file was not found: $KEYCLOAK_ENV" >&2
  exit 1
fi

set -a
source "$KEYCLOAK_ENV"
set +a

KC_URL="${KEYCLOAK_URL:-http://keycloak.localhost:8080}"

admin_token() {
  curl --fail --silent --show-error \
    --request POST "$KC_URL/realms/master/protocol/openid-connect/token" \
    --header 'Content-Type: application/x-www-form-urlencoded' \
    --data-urlencode 'grant_type=password' \
    --data-urlencode 'client_id=admin-cli' \
    --data-urlencode "username=$KEYCLOAK_ADMIN_USERNAME" \
    --data-urlencode "password=$KEYCLOAK_ADMIN_PASSWORD" \
    | jq --exit-status --raw-output '.access_token'
}

TOKEN="$(admin_token)"
CLIENT_UUID="$(
  curl --fail --silent --show-error \
    "$KC_URL/admin/realms/$REALM/clients?clientId=$CLIENT_ID" \
    --header "Authorization: Bearer $TOKEN" \
    | jq --raw-output '.[0].id // empty'
)"

if [[ -z "$CLIENT_UUID" ]]; then
  echo "Keycloak client '$CLIENT_ID' was not found in realm '$REALM'." >&2
  exit 1
fi

MAPPER_PAYLOAD="$(
  jq --null-input \
    --arg name "$MAPPER_NAME" \
    --arg audience "$MCP_RESOURCE_AUDIENCE" \
    '{
      name: $name,
      protocol: "openid-connect",
      protocolMapper: "oidc-audience-mapper",
      consentRequired: false,
      config: {
        "included.custom.audience": $audience,
        "access.token.claim": "true",
        "id.token.claim": "false",
        "introspection.token.claim": "true"
      }
    }'
)"

MAPPER_ID="$(
  curl --fail --silent --show-error \
    "$KC_URL/admin/realms/$REALM/clients/$CLIENT_UUID/protocol-mappers/models" \
    --header "Authorization: Bearer $TOKEN" \
    | jq --raw-output --arg name "$MAPPER_NAME" '.[] | select(.name == $name) | .id' \
    | head -n 1
)"

if [[ -n "$MAPPER_ID" ]]; then
  # Keycloak requires an existing mapper's ID in a PUT representation. Keep
  # the mapper identity stable so existing realm volumes are reconciled rather
  # than receiving duplicate audience claims.
  MAPPER_UPDATE_PAYLOAD="$(
    printf '%s' "$MAPPER_PAYLOAD" | jq --arg id "$MAPPER_ID" '. + {id: $id}'
  )"
  curl --fail --silent --show-error \
    --request PUT "$KC_URL/admin/realms/$REALM/clients/$CLIENT_UUID/protocol-mappers/models/$MAPPER_ID" \
    --header "Authorization: Bearer $TOKEN" \
    --header 'Content-Type: application/json' \
    --data "$MAPPER_UPDATE_PAYLOAD" \
    >/dev/null
else
  curl --fail --silent --show-error \
    --request POST "$KC_URL/admin/realms/$REALM/clients/$CLIENT_UUID/protocol-mappers/models" \
    --header "Authorization: Bearer $TOKEN" \
    --header 'Content-Type: application/json' \
    --data "$MAPPER_PAYLOAD" \
    >/dev/null
fi

echo "[mcp-audience] Client '$CLIENT_ID' issues tokens for '$MCP_RESOURCE_AUDIENCE'."
