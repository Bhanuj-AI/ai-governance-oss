# Agent Tool Evidence Interoperability & Causal Replay

## POV

AI Governance Control Plane is not inventing a proprietary model of agent tool
use. Modern agent runtimes increasingly expose a common observational envelope:
an identifiable tool call, its requested input, a correlated result, execution
lineage, and some model or agent metadata.

That envelope is sufficient to observe an agent trajectory. It is not enough to
establish whether returned evidence affected an outcome.

```text
Industry-standard observability
  tool action (T) + returned evidence (E) + lineage

AI Governance Control Plane
  governed counterfactual (E′) + isolated replay(T, E′) + outcome comparison
```

This distinction is the foundation of Causal Audit. A tool call is evidence
that an agent requested information, not proof that its result influenced the
evaluated outcome.

This document is an architectural point of view and integration contract. It
does not claim every provider or connector currently supplies every field.
Integrations must declare their actual capability and fail closed when safe
counterfactual replay is not available.

## Generally Portable

The following signals are broadly available across provider tool APIs,
Model Context Protocol (MCP) implementations, and OpenTelemetry-based tracing.
Their exact field names differ; an integration normalizes them to the Agents
Runtime evidence contract.

| Signal | Why it matters to the control plane | Portability |
| --- | --- | --- |
| Tool-call identifier | Identifies the exact call to inspect or intervene on. | Common |
| Tool name | Resolves a governed Intervention Policy. | Common |
| Tool arguments and input schema | Identifies the requested evidence and validates the invocation. | Common, usually JSON |
| Tool result and result status | Establishes observed evidence `E`; failed calls are not usable evidence. | Common concept |
| Result/output schema | Validates structural properties of `E′`. | Strongest in schema-aware protocols such as MCP |
| Call/result correlation | Reconstructs the execution trajectory. | Common |
| Agent/model identity and version | Supports reproducibility and attribution. | Common but provider-specific |
| Turn, response, trace, and span identifiers | Preserves ordering and cross-system lineage. | Increasingly common |
| Stop reason and token usage | Explains termination and enables future bounded-use analysis. | Common but not universal |

