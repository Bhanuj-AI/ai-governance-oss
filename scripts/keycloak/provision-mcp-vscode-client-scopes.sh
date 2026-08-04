#!/usr/bin/env bash

set -euo pipefail

# Keycloak imports a realm only once. Reconcile the public PKCE client on every
# local startup so existing realm volumes receive standard OIDC scopes added by
# newer realm definitions without deleting identities or other realm state.

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
KEYCLOAK_ENV="$ROOT_DIR/keycloak-postgres/.env.keycloak"
REALM="kavach"
CLIENT_ID="${KAVACH_MCP_VSCODE_CLIENT_ID:-kavach-mcp-vscode}"

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

ensure_default_scope() {
  local scope_name="$1"
  local scope_uuid

  scope_uuid="$(
    curl --fail --silent --show-error \
      "$KC_URL/admin/realms/$REALM/client-scopes?search=$scope_name" \
      --header "Authorization: Bearer $TOKEN" \
      | jq --raw-output --arg name "$scope_name" '.[] | select(.name == $name) | .id' \
      | head -n 1
  )"

  if [[ -z "$scope_uuid" ]]; then
    echo "[mcp-vscode] Creating missing OIDC scope '$scope_name'..."
    curl --fail --silent --show-error \
      --request POST "$KC_URL/admin/realms/$REALM/client-scopes" \
      --header "Authorization: Bearer $TOKEN" \
      --header 'Content-Type: application/json' \
      --data "$(jq --null-input --arg name "$scope_name" '{name: $name, protocol: "openid-connect", attributes: {"display.on.consent.screen": "false", "include.in.token.scope": "true"}}')" \
      >/dev/null
    scope_uuid="$(
      curl --fail --silent --show-error \
        "$KC_URL/admin/realms/$REALM/client-scopes?search=$scope_name" \
        --header "Authorization: Bearer $TOKEN" \
        | jq --exit-status --raw-output --arg name "$scope_name" '.[] | select(.name == $name) | .id' \
        | head -n 1
    )"
  fi

  curl --fail --silent --show-error \
    --request PUT "$KC_URL/admin/realms/$REALM/clients/$CLIENT_UUID/default-client-scopes/$scope_uuid" \
    --header "Authorization: Bearer $TOKEN" \
    >/dev/null
}

echo "[mcp-vscode] Reconciling standard OIDC scopes for '$CLIENT_ID'..."
for scope in profile email roles; do
  ensure_default_scope "$scope"
done
echo "[mcp-vscode] Keycloak client '$CLIENT_ID' is ready."
