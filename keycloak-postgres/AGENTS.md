# Scope

This directory owns the local Keycloak and PostgreSQL topology, realm import,
and identity-development configuration.

## Architectural Facts

- `docker-compose.yml` defines the local `postgres` and `keycloak` services.
- `keycloak/ai-governance-realm.json` is the imported realm contract used by local
  Keycloak development.
- The API validates Keycloak credentials through its authentication and tenant
  context dependencies; this topology must remain compatible with that flow.

## Change Rules

- Treat realm clients, roles, scopes, redirect URIs, origins, and audience
  configuration as security contracts. Do not weaken them or commit real
  credentials for local convenience.
- Preserve the PostgreSQL volume and realm-import compatibility unless an
  intentional reset is documented. Local identity changes can invalidate
  existing developer sessions and client credentials.
- Keep least-privilege role assignments and the expected login or
  client-credentials flow aligned with `src/ai_governance/tenancy`.

## Validation

From this directory, run
`docker compose --env-file .env.keycloak -f docker-compose.yml config --quiet`,
then validate the affected local login or client-credentials flow against a
clean startup.
