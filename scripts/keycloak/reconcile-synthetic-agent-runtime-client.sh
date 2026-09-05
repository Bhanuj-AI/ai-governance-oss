#!/usr/bin/env bash

set -euo pipefail

# Keycloak imports a realm only when its data volume is new. Keep the local
# simulator identity available on existing developer volumes without resetting
# users, sessions, or unrelated clients.

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
KEYCLOAK_ENV="$ROOT_DIR/keycloak-postgres/.env.keycloak"
REALM="ai-governance"
CLIENT_ID="synthetic-agent-runtime"
CLIENT_SECRET="${SYNTHETIC_RUNTIME_CLIENT_SECRET:-local-synthetic-runtime-client-secret}"

if [[ ! -f "$KEYCLOAK_ENV" ]]; then
  echo "Keycloak environment file was not found: $KEYCLOAK_ENV" >&2
  exit 1
fi

set -a
source "$KEYCLOAK_ENV"
set +a

KC_URL="${KEYCLOAK_URL:-http://keycloak.localhost:8080}"
CLIENT_SECRET="${SYNTHETIC_RUNTIME_CLIENT_SECRET:-$CLIENT_SECRET}"

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
  CLIENT_PAYLOAD="$(
    jq --null-input \
      --arg client_id "$CLIENT_ID" \
      --arg client_secret "$CLIENT_SECRET" \
      '{
        clientId: $client_id,
        name: "Synthetic Agent Runtime",
        enabled: true,
        publicClient: false,
        clientAuthenticatorType: "client-secret",
        secret: $client_secret,
        serviceAccountsEnabled: true,
        standardFlowEnabled: false,
        directAccessGrantsEnabled: false,
        protocol: "openid-connect"
      }'
  )"
  curl --fail --silent --show-error \
    --request POST "$KC_URL/admin/realms/$REALM/clients" \
    --header "Authorization: Bearer $TOKEN" \
    --header 'Content-Type: application/json' \
    --data "$CLIENT_PAYLOAD" \
    >/dev/null
  CLIENT_UUID="$(
    curl --fail --silent --show-error \
      "$KC_URL/admin/realms/$REALM/clients?clientId=$CLIENT_ID" \
      --header "Authorization: Bearer $TOKEN" \
      | jq --exit-status --raw-output '.[0].id'
  )"
fi

reconcile_hardcoded_claim() {
  local mapper_name="$1"
  local claim_name="$2"
  local claim_value="$3"
  local mapper_payload mapper_id mapper_update_payload

  mapper_payload="$(
    jq --null-input \
      --arg name "$mapper_name" \
      --arg claim_name "$claim_name" \
      --arg claim_value "$claim_value" \
      '{
        name: $name,
        protocol: "openid-connect",
        protocolMapper: "oidc-hardcoded-claim-mapper",
        consentRequired: false,
        config: {
          "claim.name": $claim_name,
          "claim.value": $claim_value,
          "jsonType.label": "String",
          "access.token.claim": "true",
          "id.token.claim": "false",
          "userinfo.token.claim": "false"
        }
      }'
  )"
  mapper_id="$(
    curl --fail --silent --show-error \
      "$KC_URL/admin/realms/$REALM/clients/$CLIENT_UUID/protocol-mappers/models" \
      --header "Authorization: Bearer $TOKEN" \
      | jq --raw-output --arg name "$mapper_name" '.[] | select(.name == $name) | .id' \
      | head -n 1
  )"

  if [[ -n "$mapper_id" ]]; then
    mapper_update_payload="$(printf '%s' "$mapper_payload" | jq --arg id "$mapper_id" '. + {id: $id}')"
    curl --fail --silent --show-error \
      --request PUT "$KC_URL/admin/realms/$REALM/clients/$CLIENT_UUID/protocol-mappers/models/$mapper_id" \
      --header "Authorization: Bearer $TOKEN" \
      --header 'Content-Type: application/json' \
      --data "$mapper_update_payload" \
      >/dev/null
  else
    curl --fail --silent --show-error \
      --request POST "$KC_URL/admin/realms/$REALM/clients/$CLIENT_UUID/protocol-mappers/models" \
      --header "Authorization: Bearer $TOKEN" \
      --header 'Content-Type: application/json' \
      --data "$mapper_payload" \
      >/dev/null
  fi
}

reconcile_hardcoded_claim "organization-id" "organization_id" "org_default"
reconcile_hardcoded_claim "project-ids" "project_ids" "project_default"
reconcile_hardcoded_claim "principal-type" "principal_type" "service"

echo "[synthetic-runtime] Keycloak client '$CLIENT_ID' is ready."
