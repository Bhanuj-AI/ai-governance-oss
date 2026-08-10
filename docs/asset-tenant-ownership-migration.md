# Asset Tenant Ownership Migration

Prompt and Model registry records persist `tenant_id`, `organization_id`,
and `project_id`. Dataset records already carried organization/project scope.
Repository reads for prompts and models require organization and project scope,
preventing cross-tenant reads through the catalog API.

## Migration and Backfill

SQLite initialization adds missing ownership columns for legacy registries and
backfills them to `AI_GOVERNANCE_BOOTSTRAP_ORGANIZATION_ID` and
`AI_GOVERNANCE_BOOTSTRAP_PROJECT_ID` (or `org_default` / `project_default`).
PostgreSQL initialization uses idempotent `ALTER TABLE ... ADD COLUMN IF NOT
EXISTS` statements and assigns legacy `tenant_id` values from the persisted
organization. Both stores add a tenant-scope index.

The deterministic bootstrap backfill is appropriate only for a known
single-tenant legacy database. A multi-tenant database with ambiguous legacy
asset ownership must be administratively partitioned before migration; the
application does not infer ownership from names, tags, actors, or requests.

## Rollback

The prior application version ignores the new columns, so application rollback
does not require data deletion. Keep the ownership columns and indexes in
place. Dropping them would remove tenant-isolation evidence and is not a safe
rollback procedure.
