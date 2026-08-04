# Scope

This directory owns persistence-neutral repository contracts, record mappers,
backend implementations, and backend-selection factories.

## Architectural Facts

- Repository interfaces expose domain types; driver rows and database handles
  stay inside backend implementations and mappers.
- `src/kavach/repositories/factories` selects the configured implementation.
  API dependency providers call those factories after settings resolution.
- Contract tests live in `tests/repositories/contract`; factory and mapper
  tests live alongside them.

## Architectural Invariants

- Require explicit organisation and project scope for tenant-owned queries.
  API filtering is insufficient because repositories are also used by services
  and workers.
- Preserve equivalent lifecycle, ordering, idempotency, and error semantics
  across in-memory, SQLite, PostgreSQL, Snowflake, and ontology-backed paths
  where a contract supports them.
- Keep backend-specific behavior out of public repository contracts. A concrete
  implementation must not define a different domain rule.

## Change Rules

- Do not instantiate SQLite or PostgreSQL repositories from services or API
  code; doing so bypasses backend selection and couples use cases to a
  deployment.
- Use deterministic ordering for pagination. Make retryable mutations
  idempotent and use explicit versioning or compare-and-set semantics when a
  write is concurrency-sensitive.
- Change schemas through the database boundary and cover compatibility there.

## Validation

Run the relevant contract, factory, mapper, and backend test under
`tests/repositories/`. Run `tests/integration/test_tenant_isolation.py` when a
tenant-scoped query changes.
