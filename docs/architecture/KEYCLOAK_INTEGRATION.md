# Keycloak Integration Design

## Purpose

Kavach uses Keycloak for authentication and keeps tenancy, membership, roles,
and permissions in Kavach. This separation allows an identity provider to be
replaced or centrally managed without moving Kavach authorization decisions out
of the platform.

This document defines the browser-to-API authentication flow, Keycloak realm
contract, local bootstrap procedure, and operational failure boundaries.

## Scope and ownership

| Concern | Owner |
| --- | --- |
| User login, sessions, passwords, JWT signing keys | Keycloak |
| Browser login redirect and token refresh | Kavach Studio |
| JWT signature, issuer, expiry, and subject validation | Kavach API |
| Organizations, projects, memberships, roles, permissions | Kavach control plane |
| Policy and governance authorization | Kavach `AuthorizationService` |

Keycloak roles and claims must not be used to bypass Kavach membership or RBAC
checks. The only runtime caller identity trusted by Kavach in Keycloak mode is
the validated JWT `sub` claim.

## Request flow

```text
Browser
  │  1. Open Studio
  ▼
Kavach Studio AuthProvider
  │  2. Keycloak Authorization Code Flow with PKCE (S256)
  ▼
Keycloak realm: kavach
  │  3. Access token
  ▼
Studio API client
  │  4. Authorization: Bearer <access token>
  │     X-Kavach-Organization-Id / X-Kavach-Project-Id
  ▼
Kavach API AuthenticationService
  │  5. Validate RS256 signature with JWKS, issuer, and expiry
  ▼
AuthenticatedPrincipal
  │  6. subject → TenantContext.actor_id
  ▼
AuthorizationService
  │  7. Validate tenant constraint, membership, role, and permission
  ▼
Protected API response
```

Studio initializes Keycloak once in a client-side provider. It does not persist
tokens in `localStorage` or `sessionStorage`. Before each API request, the
central API client obtains a current token and calls `updateToken(30)`. A `401`
causes one refresh-and-retry attempt; repeated `401` responses remain errors.
A `403` is an authorization result and must not redirect the user to login.

## Studio client contract

Studio uses the public Keycloak client `kavach-studio`.

```text
Client authentication: Off
Standard flow: On
PKCE method: S256
Redirect URIs: http://localhost:3000/*
Web origins: http://localhost:3000
```

The browser client never receives a client secret. Its required build-time
configuration is:

```env
NEXT_PUBLIC_KAVACH_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_KEYCLOAK_URL=http://keycloak.localhost:8080
NEXT_PUBLIC_KEYCLOAK_REALM=kavach
NEXT_PUBLIC_KEYCLOAK_CLIENT_ID=kavach-studio
```

These variables are compiled into the Next.js browser bundle. Docker builds
must provide them as `kavach-studio` build arguments; runtime-only changes do
not update an already-built Studio image.

## VS Code MCP client contract

The local realm also defines `kavach-mcp-vscode`, a public Authorization Code
client with PKCE S256 and loopback redirect URIs. Its access-token audience
mapper adds `http://localhost:8002/mcp`. This must remain equal to the MCP
service's `KAVACH_MCP_PUBLIC_URL` plus its configured MCP path, because the
MCP service rejects tokens intended for any other resource.

## JWT contract

The API requires these verified JWT claims:

| Claim | Use |
| --- | --- |
| `iss` | Must equal `KAVACH_OIDC_ISSUER`. |
| `exp` | Token expiry validation. |
| `sub` | Immutable Kavach runtime actor ID. Required. |
| `azp` or `client_id` | Authenticated client identifier for observability. |
| `organization_id` | Optional tenant constraint. |
| `principal_type` | Optional mapping to USER, SERVICE, or SYSTEM. |

The realm must attach the standard `oidc-sub-mapper` to `kavach-studio` with
the access-token claim enabled. Kavach rejects a token without `sub`; it does
not fall back to username, email, or a client ID.

Keycloak lightweight tokens omit identity claims unless explicitly mapped. The
local realm disables lightweight tokens for Studio and maps `sub` directly as a
defense in depth measure.

## Tenant and authorization rules

The client supplies requested tenant scope through:

```http
X-Kavach-Organization-Id: <organization>
X-Kavach-Project-Id: <optional project>
```

The client never supplies the runtime actor ID in Keycloak mode. Kavach creates
the tenant context from the verified principal:

```text
organization_id = requested header value
project_id      = requested header value
actor_id        = principal.subject
request_id      = request metadata or generated value
```

If the JWT contains `organization_id`, it must equal the requested organization.
Kavach then requires an active membership and a role assignment that grants the
requested permission. The resulting rule is:

```text
JWT organization constraint
AND active Kavach membership
AND Kavach role assignment
AND required Kavach permission
```

Target actor fields in membership and role-management requests remain explicit
operation inputs. They are distinct from the authenticated caller.

