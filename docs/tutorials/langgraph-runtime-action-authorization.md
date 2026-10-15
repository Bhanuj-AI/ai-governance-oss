# LangGraph Runtime Action Authorization

This guide protects a consequential LangGraph tool operation with the OSS
runtime-action authorization endpoint. AIGP makes and persists the decision;
LangGraph still owns execution and must enforce it.

Read [Runtime Action Authorization](runtime-action-authorization.md) first for
the framework-neutral public contract, policy convention, evidence model, and
time-of-check/time-of-use boundary.

## Protected Tool Wrapper

The runtime authenticates to AIGP normally. Tenant and actor are derived from
that authenticated server context, not from this request.

```python
from ai_governance.runtime_authorization import (
    AIGPRuntimeActionAuthorizationClient,
    LangGraphOperationAuthorizer,
    RuntimeActionAuthorizationRequest,
    RuntimeActionResource,
    canonical_tool_arguments_digest,
)

client = AIGPRuntimeActionAuthorizationClient(
    "https://aigp.example.com",
    bearer_token=runtime_service_token,
    # Only established scope headers are accepted. In a Keycloak deployment,
    # omit the development-only actor header and let the token identify it.
    scope_headers={
        "X-AI-Governance-Organization-Id": organization_id,
        "X-AI-Governance-Project-Id": project_id,
        "X-Correlation-Id": langgraph_run_id,
        "X-Request-Id": f"{langgraph_run_id}:claims.update",
    },
)
authorizer = LangGraphOperationAuthorizer(
    client,
    actor_id="claims-runtime-service",
)

def update_claim_tool(execution_id: str, claim_id: str, delegation) -> None:
    tool_arguments = {"claim_id": claim_id, "status": "APPROVED"}
    request = RuntimeActionAuthorizationRequest(
        execution_id=execution_id,
        action_id="claims.update",
        resource=RuntimeActionResource("sqlite.row", f"claims:{claim_id}"),
        delegation_id=delegation.delegation_id,
        delegation_version=delegation.version,
        delegation_digest=delegation.contract_digest,
        tool_arguments_digest=canonical_tool_arguments_digest(tool_arguments),
        context={},
        idempotency_key=f"{execution_id}:claims.update:{claim_id}",
    )
    decision = authorizer.require_allow(
        request,
        actual_tool_arguments_digest=canonical_tool_arguments_digest(tool_arguments),
    )
    # Only a valid, unexpired ALLOW reaches this point.
    update_claim_in_sqlite(claim_id)
    emit_tool_call_evidence(
        execution_id=execution_id,
        causation_id=decision.decision_id,
        tool="claims.update",
    )
```

`require_allow()` fails closed for a timeout, unavailable service, malformed
response, denial, mismatch, expiry, or tool-argument mutation. It validates
the returned execution, actor, action, resource, delegation, full request
fingerprint, idempotency key, and exact tool-argument digest before the tool
runs. The separate `TOOL_CALL`
event records whether the runtime says the tool actually executed; the
preceding `RUNTIME_ACTION_AUTHORIZATION` event is decision evidence only.
