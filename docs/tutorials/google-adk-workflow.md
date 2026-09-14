# Govern a Google ADK Workflow

This optional integration records bounded runtime evidence from a Google ADK
workflow in AI Governance Control Plane. It does not run, route, mutate, or
inspect ADK execution state. The adapter reads only the public context given to
function nodes and sends evidence one way to the control plane.

It is written against `google-adk==2.9.0` on Python 3.12. Keep that runtime
dependency with the application that runs ADK; the governance control-plane
package does not require Google ADK.

## Event mapping

| Google ADK fact | Canonical evidence |
| --- | --- |
| Root invocation | `EXECUTION_STARTED`; the public `invocation_id` is `external_execution_id` and correlation ID. |
| Workflow node begins | `WORKFLOW_STEP` with `lifecycle: STARTED`. |
| Workflow node returns | Same `WORKFLOW_STEP` with `lifecycle: COMPLETED`. |
| Workflow node raises | Same `WORKFLOW_STEP` with `lifecycle: FAILED`, then the original exception is re-raised. |
| Actual model/tool invocation inside a node | A separate `MODEL_CALL` or `TOOL_CALL` integration, when that boundary is available. It is never inferred from a node. |
| Root invocation finishes | Mark the execution `SUCCEEDED`, `FAILED`, or `CANCELLED`. |

`WORKFLOW_STEP` means a unit of orchestration. It must not be used to claim a
model call or tool invocation occurred. Conversely, a nested tool call does
not replace the surrounding node evidence.

## Install and configure the runtime

The example is self-contained and uses only Python standard-library HTTP. In
the ADK application's environment, install the pinned framework version:

```bash
uv pip install "google-adk==2.9.0"
```

Configure the adapter with the control-plane base URL and the deployment's
ordinary authentication and tenant headers. Do not place credentials, prompts,
responses, tool payloads, or chain-of-thought in metadata or event attributes.

```python
from examples.google_adk.governed_workflow import AIGovernanceRuntimeClient

client = AIGovernanceRuntimeClient(
    base_url="https://governance.example",
    headers={
        "Authorization": "Bearer <runtime-service-token>",
        # Use the tenant headers and authentication scheme configured by your deployment.
    },
)
```

## Instrument public function nodes

Start one evidence session from the root public `invocation_id`, then construct
or invoke the ADK workflow with decorated function nodes. The exact workflow
construction is application-specific; the wrapper does not depend on ADK
private scheduler or graph internals.

```python
from examples.google_adk.governed_workflow import governed_adk_node

def run_claims_workflow(root_context, claim):
    evidence = client.start_execution(
        agent_id="claims-agent",
        agent_name="Claims agent",
        agent_version="1.0.0",
        root_invocation_id=root_context.invocation_id,
        metadata={"workflow": "insurance-claims"},
    )

    @governed_adk_node(evidence)
    def check_policy(ctx, node_input):
        # Existing deterministic business logic. Its return value is unchanged.
        return {"approved": node_input["amount"] < 10_000}

    try:
        result = check_policy(root_context, claim)
    except Exception:
        # Preserve ADK's original exception and error path.
        evidence.complete("FAILED")
        raise
    evidence.complete("SUCCEEDED")
    return result
```

The decorator derives a stable step ID from public `invocation_id`, `run_id`,
and `node_path`; it uses the public `parent_ctx` only when it has the same
stable facts. It keeps bounded `adk_node_path`, `adk_run_id`, and non-negative
`adk_attempt_count` attributes. If those public identifiers are unavailable,
it records no node evidence rather than collapsing distinct nodes into an
ambiguous ID.

For a nested function node, decorate the parent function node too. The adapter
uses `parent_ctx` only when its public ADK node is itself a `FunctionNode`;
the surrounding ADK `Workflow` root is an orchestration container, not a
`WORKFLOW_STEP`, and is deliberately not synthesized as a parent. This keeps
every emitted `parent_step_id` resolvable to evidence in the same execution.

## Delivery and failure semantics

The adapter is deliberately fail-open. A delivery failure is swallowed, while
the ADK node's return value and original exception are preserved. Delivery is
also unidirectional: it does not alter ADK state, routing, outputs, retry
policy, or scheduling. The control-plane endpoint provides the durability and
duplicate handling; each lifecycle emission uses a deterministic idempotency
key derived from the stable step ID and lifecycle.

The adapter does not patch ADK private state and does not depend on private
fields such as `isolation_scope`. There is no generic ADK plugin callback that
reliably observes both a node start and terminal outcome, so the explicit
function-node wrapper is the supported v1 integration boundary.

## Expected deterministic evidence

For an eight-node insurance workflow, expect exactly 18 events:

- one execution start;
- eight `WORKFLOW_STEP` `STARTED` events;
- eight corresponding `COMPLETED` events;
- one execution completion.

That run should report zero `TOOL_CALL` events unless the workflow actually
executes a tool and has a separate tool-boundary integration. A node failure
produces `STARTED`, then `FAILED`, followed by a failed root execution.

## Guardrails

Stop and review the integration rather than widening the Core vocabulary if
any of these are false in your ADK application:

- a workflow unit cannot be mapped to `WORKFLOW_STEP` without inventing model
  or tool semantics;
- nested execution cannot be tied to a real public parent context;
- a tool boundary is ambiguous and would make a node look like a tool call; or
- the public context lacks the stable invocation, run, and node identifiers
  needed for duplicate-safe evidence.

If you need ADK details beyond this integration, use the focused ADK reference
at <https://adk.dev/llms.txt>; do not depend on broad documentation crawling
or private source-tree behavior.
