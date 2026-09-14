# Agents Runtime Guide

**Agents Runtime** is the place to understand what externally-run AI agents
actually did. It records bounded execution evidence, groups it by agent, and
turns repeatable conditions into deterministic findings.

This guide is written for someone opening the page for the first time. You do
not need to know the internals of an agent framework to use it.

## Start Here

The shortest useful workflow is:

1. Open **Agents Runtime** in Studio.
2. In a new local installation, select **Load demo data** once.
3. Open the **Executions** tab and select an agent from the observed-agent
   list.
4. Read the selected-agent metrics, then inspect the execution records below.
5. Open **Findings** to see deterministic operational conditions.
6. Select **How this works** beside Detect and Reconcile whenever you need a
   reminder of the finding lifecycle.

The page is tenant-scoped. The organization and project selectors in Studio
determine which evidence, agents, and findings you can see.

## What this feature is—and is not

Agents Runtime is an **evidence and operations** surface. An external runtime
such as LangChain, LangGraph, CrewAI, or an in-house service runs the agent.
That runtime sends AI Governance Control Plane a small, structured record of
what happened.

AI Governance Control Plane then stores and presents:

- each agent execution;
- an ordered timeline of events within that execution;
- current execution status and duration;
- aggregated agent health information; and
- deterministic findings, such as an elevated failure rate or repeated error.

It does **not** run the agent, store its chain of thought, or generate
LLM-written alerts. A finding is produced by a configured detector and
measurable evidence, not by an LLM guess.

```text
External agent runtime
        │ sends bounded execution events
        ▼
AI Governance Control Plane
        │ stores tenant-scoped evidence
        ├── Executions: what happened?
        └── Findings: is a measured condition worth attention?
```

## Glossary

| Term | Meaning |
| --- | --- |
| Agent | A named, versioned automated worker, such as `claims-agent-v2`. |
| Execution | One run of one agent. An agent can have many executions. |
| Event | One ordered fact inside an execution, such as a model call, tool call, policy decision, or error. |
| Evidence | The safe, structured operational data used to explain an execution or finding. |
| Finding | A deterministic observation that a configured condition was met. It is not a ticket or an LLM opinion. |
| Detector | The deterministic rule that decides whether a finding exists. |
| Baseline | The historical behaviour used for comparison. |
| Observation window | The recent period being checked for a change or problem. |
| Reconcile Operational | Recheck open operational findings to see whether they have genuinely recovered. |


## Distinct Execution Layers: Model-driven Tool Use & Framework-controlled Workflow Execution
| Ecosystem                     | LLM / agent action primitive                       | Structured workflow primitive                                                                                            | What BHANUJ should ingest                                               |
| ----------------------------- | -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------- |
| **OpenAI API / Agents SDK**   | Function/tool calls, agent handoffs, agent turns   | No first-class graph/node abstraction; orchestration is largely SDK/Python controlled                                    | `TOOL_CALL`; optionally agent/handoff later ([OpenAI GitHub][1])        |
| **Anthropic Claude**          | `tool_use` → `tool_result`                         | No first-class deterministic workflow graph in the model API                                                             | `TOOL_CALL` ([Claude Platform][2])                                      |
| **Google Gemini API**         | `function_call` / tools                            | No graph primitive at raw model API                                                                                      | `TOOL_CALL` ([Google AI for Developers][3])                             |
| **Google ADK 2.0**            | Agents and tools                                   | **Workflow graph: nodes + edges**; deterministic code/tool/agent nodes; older Sequential/Parallel/Loop agents also exist | `WORKFLOW_STEP` + nested `TOOL_CALL` ([Google Developers Blog][4])      |
| **LangGraph**                 | Tool calls can happen inside nodes                 | **Nodes + edges + supersteps**; a node may contain an LLM *or plain code*                                                | `WORKFLOW_STEP` + nested `TOOL_CALL` ([Docs by LangChain][5])           |
| **Microsoft Agent Framework** | Agents/tools                                       | **Executors + edges**, plus functional `@step`; emits executor/workflow events                                           | `WORKFLOW_STEP` + `TOOL_CALL` ([Microsoft Learn][6])                    |
| **AWS Bedrock model APIs**    | Tool use/function calling                          | No deterministic graph at model API level                                                                                | `TOOL_CALL` ([AWS Documentation][7])                                    |
| **AWS Strands Agents**        | Agents/tools                                       | **Graph nodes + edges**, including custom deterministic business-logic nodes                                             | `WORKFLOW_STEP` + `TOOL_CALL` ([Strands Agents SDK][8])                 |
| **CrewAI**                    | Agents, Tasks, Tools                               | **Flows** with structured start/listen/router execution and state                                                        | `WORKFLOW_STEP` + `TOOL_CALL` ([CrewAI Documentation][9])               |
| **LlamaIndex**                | `ToolCall` / `ToolCallResult`                      | **Workflow `@step`** + typed events                                                                                      | `WORKFLOW_STEP` + `TOOL_CALL` ([Developer Documentation][10])           |
| **AutoGen**                   | Agent/tool calls                                   | `GraphFlow`: directed graph whose nodes are agents; currently experimental                                               | `WORKFLOW_STEP` + `TOOL_CALL` ([Microsoft GitHub][11])                  |
| **Snowflake Cortex Agents**   | Agent plans and calls Cortex/custom/MCP/code tools | Orchestration is LLM-driven plan → tool → reflect, not an exposed deterministic graph                                    | Primarily `TOOL_CALL` / agent execution ([Snowflake Documentation][12]) |