## Membership persistence and provisioning

Authentication does not create a membership implicitly. A valid Keycloak token
establishes *who* is calling (`sub`); Kavach's control-plane repository decides
whether that actor belongs to an organization and which permissions it has.

For every organization an actor may access, Kavach persists one membership
identified by the composite key:

```text
organization_memberships.organization_id + organization_memberships.actor_id
```

`actor_id` is the immutable Keycloak `sub` value, not a Keycloak username,
email address, or client ID. The record stores an optional display name,
membership status, and creation/update timestamps. Only `ACTIVE` memberships
can authorize requests or make an organization visible in the organization
list.

```text
verified JWT sub
       │
       ├── organization_memberships(organization_id, actor_id, status=ACTIVE)
       │       └── required before any role assignment can exist
       │
       └── role_assignments(organization_id, project_id?, actor_id, role)
               └── grants the permission after membership is confirmed
```

The control plane creates the membership in either of these ways:

- Creating an organization creates an active membership and an
  organization-wide `ORGANIZATION_ADMIN` assignment for its creator.
- A caller with `membership.manage` can add an explicit active membership for
  another actor, then assign organization- or project-scoped roles.
- Local bootstrap creates the initial admin membership from
  `KAVACH_BOOTSTRAP_ADMIN_SUB` only when the control-plane database is empty.

Changing a Keycloak user's `organization_id` or `project_ids` attributes does
not provision a Kavach membership or role. Those claims constrain the tenant
scope accepted from that token; membership and role records remain the source
of authorization truth. For the local `studio`, the stable subject in the
realm definition, `KAVACH_BOOTSTRAP_ADMIN_SUB`, and the persisted membership
must match.

The repository contract is persistence-independent. The in-memory repository
uses a dictionary keyed by `(organization_id, actor_id)` for tests and
lightweight development; the SQLite repository persists the same model in
`organization_memberships`; PostgreSQL uses the equivalent table in production.
This makes membership behavior identical across repository implementations.

## Local realm and bootstrap

The local realm definition is
`keycloak-postgres/keycloak/kavach-realm.json`. It defines:

- Realm `kavach`.
- Public Studio client `kavach-studio`.
- Subject mapper and tenant attribute mappers.
- Local `studio` user with stable subject ID.
- `organization_id=org_default` and `project_ids=project_default` user
  attributes.

Keycloak 26 user profiles ignore unmanaged custom user attributes by default.
The local realm therefore enables `unmanagedAttributePolicy: ENABLED` so the
tenant attributes are retained and can be mapped into tokens.

The platform's local Compose configuration sets
`KAVACH_BOOTSTRAP_ADMIN_SUB` to the same stable Keycloak subject. On a clean
Kavach control-plane database, bootstrap creates the initial membership and
organization-wide `ORGANIZATION_ADMIN` role assignment for that subject.

`KAVACH_BOOTSTRAP_ADMIN_SUB` is bootstrap-only. It must not be used to identify
or impersonate a runtime caller.

## Local startup

```bash
./scripts/keycloak/start-keycloak.sh
./kavach.sh
```

Open Studio at `http://localhost:3000` and sign in as `studio` using the
password configured by `KAVACH_STUDIO_PASSWORD` in the local Keycloak env file.

Keycloak imports the realm JSON only for a new PostgreSQL volume. To recreate a
disposable local Keycloak realm:

```bash
cd keycloak-postgres
docker compose down -v
cd ..
./scripts/keycloak/start-keycloak.sh
```

This deletes Keycloak users, sessions, client configuration, and signing state.

## Failure handling

| Response | Meaning | Operator action |
| --- | --- | --- |
| `401 missing_authorization` | Studio did not send a bearer token. | Rebuild Studio and verify public Keycloak build arguments. |
| `401 missing_claims` | JWT lacks `sub` or another required claim. | Verify the `oidc-sub-mapper` and disable lightweight tokens for Studio. |
| `401 invalid_signature` | JWT does not match current Keycloak JWKS. | Verify issuer/JWKS reachability and reauthenticate. |
| `403 TENANT_SCOPE_MISMATCH` | Requested tenant differs from JWT constraint or membership scope. | Align Keycloak tenant attributes, Studio selection, and Kavach membership. |
| `403 authorization_denied` | Authenticated actor lacks Kavach permission. | Add or adjust Kavach membership/role assignment; do not change Keycloak roles. |

## Security properties

- Studio uses Authorization Code Flow with PKCE, never a browser client secret.
- Tokens are held only in memory.
- The API validates JWT signing keys, issuer, and expiry before constructing a
  principal.
- Runtime identity is always the validated `sub` claim.
- Bootstrap configuration cannot impersonate callers after startup.
- Keycloak tenant claims constrain tenant scope but never grant permissions.
- Authorization decisions remain in Kavach and are auditable through its
  existing authorization and control-plane audit mechanisms.
