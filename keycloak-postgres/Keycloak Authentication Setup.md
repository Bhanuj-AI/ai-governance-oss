# AI Governance Control Plane Local Development: Keycloak Authentication Setup

## Purpose

AI Governance Control Plane Studio uses Keycloak for browser authentication. The Studio sends Keycloak access tokens to the AI Governance Control Plane API, while AI Governance Control Plane remains responsible for tenant membership, roles, and permissions.

Local services:

| Service | URL |
|---|---|
| AI Governance Control Plane Studio | `http://localhost:3000` |
| AI Governance Control Plane API | `http://localhost:8000` |
| Keycloak | `http://keycloak.localhost:8080` |
| Keycloak realm | `ai-governance` |
| Studio client | `ai-governance-studio` |

## Architecture

```text
Browser
  → Keycloak login (Authorization Code + PKCE)
  → Studio receives access token
  → Studio API client adds Authorization: Bearer <token>
  → AI Governance Control Plane API validates JWT via Keycloak JWKS
  → AI Governance Control Plane evaluates tenant membership and role permissions
```

Keycloak owns identity. AI Governance Control Plane owns organization membership, role assignments, and governance authorization.

## Local configuration

Studio uses these public environment variables:

```env
NEXT_PUBLIC_AI_GOVERNANCE_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_KEYCLOAK_URL=http://keycloak.localhost:8080
NEXT_PUBLIC_KEYCLOAK_REALM=ai-governance
NEXT_PUBLIC_KEYCLOAK_CLIENT_ID=ai-governance-studio
```

The API uses:

```env
AI_GOVERNANCE_AUTH_MODE=keycloak
AI_GOVERNANCE_OIDC_ISSUER=http://keycloak.localhost:8080/realms/ai-governance
AI_GOVERNANCE_BOOTSTRAP_ADMIN_SUB=e44566f1-c748-45e1-83db-d2ee5fb424ef
```

`AI_GOVERNANCE_BOOTSTRAP_ADMIN_SUB` is startup/bootstrap-only. It must never be used as a runtime caller identity.

## Machine identities used by local validation

The local validation flow uses two existing Keycloak service accounts. A
service account is a non-human login used by software, not an additional
person or tenant.

| Keycloak client | Purpose | OSS access |
|---|---|---|
| `synthetic-agent-runtime` | Sends simulated agent executions and events. | Ingest-only, scoped to `org_default/project_default`. |
| `ai-governance-service` | Runs the Causal Audit validator after an execution is observed. | Project-scoped external-runtime operator in `org_default/project_default`. |

The validator identity is deliberately separate from the simulator identity:
the simulator cannot grant itself audit permissions. Keycloak supplies the
immutable `sub` for each service account; AI Governance Control Plane stores
the membership and role. Use
`scripts/keycloak/get-service-account-actorids.sh` to resolve the existing
subjects. It does not create clients, users, or duplicate identities. The
Keycloak startup launcher reconciles the local `synthetic-agent-runtime`
client and its required scope claims when an existing development volume
predates this capability.

## Start the platform

From the repository root:

```bash
./servers.sh
```

This builds and starts Studio, API, and Neo4j.

Keycloak is started by the root launcher. To start only Keycloak:

```bash
./scripts/keycloak/start-keycloak.sh
```

Verify:

```bash
docker compose ps
cd keycloak-postgres && docker compose ps
```

## Local login

Use the realm user configured in:

```text
keycloak-postgres/.env.keycloak
```

```text
Username: studio
Password: value of AI_GOVERNANCE_STUDIO_PASSWORD
```

After login, Studio should load tenant-scoped pages without `401` or `403` responses.

## Keycloak realm requirements

The `ai-governance-studio` client must be configured as:

```text
Client authentication: Off
Standard flow: On
PKCE method: S256
Valid redirect URIs: http://localhost:3000/*
Web origins: http://localhost:3000
```