[1]: https://openai.github.io/openai-agents-python/?utm_source=chatgpt.com "OpenAI Agents SDK"
[2]: https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview?utm_source=chatgpt.com "Tool use with Claude - Claude Platform Docs"
[3]: https://ai.google.dev/gemini-api/docs/function-calling?utm_source=chatgpt.com "Function calling with the Gemini API  |  Google AI for Developers"
[4]: https://developers.googleblog.com/why-we-built-adk-20/?utm_source=chatgpt.com "Why we built ADK 2.0 - Google Developers Blog"
[5]: https://docs.langchain.com/oss/python/langgraph/graph-api?utm_source=chatgpt.com "Graph API overview - Docs by LangChain"
[6]: https://learn.microsoft.com/en-us/agent-framework/workflows/workflows?utm_source=chatgpt.com "Microsoft Agent Framework Workflows - Workflow Builder & Execution | Microsoft Learn"
[7]: https://docs.aws.amazon.com/bedrock/latest/userguide/tool-use.html?utm_source=chatgpt.com "Use a tool to complete an Amazon Bedrock model response - Amazon Bedrock"
[8]: https://strandsagents.com/docs/user-guide/concepts/multi-agent/graph/?utm_source=chatgpt.com "Graph Multi-Agent Pattern | Strands Agents"
[9]: https://docs.crewai.com/?utm_source=chatgpt.com "CrewAI Documentation - CrewAI"
[10]: https://docs.llamaindex.ai/en/stable/understanding/workflows/unbound_functions/?utm_source=chatgpt.com "Unbound syntax - LlamaIndex"
[11]: https://microsoft.github.io/autogen/dev/user-guide/agentchat-user-guide/graph-flow.html?utm_source=chatgpt.com "GraphFlow (Workflows) — AutoGen"
[12]: https://docs.snowflake.com/en/en/user-guide/snowflake-cortex/cortex-agents?utm_source=chatgpt.com "Cortex Agents | Snowflake Documentation"


## First-time Local Walkthrough

### 1. Start the local stack

From the repository root:

```bash
./servers.sh
docker compose ps
```

Open Studio at <http://localhost:3000>. The REST API and its interactive
OpenAPI documentation are available at <http://localhost:8000/docs>.

### Local thesis-validation profile

`synthetic_agent_runtime run --configure-test-windows` is intentionally
disabled by default: it grants the simulator's otherwise ingest-only service
account the narrowly scoped `settings.manage` permission and enables
minute-scale Runtime Findings windows for one project. For an isolated local
Docker run only, add the following to `.env.platform` and recreate the
`ai-governance-platform` service:

```env
AI_GOVERNANCE_SYNTHETIC_RUNTIME_TEST_SETTINGS_ENABLED=true
AI_GOVERNANCE_RUNTIME_FINDINGS_TEST_WINDOWS_ENABLED=true
AI_GOVERNANCE_RUNTIME_FINDINGS_TEST_WINDOW_PROJECT_ID=project_default
```

Remove or set the flags to `false` after the validation run and recreate the
service again. Do not enable this profile in shared or production deployments.

The broader local-stack instructions are in the
[End-to-End Local Tutorial](end-to-end-local.md).

### 2. Load the local runtime sample

Open **Agents Runtime** from the left navigation. A new local environment
shows an informational message that no sample data is loaded. This is normal.

Select **Load demo data**. The sample creates realistic executions, event
timelines, statuses, and findings for several agents. It is safe to select
again: the operation is idempotent and repairs a partial seed without
overwriting existing evidence.

After the complete sample is present, Studio changes the button to **Demo data
loaded** and disables it. Studio checks this state when the page opens; it does
not rely on a button click from the current browser session.

