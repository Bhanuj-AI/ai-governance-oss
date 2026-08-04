# Multi-organization tenancy and RBAC

Kavach resolves authorization from an explicit `TenantContext`; resources are
never authorized from client-provided roles or permission claims. The REST
transport accepts organization and project selectors through
`X-Kavach-Organization-Id` and `X-Kavach-Project-Id`. The actor identity comes
from the authentication layer:

- **Development mode** — `X-Kavach-Actor-Id` header or
  `KAVACH_DEVELOPMENT_ACTOR_ID` environment variable.
- **Keycloak mode** — JWT `sub` claim from a validated Bearer token.

Request IDs are generated when absent and correlation IDs are preserved.

The permission model is version `1`. Built-in roles and their immutable mapping
live in `kavach.tenancy.permissions`. Authorization denies by default, checks
active membership, resolves organization-wide plus selected-project role
assignments, and returns a stable reason code.

Local development bootstraps `org_default`, `project_default`, the
`local-admin` membership, and an organization-administrator assignment. All
values can be set with the `KAVACH_BOOTSTRAP_*` and
`KAVACH_DEVELOPMENT_ACTOR_*` environment variables.

In keycloak mode, the initial administrator is provisioned using
`KAVACH_BOOTSTRAP_ADMIN_SUB` (the Keycloak user `sub`) instead of
`KAVACH_DEVELOPMENT_ACTOR_ID`. The bootstrap operation is idempotent in both
modes — repeated startup does not create duplicate organizations or memberships.

| Variable | Default | Purpose |
| --- | --- | --- |
| `KAVACH_DEVELOPMENT_ACTOR_ID` | `local-admin` | Actor ID for the initial administrator in development mode. |
| `KAVACH_DEVELOPMENT_ACTOR_NAME` | `Local Administrator` | Display name for the initial administrator in development mode. |
| `KAVACH_BOOTSTRAP_ADMIN_SUB` | - | Keycloak user `sub` for the initial administrator in keycloak mode. Required when `KAVACH_AUTH_MODE=keycloak`. |
| `KAVACH_BOOTSTRAP_ADMIN_NAME` | - | Display name for the initial administrator in keycloak mode. Optional. |

## Authentication and authorization separation

Authentication establishes identity; authorization determines permissions. The
two planes are strictly separated:

- The authentication plane (Keycloak or development) validates tokens and builds
  an `AuthenticatedPrincipal`. It never grants permissions.
- The authorization plane (`AuthorizationService`) checks memberships, resolves
  role assignments against `ROLE_PERMISSIONS`, and makes all permission decisions.
- JWT claims such as `organization_id` or `principal_type` are informational only;
  they do not bypass the RBAC model.

This separation ensures that Keycloak is never the source of truth for Kavach
authorization. Removing or modifying realm roles in Keycloak has no effect on
Kavach permissions.

When a JWT includes `organization_id`, Kavach treats it as a tenant constraint:
the requested organization must match it. The claim does not grant access;
active Kavach membership and a role assignment are still required. See the
[Keycloak integration design](./KEYCLOAK_INTEGRATION.md) for the complete
identity-to-tenant flow.

Control-plane endpoints are rooted at `/api/v1/organizations`; the current
resolved identity, roles, permissions, and selected scope are exposed by
`GET /api/v1/context`. Organization and project records use archival rather
than deletion. Membership and assignment removal protects the last active
organization administrator.

## Built-in roles

The five built-in roles are read-only definitions. `ORGANIZATION_ADMIN` owns
all version-1 permissions. `GOVERNANCE_ADMIN` manages policies, decisions,
evaluations, jobs, synchronization, and governance audit. `GOVERNANCE_REVIEWER`
can read and publish review-ready governance state. `PLATFORM_OPERATOR` runs
jobs, evaluations, retries, cancellation, and ontology reconciliation.
`VIEWER` has project governance read access. The checked-in exhaustive matrix
test fails whenever a permission or role is added without an explicit mapping.

Organization-wide assignments use a null `project_id`; project assignments
apply only in the selected project. Membership must be active before any role
can authorize an operation. Membership or assignment revocation is immediately
consistent and the last active organization administrator is protected.

## Persistence and migration

Set `KAVACH_TENANCY_REPOSITORY` to `inmemory`, `sqlite`, or `postgres`. SQLite
requires `KAVACH_TENANCY_SQLITE_PATH`; PostgreSQL requires
`KAVACH_TENANCY_POSTGRES_DSN`. Both relational schemas contain organization,
project, membership, and assignment constraints plus tenant-aware indexes.

SQLite initialization performs an idempotent compatibility migration. Existing
policy, decision, job, evaluation, experiment, registry, ontology-event, and
audit rows are backfilled into the configured bootstrap scope. PostgreSQL uses
idempotent `ADD COLUMN IF NOT EXISTS` migration statements. Backup the database
before upgrading; rollback consists of restoring that backup because tenant
ownership columns deliberately remain non-null after migration.

Jobs persist a `JobExecutionContext` containing organization, project, actor,
request, and correlation identity. Workers use this record and never infer
scope from job payloads. Job idempotency hashes and database uniqueness include
organization and project scope.

Ontology nodes and relationships carry organization and project properties.
Neo4j uniqueness, endpoint matching, and traversal entry predicates include
both values, preventing identifiers and paths from crossing tenant boundaries.

## Production identity guardrail

`KAVACH_AUTH_MODE=development` logs a critical warning. A production
environment rejects it unless
`KAVACH_ALLOW_DEVELOPMENT_IDENTITY_IN_PRODUCTION=true` is explicitly set.
