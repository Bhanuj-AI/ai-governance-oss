# Scope

This file governs the Kavach OSS repository. Child `AGENTS.md` files refine
these rules for their own directories.

## Purpose

Kavach OSS is an independently usable governance control plane for AI
workflows and governed assets. Preserve explicit ownership of governance state,
evidence, policy, audit, replay and persistence contracts.

## Architectural Facts

- `src/kavach/api`, `src/kavach/mcp`, and `src/kavach/cli` are transport
  adapters. `src/kavach/services` coordinates use cases; domain contracts and
  repository interfaces remain below that layer.
- Repository backend selection is a control-plane concern owned by the
  factories in `src/kavach/repositories/factories/`; API dependency providers
  compose factories with settings. Do not choose a concrete backend in a
  service or adapter.
- Extensions use the public `KavachPlugin` and SPI (Service Provider Interfaces) contracts. OSS discovers
  entry points in the `kavach.plugins` group and does not import or detect a
  separately installed Enterprise distribution. See
  `docs/architecture/EXTENSIBILITY.md`.
- The current tree still contains Enterprise-named settings. Optional
  Enterprise MCP tools are discovered through the `kavach.mcp.plugins` entry
  point rather than OSS environment switches. Do not add dependencies on an
  Enterprise distribution from OSS.

## Core / Enterprise Extension Boundary

Kavach Core owns stable, generic contracts. Enterprise owns its business
concepts, semantics, validation, persistence, metrics, routes and handlers.
Do not add an Enterprise business concept to Core when it can be carried by an
existing plugin, SPI, handler, event, or provider extension point.

Before editing Core for an Enterprise feature:

1. Inspect the existing extension points and use the narrowest one that can
   carry the feature.
2. Prefer an Enterprise-owned, namespaced, versioned operation or payload over
   a feature-specific Core enum, route, setting, persistence table, or import.
3. Treat a proposed Core symbol containing an Enterprise feature name (for
   example `SLO`, `Impact`, or `Contract`) as a boundary violation unless its
   generic ownership is explicitly demonstrated.
4. Introduce a Core change only when it is generic, has no Enterprise
   dependency, and has at least two plausible independent consumers.
5. Before making any Core edit, state the proposed generic contract, explain
   why the existing extension points are insufficient, and obtain explicit
   approval.

Core extension contracts must remain open for plugin implementation but closed
to plugin-specific semantic changes.

## Architectural Invariants

```text
REST / MCP / CLI adapters
            ↓
application services and analyzers
            ↓
domain and repository contracts
            ↓
storage or provider implementations
```

- Adapters do not own domain decisions or persistence selection. Services do
  not contain storage-engine SQL. Storage implementations do not create
  alternative domain semantics.
- Public REST, MCP, CLI, SPI, event, and persisted-artifact contracts evolve
  compatibly unless a deliberate versioned change is made.
- Governance decisions must be deterministic, explainable, and auditable.
  Replay source evidence and finalized decision records are historical
  evidence, not mutable working state.
- Resolve tenant scope through the approved runtime path. REST uses
  `get_tenant_context` or `get_compatible_tenant_context` in
  `src/kavach/api/dependencies/tenancy.py`; Keycloak mode constructs context
  from a validated `AuthenticatedPrincipal` with `TenantContextFactory`.
  Development-mode scope headers are validated against the control plane; they
  are not a replacement for server-side authorization.
- Carry `TenantContext` through protected reads, writes, jobs, audit records,
  ontology operations, and provider calls. Do not bypass scope enforcement by
  direct repository access.
- Do not log credentials, raw tokens, protected prompt content, or
  tenant-sensitive data.

## Degrees of Freedom

### Low freedom

Follow established contracts exactly for authentication and authorization,
tenant context, repository selection, public compatibility, idempotency,
settings precedence, audit persistence, replay source evidence, and
deterministic ontology identifiers.

### Medium freedom

Follow the nearest established pattern for services, adapters, repository
implementations, workers, provider integrations, and Studio pages.

### High freedom

Use judgement for behavior-preserving internal refactors, documentation
organisation, test helpers, and developer tooling that do not alter the
contracts above.

## Repository Skills

Use skills for repeatable task workflows; they do not replace these
architectural constraints.

- `skills/api-change/SKILL.md`
- `skills/domain-feature/SKILL.md`
- `skills/governance-policy/SKILL.md`
- `skills/tenant-isolation/SKILL.md`

## Related Guidance

- `src/kavach/api/AGENTS.md`
- `src/kavach/domain/AGENTS.md`
- `src/kavach/repositories/AGENTS.md`
- `src/kavach/services/AGENTS.md`
- `src/kavach/tenancy/AGENTS.md`
- `src/kavach/workers/AGENTS.md`
- `docs/architecture/ARCHITECTURE.md`
