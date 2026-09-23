# Causal Audit

Causal Audit is an execution-level diagnostic in Agents Runtime. It asks whether
the evidence returned by a tool materially affected the evaluated outcome; it
does not treat a tool call itself as proof that the agent used its evidence.

```text
Execution evidence → Causal Audit → immutable CausalAuditResult → optional Finding
```

The source execution remains owned by Agents Runtime. Causal Audit never edits
the source evidence and the job worker owns asynchronous execution.

## Evidence Influence

For each eligible tool call, Causal Audit creates a normal, durable Replay
request. The Replay worker selects the runtime-declared adapter, applies the
versioned evidence intervention in that isolated adapter, and persists a new
counterfactual execution. Causal Audit reads the resulting outcome score only
after that Replay execution succeeds.

`Evidence influence = baseline outcome score − aggregate counterfactual score`

The observed baseline is scored from a bounded numeric outcome artifact. The
counterfactual score is produced by the Replay execution; each influence record
therefore exposes its Replay IDs and produced-execution IDs. The reference
`deterministic-agent-runtime/v1` adapter exists for local validation only; a
runtime integration supplies a real adapter through the existing Replay adapter
registry. The core contract does not require logits or model probabilities.

Controlled Replays are finalized by the Causal Audit worker path rather than
the generic Replay-evaluation/comparison workflow. Their adapter produces the
bounded outcome artifact used by the Causal Audit scorer; requiring an
unrelated compatible source evaluation would both duplicate the evaluation and
reject valid isolated counterfactuals.

An influence record is valid only with complete durable lineage for every
counterfactual sample:

```text
policy version → intervention digest → counterfactual reference + digest
  → successful Replay + produced execution → evaluator score → influence
```

The domain contract rejects incomplete or mismatched lineage, and persistence
round-trips that typed record. A partial counterfactual failure fails the audit;
it never produces a best-effort influence value.

Terminal reconciliation is mandatory. When a controlled Replay succeeds,
fails, or is cancelled, the Replay worker submits an idempotent Causal Audit
finalization job. A failed or cancelled Replay moves its still-running audit to
`FAILED`, retaining the planned counterfactual Replay lineage in diagnostics
and recording `CONTROLLED_REPLAY_FAILED` or `CONTROLLED_REPLAY_CANCELLED` with
the persisted Replay failure reason. This prevents a permanent Replay failure
from leaving an audit indefinitely `RUNNING`.

## Safety and Eligibility

An audit is eligible only for a succeeded execution with a durable outcome
score, bounded tool calls, durable evidence references, and an explicit
runtime replay capability. That capability names an adapter and version,
provides an opaque frozen replay reference, and declares the supported
interventions. Missing evidence, a missing capability, an unsupported
intervention, or an unavailable adapter fails closed. Counterfactual runs must
not perform production side effects.

```text
Observed execution → explicit replay capability → Causal Audit
    → durable controlled Replay → Replay worker + adapter
    → counterfactual execution → outcome comparison → classification
```

### Local Docker execution

Causal Audit work is asynchronous: the API persists the audit and submits a
job, while `ai-governance-replay-worker` retrieves that audit in a separate
process. Consequently, the API and worker must use the same durable Agent
Runtime repository. The supplied Docker Compose stack configures both with
SQLite at `/var/lib/ai-governance/governance.db`; do not use the in-memory
Agent Runtime backend when the Replay worker is a separate process.

For message-level diagrams of the policy lifecycle, Causal Audit orchestration,
controlled counterfactual Replay, result retrieval, and fail-closed paths, see
[Causal Audit and Controlled Replay sequence diagrams](CAUSAL_AUDIT_SEQUENCES.md).

The initial deterministic intervention strategies are `NULLIFY`, `REPLACE`,
and `PERTURB`. Their strategy version, seed, sample count, thresholds, source
references, and result digest are persisted with every completed audit.

## Classification

`causal-audit/v1` uses deterministic classification only:

- `NO_TOOL_EVIDENCE`: no auditable tool evidence existed in the execution.
- `EVIDENCE_IGNORED`: tool evidence existed but did not materially influence the
  evaluated outcome.
- `OVER_EXTENDED`: evidence materially influenced the outcome, but calls
  continued after saturation or exhausted the tool-call budget.
