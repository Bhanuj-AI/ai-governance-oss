---
name: tenant-isolation
description: Implement, review, or test AI Governance Control Plane authentication, authorization, tenant context propagation, and tenant data isolation. Use for protected reads or writes, repositories, workers, audit records, cache and ontology access, external-provider calls, and any change that could expose one tenant's data to another.
---

# Tenant Isolation

Treat tenant and actor context as mandatory security input for every protected
operation.

## Workflow

1. Read root `AGENTS.md` and `src/ai_governance/tenancy/AGENTS.md`, then read the scoped
   instructions for each changed transport, service, repository, worker, or
   provider layer.
2. Trace the context from authenticated principal through the approved context
   dependency or factory into the application service and every persistence or
   provider call.
3. Authenticate first, authorize second, then access data. Deny by default
   when context is missing, invalid, or ambiguous.
4. Scope every lookup, list, idempotency key, event, audit record, cache entry,
   ontology identifier, and external request by organisation and project where
   applicable.
5. Add a negative test: create or request the same identifier in two tenants,
   then prove that each tenant can see only its own resource.
6. Do not log raw tokens, secrets, or unnecessary identity attributes.

## Context pattern

Pass the established immutable context; do not rebuild it from client-supplied
values inside application code.

```python
@dataclass(frozen=True)
class TenantContext:
    organization_id: str
    project_id: str | None
    actor_id: str
    request_id: str
    correlation_id: str | None = None
```

For an API route, depend on `get_compatible_tenant_context` and pass the
resulting `context` to the service. For a worker, reconstruct only the
tenant context captured when the job was submitted; never accept a new caller
scope for an existing job.

## Isolation test pattern

Make collisions intentional. The current integration test submits the same
input and idempotency key in two tenant scopes, then verifies that IDs and
lists do not cross the boundary. Use the same approach for the resource being
changed.

```python
assert repository.find_by_id("job_a", "org_b", "project_b") is None
assert repository.list_jobs(
    organization_id="org_a", project_id="project_a"
) == [first]
```

## Verify

Run the integration test first, followed by the closest protected API, service,
or worker test:

```bash
uv run ruff check src/ai_governance/tenancy
uv run pytest tests/integration/test_tenant_isolation.py
```

When a change spans a repository, worker, audit path, ontology projection, or
provider call, add a focused negative test in that boundary as well.