The seed endpoint is deliberately limited to local and development
environments:

```http
GET  /api/v1/local/demo/agent-runtime/status
POST /api/v1/local/demo/agent-runtime
```

Do not use demo data as production evidence.

### 3. Choose an agent instead of typing an ID

Open the **Executions** tab. The top list is a paginated list of agents that
already have execution evidence in the selected organization and project.

Select an agent row. The detail pane below the list shows the selected agent
and its recent execution records. This avoids asking an operator to guess an
agent ID.

The agent index is ordered by recent activity and supports Previous/Next page
navigation. It is derived from execution evidence, so an agent appears only
after its runtime has reported at least one execution.

### 4. Read the selected-agent panel

The panel has two layers of information.

**Lifecycle totals** describe all known executions for the selected agent:

- **Executions** — total observed executions.
- **Succeeded** — executions with a successful terminal status.
- **Failed** — executions with a failed terminal status.
- **Running** — executions that have started and are not terminal.

**Operational metrics** are calculated from the recent records currently
loaded in the detail table. The panel says how many records were used, so the
number is never mistaken for an unbounded lifetime statistic.

| Metric | What it means |
| --- | --- |
| Success rate | Successful executions divided by successful plus failed completed outcomes. Cancelled executions are excluded from this percentage. |
| Average duration | Average elapsed time for terminal executions in the loaded records. |
| Observed events | Sum of the event counts in the loaded records. |
| Cancelled | Number of loaded records ending in `CANCELLED`. |

Below the metrics, each execution row shows the runtime-owned execution ID,
status, start time, terminal duration, and number of recorded events. A long
duration is not automatically bad; compare it with the agent's normal
behaviour and the applicable runtime-finding thresholds.

## Findings: Operational Workflow

Open the **Findings** tab when you want a concise, explainable answer to:

> Is the current observed behaviour outside the configured limits?

Findings can be filtered by severity and lifecycle:

- **Open** means the measured condition is currently active or has not yet
  shown sustained recovery.
- **Resolved** means reconciliation observed enough healthy periods to close
  the finding.
- **Severity** is assigned by configured thresholds. It is not chosen by an
  LLM.

Each finding row shows its detector, subject, **Evidence / Change**, and
lifecycle status. Operational findings show the baseline-to-current comparison.
Causal Audit findings instead show evidence influence or the affected tool
call, because they explain one execution rather than a time-series anomaly.
The API retains bounded metric snapshots, evidence references, detector
version, timestamps, and related execution references so the observation can
be explained later.

### Detect vs Reconcile

These buttons do different jobs.

| Action | Use it when | What it does |
| --- | --- | --- |
| **Detect** | New execution evidence has arrived, or you want to evaluate current behaviour. | Runs the configured detectors and creates or refreshes findings for conditions that meet their thresholds. |
| **Reconcile operational** | A team has remediated an operational issue, or you want to check whether that condition has recovered. | Rechecks only open operational findings against current evidence and advances or resets their recovery state. Causal Audit findings are excluded. |
| **Acknowledge / close** | A person has reviewed a completed Causal Audit finding. | Records the reviewer and time, then leaves the historical causal result unchanged. |

Operational reconciliation is intentionally cautious. It does not close a finding after one
good observation. When the detector reports a normal condition with sufficient
evidence, the finding receives one normal window. If the condition returns—or
there is insufficient evidence—the normal-window count resets. The default
setting requires **two consecutive normal windows** before the finding becomes
resolved.

```text
OPEN finding
    │ reconcile sees normal evidence
    ▼
1 healthy window ── another normal result ──► RESOLVED
    │
    └── condition returns or evidence is insufficient ──► remains OPEN; counter resets
```

This protects operators from alert flapping: an intermittent problem does not
disappear just because one short period happened to look healthy.

Select **How this works** beside the actions to open the same explanation in a
right-side panel without leaving the Findings page.

### Response Pattern

When you see an open finding:

1. Read the detector and subject first. Know what was measured before acting.
2. Read **Evidence / Change**: compare baseline and current for operational
   findings, or review influence and the affected tool call for causal
   findings.
3. Open the relevant agent and inspect the execution sequence and errors.
4. Fix the runtime, model, tool, policy, integration, or data issue outside
   the control plane.
5. Let new evidence arrive, then select **Detect** to evaluate it.
6. Select **Reconcile operational** after remediation to confirm sustained recovery for an operational finding. For a causal finding, acknowledge and close the historical case after review.
7. Keep the finding open if evidence is insufficient. “Unknown” should not be
   treated as “healthy.”

