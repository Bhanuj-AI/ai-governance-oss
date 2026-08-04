---
name: governance-policy
description: Add or modify Kavach governance policies, policy rules, evidence, decision reasoning, explanations, audit records, policy lifecycle behaviour, or decision APIs. Use when a change affects deterministic evaluation, explainability, evidence lineage, decision persistence, or replayable governance outcomes.
---

# Governance Policy

Build a deterministic decision from versioned policy and inspectable evidence.

## Workflow

1. Read root `AGENTS.md`, `src/kavach/domain/AGENTS.md`, and
   `src/kavach/services/AGENTS.md`. Read API, repository, tenancy, and MCP
   instructions if the change reaches those boundaries.
2. Define the target type, evidence fields, condition operators, rule priority,
   effect, and human-readable reason before changing the evaluator.
3. Model policy rules as structured, versioned data. Do not embed an
   untestable policy decision in a route, database adapter, or provider call.
4. Ensure the evidence builder produces the exact fields used by the policy.
   Preserve the evaluation outcome and explanation needed to reconstruct why
   the decision was made.
5. Persist final committed outcomes with policy outcomes, explanation, audit
   context, and tenant scope. Maintain idempotency for repeated decision
   requests.
6. Test the approved, rejected or blocked, missing-evidence, lifecycle, and
   repeated-request paths that apply to the change.

## Rule pattern

Use the existing policy builder so an evaluator trace can name the rule,
condition, effect, reason, and priority that produced its result.

```python
rule = build_policy_rule(
    rule_id="rule-1",
    name="Groundedness gate",
    conditions=(
        {
            "field_path": "metrics.groundedness.score",
            "operator": PolicyConditionOperator.GREATER_THAN.value,
            "expected_value": 0.8,
        },
    ),
    effect=PolicyEffect.APPROVE.value,
    reason_template="Groundedness passed.",
    priority=10,
    severity="HIGH",
    metadata={"source": "unit-test"},
)
```

Do not make outcome meaning depend on an unordered dictionary, current time,
or a provider response that is not captured as evidence.

## Decision integrity checklist

- Version the policy and enforce its lifecycle; do not silently change an
  active definition.
- Make missing or invalid evidence explicit instead of inventing a result.
- Persist the explanation and audit record with the committed decision.
- Scope decision retrieval, evidence, explanation, and lineage by tenant
  context.
- Return a stable conflict for a reused request ID with different input.

## Verify

These commands cover the current policy lifecycle, evaluation, explanation,
audit, idempotency, and API contract paths:

```bash
uv run ruff check src/kavach/decisions src/kavach/services
uv run pytest tests/unit/test_policy_administration_service.py
uv run pytest tests/api/test_policy_administration_api.py tests/api/test_decision_api.py
```

Run the closest persistence or tenant-isolation test when the change alters
stored decision evidence or an externally visible decision query.
