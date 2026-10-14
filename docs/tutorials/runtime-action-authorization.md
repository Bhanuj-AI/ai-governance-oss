# Runtime Action Authorization

AIGP OSS makes authoritative, deterministic decisions
about individual consequential operations that an external agent runtime wants
to perform. The runtime remains responsible for enforcing the decision before
it invokes the operation.

The authorization endpoint is a decision service. It neither receives a tool
payload nor executes a tool, and it has no dependency on a particular agent
framework.

## Public Contract

Call `POST /api/v1/runtime-action-authorizations/authorize` for one proposed
operation. Requests use the versioned
`runtime-action-authorization/v1` schema and contain:

- an `execution_id` and optional correlation ID;
- a registered `action_id` and bounded resource type/reference;
- at most 32 bounded scalar context facts;
- an idempotency key; and
- optionally, a selected policy ID and expected active policy version.

The authenticated server context supplies tenant/project scope and actor or
workload identity. The endpoint rejects caller-supplied tenant and actor
claims. Context must not contain prompts, credentials, reasoning, tool
payloads, or sensitive tool outputs.

For deployments that select scope through request headers, the OSS HTTP client
accepts only the established organisation, project, correlation, request, and
development-mode actor headers through `scope_headers`; credentials remain in
its separate `bearer_token` argument. These headers establish transport scope;
they are never copied into the authorization body as authoritative claims.

Each response returns an `ALLOW` or `DENY`, machine-readable reason code,
policy ID/version when applicable, decision and expiry times, execution and
correlation references, and an immutable request fingerprint. The decision is
bound to the exact execution, actor, action, resource, idempotency key, and
bounded context. It cannot be reused for a different operation.

## Policy Convention and Evaluation

Use an existing active AIGP OSS policy definition. Opt it into runtime action
authorization with definition metadata that registers the operation types it
may govern:

```json
{
  "runtime_action_authorization": {
    "purpose": "runtime_action_authorization",
    "registered_actions": ["claims.update"],
    "registered_resource_types": ["sqlite.row"]
  }
}
```

The policy version must target `AgentExecution`. Its normal structured rules
receive only deterministic evidence: `action.id`, `resource.type`,
`resource.reference`, `actor.id`, and each bounded `context.<fact>`.
`APPROVE` allows an operation; `REJECT` and `BLOCK` deny it. Matches sort
deterministically by rule priority and policy ID, and a matching deny overrides
any allow.

No registered policy, unsupported action or resource, no matching rule, a
missing/inactive selected policy version, or an unsupported policy effect all
produce a `DENY`. Repeating an identical request returns the persisted
decision; reusing its idempotency key with different input produces a
conflict.

## Enforcement and Evidence

An integration must request authorization immediately before its protected
operation and execute only a returned, unexpired `ALLOW` whose bindings match
the operation it is about to run. A timeout, unavailable service, malformed
response, denial, mismatch, or expired decision must block the operation.

Each decision is appended as `RUNTIME_ACTION_AUTHORIZATION` evidence on the
existing agent execution. The evidence records the decision, actor, action,
resource, policy, reason code, correlation, idempotency identity, and digests
of request/context facts rather than raw context values. A later `TOOL_CALL`
event may cite the decision ID as its causation ID, but it alone records that
the runtime reports a tool invocation actually occurred.

This is necessarily a time-of-check/time-of-use boundary: AIGP cannot prove an
external runtime used its integration, nor can it guarantee the protected
resource remains unchanged after a decision. A bypassed enforcement boundary
is outside the control plane's authority.

## Framework Integrations

Framework adapters should remain thin and retain ownership of their own
execution lifecycle. See [LangGraph Runtime Action Authorization](langgraph-runtime-action-authorization.md)
for a fail-closed LangGraph tool-wrapper example.