## Configure Detectors Safely

Open **Settings → Agents Runtime**, or use the **Runtime settings** shortcut on
the Agents Runtime page.

This dedicated settings category contains the controls for runtime findings,
including:

- minimum observation counts;
- historical baseline and recent observation windows;
- absolute and relative detector thresholds;
- severity thresholds;
- recovery/resolution windows; and
- the shared count of consecutive normal windows needed for auto-resolution.

The currently supplied detector families are:

| Detector family | Example question it answers |
| --- | --- |
| Tool failure rate | Are calls to a particular tool failing more often than normal? |
| Agent execution failure rate | Is an agent failing more often than its baseline? |
| Execution latency regression | Is an agent taking materially longer than normal? |
| Evaluation failure rate | Has an evaluation outcome degraded? |
| Policy denial rate | Are policy denials becoming unusually common? |
| Repeated runtime error | Is the same runtime error recurring often enough to need attention? |

Settings use normal AI Governance Control Plane scope and precedence rules:

```text
Environment override → Project → Organization → System → Default
```

Use the narrowest appropriate scope. For example, a threshold that applies to
one project should normally be a project setting, not a global system setting.
Every change requires a reason and is versioned and auditable. An environment
override wins and is intentionally read-only in Studio.

See [Settings Control Plane](../architecture/SETTINGS_CONTROL_PLANE.md) for
scope, precedence, concurrency, and audit behaviour.

## Connect Real Agent Runtime

Your runtime sends one start record, zero or more ordered event records, and a
terminal status when the run ends.

### 1. Start Execution

```bash
curl -X POST http://localhost:8000/api/v1/agent-executions \
  -H 'Content-Type: application/json' \
  -H 'X-AI-Governance-Organization-Id: org_default' \
  -H 'X-AI-Governance-Project-Id: project_default' \
  -d '{
    "agent_id": "claims-agent-v2",
    "agent_name": "Claims Processing Agent",
    "agent_version": "2.1.0",
    "external_execution_id": "run-2026-08-18-001",
    "runtime_provider": "langchain",
    "correlation_id": "claim-8421",
    "metadata": {"workflow": "claims_intake"}
  }'
```

Save the returned `execution.execution_id`. It is the AI Governance Control
Plane identifier used for later events and completion. Repeating the same
start with the same tenant, runtime provider, and external execution ID is
idempotent.

### 2. Append Facts as Events

```bash
curl -X POST http://localhost:8000/api/v1/agent-executions/EXECUTION_ID/events \
  -H 'Content-Type: application/json' \
  -H 'X-AI-Governance-Organization-Id: org_default' \
  -H 'X-AI-Governance-Project-Id: project_default' \
  -d '{
    "event_type": "TOOL_CALL",
    "actor_id": "lookup_policy",
    "actor_type": "TOOL",
    "idempotency_key": "run-2026-08-18-001-tool-1",
    "attributes": {"tool": "lookup_policy", "latency_ms": 120}
  }'
```

Supported event types are:

```text
EXECUTION_STARTED, MODEL_CALL, TOOL_CALL, WORKFLOW_STEP, GOVERNANCE_DECISION,
EVALUATION, ERROR, EXECUTION_COMPLETED
```

`WORKFLOW_STEP` is optional provider-neutral orchestration evidence. It is not
a synonym for a tool call: a step can contain zero, one, or many tool calls,
and a provider that only exposes tools should continue to emit `TOOL_CALL`
events directly. A workflow-step event requires stable `step_id`, `step_name`,
and `lifecycle` (`STARTED`, `COMPLETED`, or `FAILED`); it can also contain a
same-execution `parent_step_id` and a bounded namespaced `source_kind` such as
`langgraph.node`.

```bash
curl -X POST http://localhost:8000/api/v1/agent-executions/EXECUTION_ID/events \
  -H 'Content-Type: application/json' \
  -H 'X-AI-Governance-Organization-Id: org_default' \
  -H 'X-AI-Governance-Project-Id: project_default' \
  -d '{
    "event_type": "WORKFLOW_STEP",
    "step_id": "claim-check-1",
    "step_name": "check_policy",
    "lifecycle": "COMPLETED",
    "source_kind": "langgraph.node",
    "idempotency_key": "run-2026-08-18-001-step-check-policy-complete"
  }'
```

Actor types are:

```text
AGENT, MODEL, TOOL, GOVERNANCE, EVALUATOR, SYSTEM
```

Use a stable idempotency key whenever the producer can retry an event delivery.

### 3. Complete Execution

