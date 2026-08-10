#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

COMPOSE=(
  docker compose
  --project-directory "$ROOT_DIR"
  -f "$ROOT_DIR/docker-compose.yml"
)

services=(
  ai-governance-platform
  ai-governance-studio
  ai-governance-replay-worker
  ai-governance-ontology-sync-worker
  ai-governance-mcp
  ai-governance-mcp-http
  neo4j
  ai-governance-neo4j-schema
  seaweedfs
)

usage() {
  cat <<'EOF'
Usage: ./servers.sh <command> [service ...]

Commands:
  up       Start Keycloak and the local AI Governance Control Plane stack (default).
  build    Build the Platform and Studio images.
  restart  Restart running Compose services. Pass service names to avoid the prompt.
  down     Stop the AI Governance Control Plane Compose stack and preserve local data.
  logs     Follow stack logs; pass service names to narrow the output.
  ps       Show Compose service status.
  config   Render and validate the Compose configuration.
EOF
}

contains() {
  local needle="$1"
  shift
  local item
  for item in "$@"; do
    [[ "$item" == "$needle" ]] && return 0
  done
  return 1
}

prepare_runtime() {
  chmod +x scripts/build/*.sh scripts/docker/*.sh scripts/keycloak/*.sh scripts/mcp/*.sh

  echo "Starting Keycloak..."
  ./scripts/keycloak/start-keycloak.sh

  echo "Discovering service-account identities..."
  ./scripts/keycloak/get-service-account-actorids.sh

  echo "Generating build metadata..."
  ./scripts/build/generate-build-metadata.sh
}

restart_services() {
  local running=()
  local selected=()
  local selection token index service
  while IFS= read -r service; do
    [[ -n "$service" ]] && running+=("$service")
  done < <("${COMPOSE[@]}" ps --services --status running)

  if (( ${#running[@]} == 0 )); then
    echo "No AI Governance Control Plane Compose services are currently running." >&2
    return 1
  fi

  if (( $# > 0 )); then
    for service in "$@"; do
      if ! contains "$service" "${running[@]}"; then
        echo "'$service' is not a running AI Governance Control Plane Compose service." >&2
        echo "Running services: ${running[*]}" >&2
        return 2
      fi
      if (( ${#selected[@]} == 0 )) || ! contains "$service" "${selected[@]}"; then
        selected+=("$service")
      fi
    done
  else
    if [[ ! -t 0 ]]; then
      echo "Specify one or more service names when restart is non-interactive." >&2
      return 2
    fi
    echo "Running AI Governance Control Plane services:"
    for index in "${!running[@]}"; do
      printf '  %2d) %s\n' "$((index + 1))" "${running[index]}"
    done
    echo "Enter numbers or service names separated by spaces or commas; use 'all' for every service."
    read -r -p "Restart: " selection
    selection="${selection//,/ }"
    for token in $selection; do
      if [[ "$token" == "all" ]]; then
        selected=("${running[@]}")
        break
      fi
      if [[ "$token" =~ ^[0-9]+$ ]]; then
        index=$((token - 1))
        if (( index < 0 || index >= ${#running[@]} )); then
          echo "'$token' is not a listed service number." >&2
          return 2
        fi
        service="${running[index]}"
      else
        service="$token"
        if ! contains "$service" "${running[@]}"; then
          echo "'$service' is not a running AI Governance Control Plane Compose service." >&2
          return 2
        fi
      fi
      if (( ${#selected[@]} == 0 )) || ! contains "$service" "${selected[@]}"; then
        selected+=("$service")
      fi
    done
  fi

  if (( ${#selected[@]} == 0 )); then
    echo "No services selected; nothing restarted."
    return 0
  fi

  echo "Restarting: ${selected[*]}"
  "${COMPOSE[@]}" restart "${selected[@]}"
  echo "Waiting for selected services to become ready…"
  "${COMPOSE[@]}" up --detach --wait --no-deps "${selected[@]}"
  echo "Restart complete: ${selected[*]}"
}

command="${1:-up}"
if (( $# > 0 )); then
  shift
fi

case "$command" in
  up)
    prepare_runtime
    echo "Validating Docker configuration..."
    "${COMPOSE[@]}" config --quiet
    "${COMPOSE[@]}" up --build --detach
    echo
    echo "AI Governance Control Plane OSS development stack is running."
    echo "Studio: http://localhost:3000"
    echo "API:    http://localhost:8000"
    ;;
  build)
    prepare_runtime
    "${COMPOSE[@]}" build ai-governance-platform ai-governance-studio
    ;;
  restart)
    restart_services "$@"
    ;;
  down)
    "${COMPOSE[@]}" down
    ;;
  logs)
    if (( $# > 0 )); then
      "${COMPOSE[@]}" logs --follow --tail=100 "$@"
    else
      "${COMPOSE[@]}" logs --follow --tail=100 "${services[@]}"
    fi
    ;;
  ps)
    "${COMPOSE[@]}" ps
    ;;
  config)
    "${COMPOSE[@]}" config
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "Unknown command: $command" >&2
    usage >&2
    exit 2
    ;;
esac
