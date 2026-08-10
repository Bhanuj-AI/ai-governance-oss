# Scope

This directory owns application use-case orchestration across domain contracts,
repositories, authorization, audit, events, jobs, settings, and providers.

## Architectural Invariants

- Services own transaction-level ordering and failure semantics. They do not
  own HTTP routing, UI state, or persistence-engine SQL.
- Authorize before a protected read or mutation, using the supplied
  `TenantContext` rather than a caller-provided tenant value.
- Retryable workflows must be idempotent. Provider failures must not leave
  ambiguous local state; final committed outcomes carry the relevant audit and
  actor context.
- Replay orchestration preserves frozen source evidence. It can schedule new
  work and record results, but must not mutate the historical source execution
  to make a replay succeed.

## Change Rules

- Keep services directly testable with repository and provider fakes.
- Make the ordering of durable writes, event publication, provider calls, and
  job submission explicit when a use case crosses those boundaries.
- Delegate deterministic policy evaluation to the governance decision and
  policy contracts; do not reproduce it in a transport adapter.

## Validation

Use focused tests under `tests/unit/`, `tests/integration/`, and `tests/workers/`
for the changed use case. For policy or decision work, use
`skills/governance-policy/SKILL.md`.
