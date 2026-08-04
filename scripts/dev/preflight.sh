#!/usr/bin/env bash
# Local change verification. It validates the intended commit metadata and
# executes checks, but deliberately never creates a commit or changes branches.

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(git -C "$script_dir/../.." rev-parse --show-toplevel)"
cd "$repo_root"

usage() {
  cat <<'EOF'
Usage: ./scripts/dev/preflight.sh [--message "type(scope): summary"] [--summary "bullet"]

Collect a Conventional Commit message and one or more release-note bullets,
then run the local quality gate. This command does not commit, push, or start
Docker services.
EOF
}

commit_message=""
summary_bullets=()
while (($#)); do
  case "$1" in
    --message)
      commit_message="${2:-}"
      shift 2
      ;;
    --summary)
      summary_bullets+=("${2:-}")
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$commit_message" ]]; then
  read -r -p "Commit message (for example, feat(mcp): add invocation audit): " commit_message
fi

conventional_commit_pattern='^(build|chore|ci|docs|feat|fix|perf|refactor|revert|style|test)(\([a-z0-9][a-z0-9._/-]*\))?(!)?: .+$'
if ! [[ "$commit_message" =~ $conventional_commit_pattern ]]; then
  cat >&2 <<'EOF'
Commit message must follow Conventional Commits:
  type(scope): short imperative summary

Examples:
  feat(mcp): add invocation audit
  fix(jobs): retain local demo records
  chore!: remove deprecated API
EOF
  exit 2
fi

if ((${#summary_bullets[@]} == 0)); then
  printf 'Release-note bullet(s); submit an empty line when finished.\n'
  while IFS= read -r -p '- ' bullet && [[ -n "$bullet" ]]; do
    summary_bullets+=("$bullet")
  done
fi

if ((${#summary_bullets[@]} == 0)); then
  printf 'At least one release-note bullet is required.\n' >&2
  exit 2
fi

printf '\nProposed commit\n  %s\n\nRelease notes\n' "$commit_message"
for bullet in "${summary_bullets[@]}"; do
  printf -- '- %s\n' "$bullet"
done

failed_checks=0

run_check() {
  local label="$1"
  shift
  printf '%s\n' "$label"
  if ! "$@"; then
    failed_checks=$((failed_checks + 1))
  fi
}

run_check '[1/4] Checking the working-tree patch...' git diff --check
run_check '[2/4] Running Python lint...' uv run ruff check src tests
run_check '[3/4] Running unit tests...' uv run pytest tests/unit

if git status --short -- console | grep -q .; then
  printf '[4/4] Type-checking Studio (console changed)...\n'
  if ! (
    cd console
    pnpm typecheck
  ); then
    failed_checks=$((failed_checks + 1))
  fi
else
  printf '[4/4] Skipping Studio type-check (console unchanged).\n'
fi

if (( failed_checks > 0 )); then
  printf '\nPreflight failed: %d check(s) need attention.\n' "$failed_checks" >&2
  exit 1
fi

printf '\nPreflight passed. You can now create the commit:\n'
printf '  git commit -m %q\n' "$commit_message"