- `EVIDENCE_ALIGNED`: evidence materially influenced the outcome and tool usage
  remained appropriately bounded.

These are product classifications. The causal-audit research paper informed the
methodology and validation, but its research terminology is not exposed as the
product taxonomy.

The default influence threshold is `0.01` and saturation threshold is `0.95`.
They are configurable Agents Runtime settings and methodology-specific defaults,
not universal scientific constants. Changing methodology semantics requires a
new methodology version and a new audit; completed audits are immutable.

Causal Audit measures outcome sensitivity under controlled evidence
interventions. It does not prove philosophical or universal causation.

## Policy Operations in Studio

The **Intervention Policies** tab in Agents Runtime is the operational surface
for the policy lifecycle. Operators can create a draft, run a non-executing
counterfactual preview, validate it, activate it, retire it, and create an
immutable next draft version from an active policy. Studio delegates all
lifecycle decisions and tenant enforcement to the Causal Audit REST API; it
does not interpret policy validity in the browser.

### Policy Validation

**Validate** is a safety and configuration check. It does not create a Replay,
does not invoke an agent or tool, does not alter an observed execution, and
does not calculate Evidence Influence. It returns the same immutable draft
policy when its provider configuration is usable.

For the bundled `structured-json/v1` provider, validation checks:

- the policy names an installed provider and compatible provider version;
- `strategy_configuration.json_schema` is a valid JSON Schema;
- the selected strategy has its mandatory configuration;
- `NULLIFY` declares a schema-valid `neutral_value`;
- `REPLACE` declares one or more non-empty `replacement_references`, and the
  authorized runtime resolver can resolve each reference to schema-valid
  evidence in the current tenant;
- `PERTURB` declares one or more supported operations (`SET`,
  `NUMERIC_DELTA`, `NUMERIC_SCALE`, or `REMOVE_OPTIONAL`) with a JSON Pointer
  target; and
- the provider can enforce the configured schema and its semantic constraints.

For `opaque-reference/v1`, we never resolve protected evidence. A policy
may either declare a counterfactual-reference namespace for a runtime-attested
transformation, or, for a fixed `REPLACE` fixture, declare both an opaque
`counterfactual_reference` and its content `counterfactual_digest`. The latter
still stores no evidence value: it lets platform prove the approved immutable
reference while requiring the external runtime to resolve it and verify the
digest before replay.

Validation is deliberately not a stored lifecycle state: a valid policy
remains `DRAFT` until activation. **Activate** repeats validation on the
server, then makes that immutable version the sole active policy for its exact
`tool_name + schema_id + schema_version` target. It fails if another active
version would make policy selection ambiguous.

### Validation, Preview, Activation and Audit Relevance

| Operation | Resolves evidence? | Runs Replay? | Changes policy lifecycle? | Produces Evidence Influence? |
| --- | --- | --- | --- | --- |
| Create draft | No | No | Creates `DRAFT` | No |
| Validate | `REPLACE` references only | No | No | No |
| Preview | Yes, for one selected tool call | No | No | No |
| Activate | `REPLACE` references only | No | Makes the version `ACTIVE` | No |
| Causal Audit | Yes | Yes, controlled and isolated | No | Yes, after successful evaluator scoring and complete lineage |

For example, a `PERTURB` policy that applies a numeric delta of `-0.50` to
`/confidence` with bounds `0` and `1` is validated as a permitted bounded
operation. The actual counterfactual value, replay outcome, evaluator score,
and influence are established only by Preview or Causal Audit. A Preview is
safe to use to confirm that evidence can be resolved and the resulting
counterfactual is schema- and semantically-valid; it does not execute the
agent.

## Worked Example: Fraud Evidence Perturbation

This local example is the smallest complete governed path. It demonstrates an
**Intervention Policy**—the product term for a versioned policy that governs
how observed tool evidence may be changed for an isolated counterfactual. It
is not an inference policy: the policy authorizes the intervention; Causal
Audit measures the resulting outcome sensitivity.

### 1. Select observed evidence

In **Agents Runtime → Intervention Policies**, start from the completed local
execution `demo-exec-ext-fraud-replay-source-001` and select its auditable tool
result:

