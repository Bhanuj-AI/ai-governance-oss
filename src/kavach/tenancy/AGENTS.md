# Scope

This directory owns authenticated identity, `TenantContext`, RBAC,
authorization, control-plane tenancy records, and tenant-isolation rules.

## Architectural Facts

- `AuthenticatedPrincipal` is the identity derived from validated credentials.
  `TenantContextFactory` maps its subject to `TenantContext.actor_id` and
  carries organisation, project, request, and correlation scope.
- REST context resolution is owned by
  `src/kavach/api/dependencies/tenancy.py`. In Keycloak mode it uses a
  validated principal; development-mode headers are checked against the
  control-plane repository.
- `AuthorizationService` owns authorization decisions. The context factory does
  not resolve memberships or permissions.

## Architectural Invariants

- Authenticate before authorizing and authorize before protected data access.
  Missing, invalid, or ambiguous context is denied.
- Scope every data path server-side, including jobs, audit, ontology, cache,
  and provider interactions. A matching identifier in another organisation or
  project must not be observable.
- Never accept an unverified decoded claim as identity or construct a protected
  scope from an arbitrary request field.

## Change Rules

- Preserve `request_id` and `correlation_id` when work crosses a transport or
  becomes an asynchronous job.
- Do not log raw tokens, secrets, or unnecessary identity attributes.
- Keep negative cross-tenant and insufficient-permission tests with every new
  protected access path.

## Validation

Run `tests/integration/test_tenant_isolation.py` and the closest unit or API
test under `tests/unit/tenancy` or `tests/api/`.

For the task workflow, use `skills/tenant-isolation/SKILL.md`.