The client must include a subject mapper:

```text
Protocol mapper: oidc-sub-mapper
Access token claim: enabled
ID token claim: enabled
```

This is essential because AI Governance Control Plane uses JWT `sub` as the immutable runtime actor ID.

The realm user must have tenant attributes:

```json
{
  "organization_id": ["org_default"],
  "project_ids": ["project_default"]
}
```

Keycloak user profile configuration must permit these custom attributes:

```json
{
  "unmanagedAttributePolicy": "ENABLED"
}
```

## AI Governance Control Plane tenant bootstrap

The local administrator’s Keycloak subject must be provisioned in AI Governance Control Plane’s control plane with:

```text
Organization: org_default
Membership status: ACTIVE
Role: ORGANIZATION_ADMIN
Project scope: organization-wide
```

The Keycloak subject currently used by local bootstrap is:

```text
e44566f1-c748-45e1-83db-d2ee5fb424ef
```

For new environments, this stable ID is defined in the realm import and referenced by `AI_GOVERNANCE_BOOTSTRAP_ADMIN_SUB`.

### Changing the local bootstrap administrator

The local bootstrap administrator is an explicit, paired configuration. Do not
change only one side:

1. Update the initial user's `id` in
   [`keycloak/ai-governance-realm.json`](keycloak/ai-governance-realm.json).
2. Update `AI_GOVERNANCE_BOOTSTRAP_ADMIN_SUB` in the root `docker-compose.yml` to the
   identical value.

AI Governance Control Plane creates the initial membership and organization-admin role for that
subject during control-plane bootstrap, before the user signs in. For an
existing local installation, reset both the local Keycloak and AI Governance Control Plane data
volumes (or migrate the existing membership and role assignment) before using
the new subject. Changing only the Keycloak user ID leaves the persisted AI Governance Control Plane
authorization records associated with the previous subject.

## Common issues

### Studio stays on “Signing in…”

Check that the Studio Docker image was rebuilt after changes:

```bash
./servers.sh
```

Check browser console and confirm all `NEXT_PUBLIC_KEYCLOAK_*` variables were supplied as Docker build arguments.

### `401 missing_authorization`

The Studio request started before the token provider was available, or the browser is using an old Studio build.

Hard refresh the page. If needed:

```bash
./servers.sh
```

### `401 missing_claims: JWT missing subject claim`

The `ai-governance-studio` Keycloak client is missing the `oidc-sub-mapper`.

Ensure the client emits `sub` in access tokens. Do not fall back to username or email for runtime identity.

### `403 TENANT_SCOPE_MISMATCH`

The JWT `organization_id` does not match the organization selected in Studio.

For local development, confirm:

```text
JWT organization_id = org_default
Studio organization = org_default
AI Governance Control Plane membership organization = org_default
```

Log out and back in after changing Keycloak attributes so a new token is issued.

### Realm JSON changes do not take effect

Keycloak imports realm JSON only when the realm/database is created. Existing PostgreSQL volumes retain the old realm configuration.

For a disposable local reset:

```bash
cd keycloak-postgres
docker compose down -v
cd ..
./scripts/keycloak/start-keycloak.sh
```

Warning: this deletes local Keycloak data.

## Developer checklist

- [ ] Keycloak is running and healthy.
- [ ] Studio is built with `NEXT_PUBLIC_KEYCLOAK_URL`, realm, and client ID.
- [ ] API runs with `AI_GOVERNANCE_AUTH_MODE=keycloak`.
- [ ] JWT issuer matches `AI_GOVERNANCE_OIDC_ISSUER`.
- [ ] Studio token includes `sub`.
- [ ] JWT tenant claim matches Studio tenant selection.
- [ ] Keycloak subject has an active AI Governance Control Plane membership.
- [ ] Keycloak subject has required AI Governance Control Plane role assignments.
- [ ] No client secret is placed in Studio configuration.