| Field | Value |
| --- | --- |
| Tool | `query_transaction_db` |
| Evidence schema | `transaction-record` / version `1` |
| Original evidence reference | `artifact://demo/fraud/replay-source-transactions` |
| Replay adapter | `deterministic-agent-runtime/v1` |

Studio copies the tool and schema identity from the observed event. An operator
should not type or guess an Evidence Schema ID unless using the explicit manual
fallback.

### 2. Create, validate, and activate one policy version

Choose the `structured-json` provider at version `v1`, then select **PERTURB**.
Use exactly one intervention strategy for the version and configure the
following bounded operation:

| Field | Value |
| --- | --- |
| Field path | `/confidence` |
| Operation | `NUMERIC_DELTA` |
| Delta | `-0.50` |
| Minimum | `0` |
| Maximum | `1` |

The equivalent advanced configuration is:

```json
{
  "json_schema": {
    "type": "object",
    "properties": {
      "confidence": { "type": "number" },
      "status": { "type": "string" }
    },
    "additionalProperties": false
  },
  "operations": [
    {
      "path": "/confidence",
      "operation": "NUMERIC_DELTA",
      "delta": -0.5,
      "minimum": 0,
      "maximum": 1
    }
  ]
}
```

**Validate** proves that the policy/provider configuration and the bounded
operation are permitted. It does not run the agent, create a Replay, or change
the historical evidence. Once validation succeeds, activate the draft. Record
the returned immutable `policy_id` and `version`; both are required to run an
audit.

### 3. Run the Causal Audit

With an active policy, submit the tenant-scoped request below. Replace
`<active-policy-id>` with the ID created in the preceding step.

```bash
curl --request POST http://localhost:8000/api/v1/agents-runtime/causal-audits \
  --header "Authorization: Bearer $TOKEN" \
  --header 'Content-Type: application/json' \
  --header 'X-AI-Governance-Organization-Id: org_default' \
  --header 'X-AI-Governance-Project-Id: project_default' \
  --data '{
    "execution_id": "demo-exec-ext-fraud-replay-source-001",
    "evaluator_ref": "recorded-outcome/v1",
    "intervention": {
      "strategy": "PERTURB",
      "counterfactual_samples": 3,
      "seed": 2,
      "intervention_policy_id": "<active-policy-id>",
      "intervention_policy_version": 1
    }
  }'
```

The request is idempotent for the complete execution, evaluator, policy,
strategy, sample count, and seed. Change the seed only when deliberately
requesting a new audit; do not retry a failed historical audit by changing its
policy or its evidence.

### 4. Verify the durable result

The worker sequence is:

```text
Causal Audit (queue controlled Replay)
  → Replay execution
  → Causal Audit finalization
```

Controlled Replays do not enter the generic Replay Evaluation and Comparison
workflow. The generic Replay screen can therefore show `EXECUTION COMPLETED`
and an **Evaluate Replay** action; do not select it for a controlled Causal
Replay. Causal Audit already consumes the adapter's bounded outcome artifact
and records its own evaluator lineage.

Retrieve the audit using the `audit_id` returned by the POST:

```bash
curl "http://localhost:8000/api/v1/agents-runtime/causal-audits/<audit-id>" \
  --header "Authorization: Bearer $TOKEN" \
  --header 'X-AI-Governance-Organization-Id: org_default' \
  --header 'X-AI-Governance-Project-Id: project_default'
```

For the supplied local fixture, the completed result is expected to contain:

| Result | Expected value |
| --- | --- |
| Status | `SUCCEEDED` |
| Classification | `EVIDENCE_ALIGNED` |
| Baseline score | `0.870` |
| Counterfactual score | `0.270` |
| Evidence influence | `+0.600` |
| Material tool call | `query_transaction_db` |

The result exposes the complete chain needed to audit that conclusion:

```text
policy ID + version
  → original evidence digest
  → counterfactual evidence reference + digest
  → intervention digest
  → controlled Replay ID + replay execution ID
  → evaluator score
  → influence and classification reason
```

`counterfactual_samples` is the requested sample budget. The current
deterministic PERTURB fixture generates the same evidence value for each seed,
so the planner deduplicates it to one unique controlled Replay. The response
therefore records `counterfactual_count: 1` and one lineage item. Production
adapters should make this distinction visible when deduplication occurs; a
request for three statistically independent samples must retain three Replay
lineages.
