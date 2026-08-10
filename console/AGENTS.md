# Scope

This directory owns the Next.js AI Governance Control Plane Studio frontend.

## Architectural Facts

- Studio consumes REST through `console/lib/api/`; backend services remain the
  authority for governance and authorization decisions.
- `TenantContextProvider` holds the selected organisation and project for the
  browser experience. It is UI state, not a server-side authorization source.
- `console/auth` owns Keycloak token acquisition. Runtime configuration is read
  through `console/lib/runtime-config.ts`.

## Change Rules

- Do not reproduce backend policy, lifecycle, or authorization logic in the
  UI. A hidden control or client-side permission check does not protect an API.
- Keep REST types and client calls aligned with public contracts; do not fork
  generated or shared API shapes into unrelated client stores.
- Treat loading, empty, partial-failure, and permission-denied states as
  product states. Keep filters and selected entities deep-linkable where the
  existing page pattern supports it.
- Do not place access tokens or tenant selection in URLs or client logs.
  Tenant selection may change presentation but never authorizes access.
- Maintain accessible labels, keyboard operation, and stable selectors for new
  controls.

## Validation

From `console/`, run `pnpm lint` and `pnpm typecheck`. Run the relevant page
or API-client checks when changing a contract consumer.
