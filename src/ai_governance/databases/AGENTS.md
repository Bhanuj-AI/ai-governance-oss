# Scope

This directory owns engine-specific database access and schema assets for
SQLite, PostgreSQL, and Snowflake.

## Architectural Facts

- Concrete repository implementations live under `src/ai_governance/repositories`;
  this directory provides the database and schema primitives they use.
- Backend selection belongs to repository factories, not database modules.
- PostgreSQL migration tooling is exposed through
  `src/ai_governance/databases/postgres/cli.py`.

## Change Rules

- Preserve the repository contract's semantics across supported storage
  backends. An optimization is not valid if it changes lifecycle, ordering,
  tenant scope, or failure behavior for one backend.
- Make schema evolution forward-compatible with persisted data. Do not silently
  repair or reinterpret invalid domain state in a database adapter.
- Keep transaction and rollback boundaries explicit where one operation changes
  multiple records. Tenant-owned indexes and queries must retain organisation
  and project scope.

## Validation

Use the matching tests in `tests/repositories/sqlite`,
`tests/repositories/postgres`, or `tests/repositories/snowflake`; run migration
coverage when changing schema or migration code.

See `src/ai_governance/repositories/AGENTS.md` for the public persistence contracts.