OpenAI Responses function tools expose a `call_id`, tool `name`, and structured
arguments, with a matching output item carrying the same call ID. Anthropic
tool-use blocks similarly contain an ID, name, and structured input. These are
different wire formats for the same core relation: a named request and a
correlated result. [OpenAI Responses API](https://developers.openai.com/api/reference/cli/resources/beta/subresources/responses), [Anthropic tool use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools)

MCP is the preferred path when structured evidence is available. An MCP tool
can declare `inputSchema` and `outputSchema`; it can return
`structuredContent`, and the structured result is expected to conform to the
declared output schema. MCP defaults unspecified schemas to JSON Schema
2020-12. [MCP tools specification](https://modelcontextprotocol.io/specification/2025-11-25/server/tools), [MCP schema reference](https://modelcontextprotocol.io/specification/2025-11-25/schema)

OpenTelemetry's GenAI conventions also contain concepts for agent identity,
tool-call IDs, tool names, arguments, results, token usage, and evaluation
data. The registry currently marks several of these entries as moved or
deprecated in favour of the dedicated GenAI semantic-conventions repository;
connector authors should follow the active convention version rather than
hard-code an obsolete attribute set. Tool arguments and results are explicitly
identified as potentially sensitive. [OpenTelemetry GenAI attributes](https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/)

## Missing Abstractions

The industry envelope gives the control plane a way to observe `T` and `E`:

```text
T = a tool action
E = the evidence returned by that action
```

It does not supply either of the following:

```text
E′ = a legitimate, schema-valid, semantically permissible counterfactual
Replay(T, E′) = a safe re-execution of the trajectory under that intervention
```

Those are deliberately separate control-plane abstractions:

| Abstraction | Question it answers | Owner |
| --- | --- | --- |
| **Replay Capability** | Can this runtime reconstruct the execution in isolation and without production side effects? | Runtime adapter |
| **Intervention Policy** | What alternative result is valid and permitted for this tool and evidence schema? | Authorized operator |
| **Evidence Intervention Provider** | How is that governed alternative generated deterministically? | Provider SPI / adapter integration |
| **Causal Audit** | How much did the evaluated outcome change under the controlled intervention? | Causal Audit service |

Neither a model provider, a tracing system, nor a tool protocol can infer the
business meaning of a valid alternative result. For example, replacing a
credit-history result with `"banana"` only tests malformed-input handling. A
schema-valid low-risk record tests whether the outcome depended on the
evidence.

## Minimum Integration Contract

A connector that wants to support auditable tool evidence should provide a
bounded, tenant-scoped execution record equivalent to the following. It may
carry durable references and digests rather than raw contents.

```text
AgentExecution
├── execution_id
├── agent_id and agent_version
├── provider and model identity
├── response, conversation, trace, or correlation identifiers
├── ordered ToolCall records
│   ├── call_id
│   ├── tool_name
│   ├── arguments reference or approved digest
│   ├── input schema identity and version, when known
│   ├── output schema identity and version, when known
│   ├── result reference and result digest
│   ├── status / error state
│   └── sequence and timestamps
├── durable final-outcome reference or bounded outcome score
└── optional ReplayCapability
```

The persisted tool-evidence descriptor is intentionally smaller than the
ephemeral tool payload:

```text
ToolEvidenceDescriptor
├── tool_call_id
├── tool_name
├── evidence_ref
├── evidence_digest
├── content_type
├── schema_id and schema_version
├── replay_adapter_id
└── safe metadata
```

An adapter resolves the original evidence under authorized tenant and project
context only when it must generate or execute an intervention. Agents Runtime,
Replay metadata, Causal Audit records, logs, and traces retain only permitted
references, digests, and provenance.

## Controlled Causal Path

For an eligible execution, the evidence flow is explicit and inspectable:

```text
Observed execution
  → select auditable tool call
  → resolve active Intervention Policy
  → resolve authorized original evidence
  → generate and validate counterfactual evidence E′
  → create ControlledEvidenceIntervention
  → create isolated Replay
  → evaluate counterfactual outcome
  → compare with original outcome
  → persist influence, reason, and replay lineage
```

`Evidence influence = original outcome score − aggregate counterfactual score`

The audit persists the original and counterfactual scores, intervention
strategy, policy and provider versions, seed, evidence digests, and durable
Replay lineage. That makes the classification explainable without exposing the
raw result that was temporarily resolved during replay.

The product classifications describe this measured relationship rather than an
agent's purported internal reasoning:

| Classification | Meaning |
| --- | --- |
| `NO_TOOL_EVIDENCE` | No auditable tool evidence existed. |
| `EVIDENCE_IGNORED` | Tool evidence existed but did not materially influence the evaluated outcome. |
| `OVER_EXTENDED` | Evidence materially influenced the outcome, but unnecessary calls continued after saturation or the tool budget was exhausted. |
| `EVIDENCE_ALIGNED` | Evidence materially influenced the outcome and tool use remained appropriately bounded. |

See [Causal Audit](./CAUSAL_AUDIT.md) for eligibility, scoring, immutable
results, and the limits of this method.

## Why MCP is the cleanest first-class integration

MCP is particularly useful because it offers a precise, standards-based bridge
between a tool result and the contract needed to transform it safely:

```text
Tool name + input schema
  → tool-use ID + structured input
  → correlated tool result
  → structuredContent + output schema
  → schema-valid counterfactual E′
```

For MCP tools with trustworthy output schemas and structured results, an
Intervention Policy can validate a replacement, null representation, or
bounded perturbation against the declared contract. This is safer and more
useful than attempting to parse an opaque free-text REST response.

MCP support is not an automatic safety guarantee. The runtime adapter must
still declare whether it can isolate the tool interaction and replay the
trajectory without side effects. The control plane must also treat tool
annotations, remote schemas, and remote results as untrusted until the
configured authorization and validation checks pass.

## Privacy and Security Position

The control plane does not need raw prompts, raw model output, chain-of-thought,
credentials, or unrestricted tool payload retention to perform this analysis.

- Do not make Causal Audit depend on provider log probabilities, confidence
  values, or hidden reasoning traces.
- Do not copy tool arguments or results into OpenTelemetry by default; the
  relevant GenAI attributes can contain sensitive data.
- Re-resolve every original, replacement, and counterfactual reference
  server-side in the audit tenant/project context.
- Reject cross-tenant evidence and unsupported side-effecting tools.
- Fail closed when no active unambiguous policy, compatible provider, schema,
  or isolated replay capability exists.

This preserves the product boundary: the control plane governs evidence and
reproducibility; it does not become a broad collector of sensitive agent
content.

## What this does not claim

This approach measures sensitivity of an evaluated outcome under a controlled
evidence intervention. It does not prove universal causation, reconstruct
private model reasoning, or establish that an agent followed a particular
reasoning path.

It also does not require a new generic agent protocol, an LLM-generated
counterfactual service, automatic policy authoring, fleet-wide causal
analytics, or automated governance actions. The OSS capability remains
purposefully narrow:

> Configure a trustworthy intervention, replay one execution safely, and
> measure the influence of its tool evidence.

## Connector Author Checklist

- Preserve tool-call IDs, names, ordering, terminal/error state, and result
  correlation.
- Prefer durable evidence references plus content digests to raw payload
  persistence.
- Supply output schema identity for structured results whenever the runtime
  exposes it; prioritize MCP `structuredContent` integrations.
- Declare Replay Capability and supported intervention strategies explicitly.
- Resolve evidence only under the server-side tenant/project context.
- Keep counterfactual generation in an Intervention Provider; do not put
  tool-specific business rules in Replay or Causal Audit.
- Ensure replays cannot execute production side effects.
- Treat unavailable schema, provider, policy, or replay isolation as an
  ineligible audit, not a best-effort fallback.

## References

- [OpenAI Responses API](https://developers.openai.com/api/reference/cli/resources/beta/subresources/responses)
- [Anthropic tool use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools)
- [Model Context Protocol — tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
- [Model Context Protocol — schema reference](https://modelcontextprotocol.io/specification/2025-11-25/schema)
- [OpenTelemetry — GenAI attributes](https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/)
