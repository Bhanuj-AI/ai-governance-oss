---
name: api-change
description: Implement or modify a AI Governance Control Plane REST API endpoint, request or response model, router, mapper, dependency, or HTTP error mapping. Use for backwards-compatible API additions, contract changes, pagination, authorization, idempotent write endpoints, and API-focused tests.
---

# API Change

Implement a REST change as a transport adapter over an application service.

## Workflow

1. Read root `AGENTS.md` and `src/ai_governance/api/AGENTS.md`. Read the service,
   tenancy, repository, or domain instructions for every layer changed.
2. Inspect the existing router, request/response models, mapper, dependency
   provider, and closest API test before choosing the public contract.
3. Preserve existing routes and fields. Add a versioned route or an optional
   field when a breaking change is not deliberately approved.
4. Put validation and mapping in the adapter. Put business decisions in an
   application service; do not import database implementations into a router.
5. Obtain context through approved dependencies. Pass the resolved context to
   every protected service call; never use an unverified tenant value from the
   body or query string.
6. Bound and validate list pagination. Require authorization and an
   idempotency mechanism where a client or transport can plausibly retry a
   write.
7. Add endpoint tests for the successful path, invalid input, authorization or
   tenant boundary, and stable error mapping.

## Route pattern

Follow the existing decision-router shape. Adapt names and response types to
the target capability; do not copy tenant identifiers from the request.

```python
@router.get("/{decision_id}", response_model=DecisionResponse)
def get_decision(
    decision_id: str,
    service: Annotated[
        object, Depends(get_governance_decision_application_service)
    ],
    context=Depends(get_compatible_tenant_context),
) -> DecisionResponse:
    decision = service.get(decision_id, context)
    return DecisionApiMapper.to_decision_response(decision)
```

For a list endpoint, use a bounded FastAPI query parameter such as
`Query(default=50, ge=1, le=500)` and pass the resolved context to the
service.

## Contract checklist

- Declare request, success, and stable error response models.
- Update OpenAPI summary and description with the actual contract.
- Map internal exceptions at the HTTP boundary without exposing implementation
  details.
- Add a mapper rather than returning a domain or persistence object directly.
- Confirm state-changing routes are authorized, deterministic under a retry,
  and auditable through the service layer.

## Verify

Choose the closest existing API test module and run it. These commands are
known to exercise the current decision and policy API contracts:

```bash
uv run ruff check src/ai_governance/api
uv run pytest tests/api/test_decision_api.py
uv run pytest tests/api/test_policy_administration_api.py
```

Run the targeted test for the changed router and any dependent service test.
Run the full relevant suite before handoff when the API change crosses a
transport, service, persistence, or tenancy boundary.