```bash
curl -X POST http://localhost:8000/api/v1/agent-executions/EXECUTION_ID/complete \
  -H 'Content-Type: application/json' \
  -H 'X-AI-Governance-Organization-Id: org_default' \
  -H 'X-AI-Governance-Project-Id: project_default' \
  -d '{"status":"SUCCEEDED"}'
```

The terminal statuses are `SUCCEEDED`, `FAILED`, and `CANCELLED`. An execution
in `RECEIVED` or `RUNNING` is not terminal. Terminal execution records are
historical evidence and are not changed into a different terminal status.

### Data you must not send

Event attributes are operational metadata, not a raw transcript store. The
ingestion boundary rejects protected content and secrets, including fields for
prompts, system prompts, responses, messages, conversations, chain of thought,
reasoning, credentials, API keys, tokens, passwords, tool payloads, tool
arguments, tool outputs, and tool results.

Prefer compact, explainable facts such as a model identifier, elapsed time,
token count, error category, policy outcome, resource reference, or evidence
reference.

## API Reference

All paths are under `/api/v1`. Authentication and tenant context apply to
every protected request. See [REST API](../reference/REST_API.md) for the
platform-wide authentication model.

| Purpose | Method and path |
| --- | --- |
| Start an execution | `POST /agent-executions` |
| Append an event | `POST /agent-executions/{execution_id}/events` |
| Complete an execution | `POST /agent-executions/{execution_id}/complete` |
| List observed agents | `GET /agent-executions/agents?offset=0&limit=20` |
| List executions | `GET /agent-executions?agent_id=&status=&runtime_provider=&limit=` |
| Read execution detail and event timeline | `GET /agent-executions/{execution_id}` |
| Read events only | `GET /agent-executions/{execution_id}/events` |
| List findings | `GET /runtime-findings?severity=&status=&limit=` |
| Run detectors | `POST /runtime-findings/detect` |
| Reconcile open operational findings | `POST /runtime-findings/reconcile` |
| Acknowledge or close a causal case | `POST /runtime-findings/{finding_id}/review` |
| Read one finding | `GET /runtime-findings/{finding_id}` |

List execution statuses exactly as stored: `RECEIVED`, `RUNNING`, `SUCCEEDED`,
`FAILED`, or `CANCELLED`. Finding lifecycle values are `OPEN` and `RESOLVED`.

## Troubleshooting

| What you see | Meaning | What to do |
| --- | --- | --- |
| “No observed agents yet” | No execution evidence exists in the selected tenant scope. | Check the organization/project selector, send an execution, or load local demo data. |
| “No local demo data is loaded” | The local sample has not been seeded. This is informational, not an error. | Select **Load demo data** in a local or development environment. |
| “Demo data loaded” but no findings | The page may be filtered to a different lifecycle or severity, or the wrong tenant may be selected. | Set Severity to All and Lifecycle to All, confirm organization/project, then refresh. |
| An operational finding remains open after a fix | Reconcile needs sufficient evidence and the required number of consecutive healthy windows. | Send new evidence, run Detect, then Reconcile operational again after the next observation window. |
| A causal finding remains open | It describes a completed execution, so healthy time windows cannot resolve it. | Review the bounded causal evidence, then acknowledge and close the case if appropriate. |
| Reconcile does not resolve a finding | The condition may persist, evidence may be insufficient, or the healthy-window threshold has not been met. | Inspect the finding metrics and Settings → Agents Runtime. |
| The browser says “Failed to fetch” | The API request did not complete successfully. | Inspect the platform container logs and confirm `GET /api/v1/runtime-findings` returns 200. Rebuild the platform after code changes. |
| Demo seed is unavailable | The endpoint is intentionally blocked outside local/development environments. | Send real execution evidence instead; do not enable demo seeding in production. |

For the current local Docker stack, rebuild the platform and Studio after a
runtime feature change:

```bash
docker compose up -d --build ai-governance-platform ai-governance-studio
```

## Operating Rhythm

For a small team, the following cadence is a good starting point:

1. Ensure every important agent reports execution start, meaningful events,
   and completion.
2. Review the agent list daily for newly failing, slow, or unusually active
   agents.
3. Use Detect after deployments, configuration changes, or a meaningful volume
   of new evidence.
4. Investigate open findings with the source runtime team.
5. Use Reconcile operational after remediation and allow enough normal evidence to prove
   recovery.
6. Adjust detector settings only with a clear reason, at the appropriate
   tenant scope, and review the audit trail afterwards.

The important habit is simple: treat Agents Runtime as a place to observe and
verify behaviour, not as a place to invent a story about it.
