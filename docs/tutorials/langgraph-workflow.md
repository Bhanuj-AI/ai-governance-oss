# Govern a Workflow

This lab records graph nodes as provider-neutral `WORKFLOW_STEP`
evidence. A node is an orchestration unit, so it is not recorded as a
`TOOL_CALL`. Emit a `TOOL_CALL` only when a node actually invokes an external
tool.

## Deterministic example

The example workflow has four deterministic nodes: `load_claim`,
`check_policy`, `evaluate_evidence`, and `make_decision`. Each node emits a
stable `step_id` for its `STARTED` and terminal event. The adapter maps the
LangGraph-specific node concept only through `source_kind="langgraph.node"`.

```python
def emit_node_lifecycle(governance_client, execution_id, node_name, lifecycle):
    # Stable for both lifecycle records of one logical node.
    step_id = f"{execution_id}:node:{node_name}"
    try:
        governance_client.append_event(
            execution_id,
            {
                "event_type": "WORKFLOW_STEP",
                "step_id": step_id,
                "step_name": node_name,
                "lifecycle": lifecycle,
                "source_kind": "langgraph.node",
                "idempotency_key": f"{step_id}:{lifecycle.lower()}",
            },
        )
    except Exception:
        # Evidence collection is fail-open: LangGraph retains execution ownership.
        pass
```

Wrap each node with `emit_node_lifecycle(..., "STARTED")` before it executes
and `emit_node_lifecycle(..., "COMPLETED")` after a successful return. Emit
`FAILED` instead of `COMPLETED` if the node raises, then re-raise the original
exception so LangGraph retains its normal failure behavior.

The complete deterministic run produces this ordered evidence sequence:

```text
EXECUTION_STARTED
WORKFLOW_STEP  load_claim          STARTED
WORKFLOW_STEP  load_claim          COMPLETED
WORKFLOW_STEP  check_policy        STARTED
WORKFLOW_STEP  check_policy        COMPLETED
WORKFLOW_STEP  evaluate_evidence   STARTED
WORKFLOW_STEP  evaluate_evidence   COMPLETED
WORKFLOW_STEP  make_decision       STARTED
WORKFLOW_STEP  make_decision       COMPLETED
EXECUTION_COMPLETED
```

It contains zero `TOOL_CALL` events because this example performs no external
tool invocation. Its business result remains `Decision: APPROVED`; unavailable
AI Governance Control Plane instrumentation must not change that result.
