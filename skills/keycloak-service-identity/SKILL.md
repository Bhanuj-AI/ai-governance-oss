---
name: keycloak-service-identity
description: Provision or rotate a local Keycloak confidential service identity and its AI Governance Control Plane authorization without treating Keycloak claims as permissions.
---

# Keycloak Service Identity

Use this skill when adding, rotating, or repairing a machine identity that calls
AI Governance Control Plane. It does not apply to browser users or to changing
the semantic permissions of a domain feature.

Keycloak authenticates the workload. AI Governance Control Plane owns the
organization membership, project scope, roles, and permissions. The runtime
actor ID is always the validated Keycloak service-account user's immutable
`sub`; never invent it, copy a client UUID, or accept it from the caller.

## Workflow

1. Read root `AGENTS.md`, `keycloak-postgres/AGENTS.md`, and the scoped
   tenancy/API instructions for every control-plane layer changed.
2. Inspect the closest existing confidential client, its claim mappers, and
   `scripts/keycloak/get-service-account-actorids.sh` before editing the realm
   import contract.
3. Keep Keycloak limited to identity and token-scope claims. Add membership and
   the least-privilege project role through the control plane.
4. Validate the realm import and Compose configuration, then prove both the
   intended authenticated request and a denied, ungranted operation.

## Local realm contract

1. Add a dedicated confidential client to
   `keycloak-postgres/keycloak/ai-governance-realm.json` with a secret supplied
   through `keycloak-postgres/.env.keycloak`/Compose interpolation. Enable
   service accounts and client credentials; disable browser and direct-grant
   flows unless they are explicitly needed.
2. Keep tenant claims limited to the intended organization and project. Claims
   constrain scope only; they do not grant control-plane permissions.
3. Extend `scripts/keycloak/get-service-account-actorids.sh` to resolve the
   client’s service-account user through the Keycloak Admin API and write an
   appropriately named `AI_GOVERNANCE_*_ACTOR_ID` to the ignored generated env
   file. The generated file is the only local hand-off of that `sub`.
4. Provision an active membership and the narrowest project-scoped role in the
   control plane from that generated environment variable. Do not use Keycloak
   realm/client roles as an authorization substitute.

Read `keycloak-postgres/Keycloak Authentication Setup.md` for the local
topology and `docs/architecture/KEYCLOAK_INTEGRATION.md` before changing token
claims or tenant-context behavior.

## Realm resets and identity rotation

Keycloak imports the realm only into a new Keycloak PostgreSQL volume. A fresh
realm gives every service account a new `sub`, so first regenerate the actor-ID
file, then provision the new membership and role. Retire the previous
control-plane memberships through the supported membership API/UI after the new
identity has been validated; do not delete rows directly from persistence.

For an intentional local realm reset, document its scope and use the
`keycloak-postgres` Compose project only. Never remove unrelated platform data
or print, commit, or persist client secrets and access tokens.

## Verification

Validate the realm JSON and Compose configuration, start from a clean local
realm when the import changed, acquire a client-credentials token, and perform
an authenticated call under the expected organization and project. Include a
negative authorization check for an ungranted permission or another project.
The workload must refresh an expiring token and retry a `401` only once.
