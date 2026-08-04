# Scope

This directory owns the FastAPI REST boundary: routers, transport models,
dependencies, mappers, and HTTP error translation.

## Architectural Facts

- `src/kavach/api/app.py:create_app` composes routers and authorization
  dependencies.
- `src/kavach/api/dependencies/tenancy.py` resolves request scope; routers use
  `get_compatible_tenant_context` while the tenant migration remains in place.
- Repository factories are reached through dependency providers such as
  `src/kavach/api/dependencies/repositories.py`, not from routes.

## Change Rules

- Keep a router as a transport adapter: validate input, obtain approved
  dependencies, call a service, and map its result. Do not add policy logic,
  SQL, or concrete repository construction here.
- Treat request and response models, route paths, OpenAPI descriptions, and
  stable HTTP errors as public contracts. Preserve existing fields and routes
  unless a versioned change is intentional.
- Pass the resolved `TenantContext` to protected service operations. A request
  payload cannot establish tenant scope.
- Keep collection order and pagination bounds explicit. State-changing
  operations that can be retried need the existing idempotency semantics.

## Validation

Run the closest API test module under `tests/api/`; decision and policy API
contracts are covered by `tests/api/test_decision_api.py` and
`tests/api/test_policy_administration_api.py`.

For the task workflow, use `skills/api-change/SKILL.md`.
