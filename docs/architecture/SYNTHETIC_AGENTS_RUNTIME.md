# Synthetic Agent Runtime Design

## Purpose

Synthetic Agent Runtime is an external simulator used to test how the AI Governance Control Plane behaves when connected to realistic AI agent systems.

It behaves like a client application rather than an internal component of the platform. The simulator creates realistic agent executions, calls multiple synthetic tools, makes decisions, introduces controlled failures, and sends runtime events to the governance platform through the same APIs that a real client would use.

The main objective is to answer:

> Can the platform correctly observe, understand, diagnose, replay, and evaluate realistic agent behaviour without owning the agent itself?

The simulator is therefore not just a data generator. It is a controlled external workload with known expected behaviour.

---

# Core Idea

A normal test often works like this:

```text
Generate random records
        ↓
Insert into database
        ↓
Check application
```

That would not adequately test our architecture because it would bypass authentication, ingestion, validation, ordering, idempotency, event handling, tenant isolation, and other real boundaries. Synthetic Agent Runtime instead behaves like this:

```text
Synthetic Agent Runtime
        ↓
Authentication
        ↓
Public Agent Runtime APIs
        ↓
AI Governance Control Plane
        ↓
PostgreSQL
        ↓
Runtime Findings
        ↓
Ontology
        ↓
Replay
        ↓
Causal Audit
```

The simulator must never directly write runtime records into the platform database.

---

# Design Principles

The design follows several important rules.

```text
Simulator owns simulation.

Governance platform owns governance.

Simulator owns synthetic agent behaviour.

Governance platform owns Runtime Findings.

Simulator owns replayable synthetic execution state.

Governance platform owns Replay lifecycle.

Simulator knows the expected answer.

Governance platform must independently discover the answer.
```

The last rule is particularly important.

If the simulator expects:

```text
TOOL_FAILURE_RATE_INCREASE
```

- It must not tell the Runtime Findings detector to create that result.
- It only produces the conditions that should cause the platform to discover the finding.

---

# System Boundary

The two systems remain independently deployable.

```text
+-----------------------------------------------------+
| Synthetic Agent Runtime                             |
|                                                     |
| Scenario engine                                     |
| Synthetic agents                                    |
| Synthetic tools                                     |
| Decision logic                                      |
| Failure injection                                   |
| Replay state                                        |
| Ground truth                                        |
| SQLite simulator state                              |
+---------------------------+-------------------------+
                            |
                            | HTTPS / REST
                            |
                            v
+-----------------------------------------------------+
| AI Governance Control Plane                         |
|                                                     |
| Authentication                                      |
| Agent Runtime ingestion                             |
| Runtime persistence                                 |
| Runtime ontology                                    |
| Runtime Findings                                    |
| Evidence finalization                               |
| Reconciliation                                      |
| Replay                                              |
| Causal Audit                                        |
| Evaluation                                          |
+-----------------------------------------------------+
```

There is no shared database contract between them.

---

# Guide

Think of the simulator as a realistic practice agent. It performs an insurance
decision outside AI Governance Control Plane and sends the same kind of
high-level events that a real agent runtime would send. The platform can then
ask a narrow question: *did this particular tool result actually change the
decision?*

It does not copy the agent, the prompt, or the tool result into the platform.
Instead, it records safe labels that let the original runtime find the same
execution and tool call again if a controlled replay is approved.

| Term | Meaning |
|---|---|
| Observed Execution | One completed agent run that the platform has received. |
| Causal Audit | A check of whether changing one piece of tool evidence changes the outcome. |
| Controlled Replay | A fresh, isolated run performed by the original runtime with one approved evidence change. |
| Evidence Influence | The measured difference between the original and controlled outcome. |
| Classification | The platform's own conclusion, such as “the evidence mattered” or “it was ignored.” |

## Machine Identities

Two existing Keycloak service accounts have different jobs. They must not be
merged or replaced with a person’s login.

| Identity | What it may do | What it must not do |
|---|---|---|
| `synthetic-agent-runtime` | Send simulator executions and events into `org_default/project_default`. | Create Causal Audits or change governance policies. |
| `ai-governance-service` | Act as the local Causal Audit validator in `org_default/project_default`: read the observed execution, create the approved audit work, and read its result. | Ingest simulator events or receive organization-admin access. |

Keycloak proves which machine is calling. AI Governance Control Plane stores
the machine's membership and project role. Re-running provisioning is safe: it
uses the existing immutable Keycloak service-account subject and does not
create another Keycloak identity.

---

# Domain Choice

The simulator focuses on financial-services decisioning because these workloads naturally involve multiple evidence sources and multiple tool calls.

The initial domains are:

```text
Vehicle insurance claims
Transaction fraud investigation
Lending and credit decisioning
```

These domains are useful because decisions usually depend on several independent pieces of evidence. For example, an insurance claim might involve:

```text
Claim
  ↓
Policy lookup
  ↓
Claim history
  ↓
Damage assessment
  ↓
Evidence verification
  ↓
Risk scoring
  ↓
Governance policy
  ↓
Decision
```

This creates realistic conditions for both Runtime Findings and Causal Audit.

---

# Vehicle Insurance Domain

A claim execution may involve tools such as:

```text
policy.lookup
claim_history.lookup
vehicle_damage.evaluate
evidence.verify
fraud.lookup
risk_model.score
governance.policy.evaluate
```

Possible decisions include:

```text
APPROVE
REVIEW
REQUEST_MORE_EVIDENCE
REJECT
```

A low-risk claim may require only a few calls.

A suspicious claim may require several:

```text
Claim received
      ↓
Policy valid?
      ↓
Previous suspicious claims?
      ↓
Damage evidence consistent?
      ↓
Fraud indicators?
      ↓
Risk score
      ↓
Policy evaluation
      ↓
REVIEW
```

This gives us realistic multi-tool trajectories rather than artificial event streams.

---

# Fraud Domain

The fraud agent simulates transaction investigation.

Typical tools include:

```text
customer_profile.lookup
transaction_history.lookup
device_risk.lookup
merchant_risk.lookup
velocity_check
fraud_model.score
policy.evaluate
```

Possible outcomes are:

```text
ALLOW
REVIEW
BLOCK
```

Example:

```text
Transaction
    ↓
Customer history
    ↓
Device reputation
    ↓
Velocity check
    ↓
Fraud model
    ↓
Policy
    ↓
BLOCK
```

The simulator can deliberately degrade one part of this path. For example:

```text
device_risk.lookup

Normal failure rate:
2%

Incident failure rate:
25%
```

The platform should then detect the change rather than being told that an incident exists.

---

# Lending Domain

The lending agent represents a credit application workflow. Typical tools include:

```text
applicant_profile.lookup
income.verify
credit_history.lookup
debt_obligations.lookup
affordability.calculate
credit_model.score
lending_policy.evaluate
```

Possible decisions include:

```text
APPROVE
REVIEW
DECLINE
```

Example:

```text
Applicant
    ↓
Income verification
    ↓
Credit history
    ↓
Debt obligations
    ↓
Affordability
    ↓
Risk score
    ↓
Policy
    ↓
APPROVE
```

This domain is particularly useful for causal testing because changing one important piece of evidence may legitimately change the final decision.

---

# Execution Model

The simulator generates executions rather than isolated event rows.

The default rate is:

```text
1 execution per second
```

This is configurable. One execution may generate several events:

```text
EXECUTION_STARTED
MODEL_CALL
TOOL_CALL
TOOL_CALL
GOVERNANCE_DECISION
EVALUATION
EXECUTION_COMPLETED
```

Therefore:

```text
1 execution / second
```

does not mean:

```text
1 event / second
```

If an average execution generates eight events, the actual runtime event rate is approximately:

```text
8 events / second
```

The execution rate can later be increased for load testing.

---

# Deterministic Generation

The simulator uses seeded randomness. For example:

```text
scenario = thesis-validation
seed = 42
```

must generate the same behavioural sequence whenever the same conditions are used. This gives us reproducibility. Without a deterministic seed, a failed validation would be difficult to diagnose because we would not know whether the platform was wrong or whether the random workload simply changed.

The simulator therefore combines:

```text
Scenario rules
+
Seeded randomness
```

The scenario determines what kind of behaviour should occur. The seed determines which individual executions experience that behaviour.

---

# Scenario Engine

A scenario describes how the simulated environment changes over time. The primary scenario is:

```text
thesis-validation
```

A simplified run looks like:

```text
Phase 1
Healthy baseline

Phase 2
Controlled degradation

Phase 3
Runtime Findings expected

Phase 4
Causal Audit fixtures generated

Phase 5
Late events introduced

Phase 6
System recovers

Phase 7
Healthy finalized windows accumulate

Phase 8
Findings resolve

Phase 9
Expected results compared with platform results
```

This allows one simulator run to exercise several platform capabilities.

---

# Runtime Findings Coverage

The simulator deliberately creates conditions for all six Runtime Findings detectors.

## Tool failure increase

Example:

```text
policy.lookup

Baseline:
2% failures

Current:
25% failures
```

Expected platform result:

```text
TOOL_FAILURE_RATE_INCREASE
```

## Agent failure increase

Example:

```text
fraud-investigation-agent

Baseline:
3% failed executions

Current:
20% failed executions
```

Expected result:

```text
AGENT_EXECUTION_FAILURE_RATE_INCREASE
```

## Latency regression

Example:

```text
credit_history.lookup

Baseline P95:
700 ms

Current P95:
4.5 seconds
```

Expected result:

```text
EXECUTION_LATENCY_REGRESSION
```

- Sample count remains the number of eligible executions.
- Median and P95 remain latency measurements.

These are separate concepts.

## Evaluation failure increase

The simulator deliberately causes an increase in failed runtime-linked evaluations.

Expected result:

```text
EVALUATION_FAILURE_RATE_INCREASE
```

## Policy denial increase

Example:

```text
Normal lending policy denials:
5%

Incident:
30%
```

Expected result:

```text
POLICY_DENIAL_RATE_INCREASE
```

## Repeated runtime error

The simulator repeatedly emits a known structured error such as:

```text
UPSTREAM_PROFILE_TIMEOUT
```

Expected result:

```text
REPEATED_RUNTIME_ERROR
```

---

# Finding Recovery

Detection is only half of the lifecycle. The simulator must also prove that a finding can recover correctly.

Example:

```text
Healthy
    ↓
Tool starts failing
    ↓
Finding OPEN
    ↓
Tool returns to normal
    ↓
Healthy finalized window 1
    ↓
Recovery 1 / 2
    ↓
Healthy finalized window 2
    ↓
RESOLVED
```

A user pressing Reconcile repeatedly cannot artificially resolve the finding.

The invariant is:

```text
Resolution
=
N distinct
+ consecutive
+ healthy
+ closed
+ evidence-finalized windows
```

It is not:

```text
N reconcile requests
```

---

# Evidence Windows

Runtime Findings need time windows because they are measuring behaviour over a population of executions.

For example:

```text
Historical baseline:
previous 7 days

Observation:
latest 1 hour
```

The detector asks:

> Has recent behaviour materially changed compared with normal behaviour?

A window first becomes closed when its clock period ends. But closed does not necessarily mean complete.

---

# Evidence Finalization

Runtime events can arrive late. Imagine an observation window ends at midnight.

```text
Window:
23:00 → 00:00
```

Some events from that hour might reach the platform after midnight. If the configured lateness allowance is two hours:

```text
Window closes:
00:00

Window finalizes:
02:00
```

- Events received before 02:00 can still participate in that window.
- Events arriving after the cutoff remain valid runtime history, but cannot rewrite the already-finalized Runtime Findings decision.

Therefore:

```text
Runtime history
=
what eventually happened

Runtime Findings window
=
what was available under the declared
finalization contract
```

Both are valid, but they serve different purposes.

---

# Compressed Validation Windows

Production Runtime Findings may reasonably use hours or days of evidence. That would make simulator testing painfully slow.

For local validation we may want:

```text
Baseline:
a few minutes

Observation:
1 minute

Resolution:
1 minute

Lateness:
a few seconds or zero
```

This does not mean production should use these values. The difference is:

```text
Production
    ↓
window determined by traffic,
risk and required confidence

Simulator
    ↓
compressed window so several
behavioural phases can be tested quickly
```

Production defaults should remain conservative.
- A high-volume production customer may legitimately choose smaller windows.
- A low-volume customer may need much larger windows.

Window size is therefore an operational policy, not a simulator constant.

---

# Causal Audit Purpose

Runtime Findings answer questions such as:

> Has tool failure increased?

Causal Audit answers a very different question:

> Did the evidence returned by this tool actually influence the agent's decision?

Causal Audit operates on an individual replay-capable execution.

Example:

```text
Original execution

claim_history.lookup
    ↓
4 suspicious previous claims
    ↓
Agent decision = REVIEW
```

Now change the evidence:

```text
Controlled Replay

claim_history.lookup
    ↓
clean claim history
    ↓
Agent decision = APPROVE
```

The decision changed. That suggests the claim-history evidence materially influenced the outcome.

---

# Why Replay calls the simulator?

AI Governance Platform observed the original execution, but it does not execute the client's agent. Therefore we cannot independently answer:

> What would this agent have done with different evidence?

The system that owns execution semantics must perform that rerun.

For the simulator:

```text
AI Governance Platform
   ↓
Replay adapter
   ↓
Synthetic Agent Runtime /replay
   ↓
rerun synthetic execution
   ↓
counterfactual outcome
   ↓
AI Governance Platform
```

This preserves the ownership boundary.
- AI Governance Platform controls the Replay lifecycle.
- The external runtime controls how its agent actually executes.

---

# Replay Capability

Not every observed execution is automatically replayable. A replayable synthetic execution explicitly declares a capability such as:

```text
adapter:
synthetic-agent-runtime/v1

replay reference:
synthetic://replays/...
```

AI Governance Platform persists that capability. When Replay is requested:

```text
Observed execution
      ↓
Replay capability
      ↓
Replay adapter registry
      ↓
synthetic-agent-runtime/v1
      ↓
Synthetic Runtime
```

There is no silent fallback to another adapter.

For a causal replay, each eligible `TOOL_CALL` carries a first-class,
reference-only `ToolCallContext`. Its runtime-native
`runtime_tool_call_id` (for example OpenAI `call_id`, LangGraph tool-call
`id`, or Anthropic `tool_use.id`) is paired with the observed
`external_execution_id`; Core-generated event IDs are never used as an
external runtime command. The adapter sends those identifiers plus the
original and counterfactual evidence digests to `/replay`. Prompts, tool
arguments, tool results, responses, and reasoning remain outside Core.

In everyday terms, these are the only identifiers Core needs:

```text
external_execution_id = “which original agent run?”
runtime_tool_call_id = “which exact tool call inside that run?”
```

They come from the runtime itself. For example, this is OpenAI's `call_id`, a
LangGraph tool-call `id`, or an Anthropic `tool_use.id`. The replay produces a
new run and may receive new IDs; Core never assumes the new run reuses the
old ones.

## Tool-call execution context

`ToolCallContext` is the provider-neutral observation of one tool call's
runtime execution structure. It is optional during ordinary ingestion, because
a runtime may expose only a partial trace, but a controlled-replay target must
provide it.

```text
sequence_number          = stable observed timeline position
runtime_tool_call_id     = runtime-native identity for one invocation
tool_call_group_id       = logical batch/group, not proof of wall-clock overlap
depends_on_tool_call_ids = explicit dependencies in this execution
causation_id             = event-level provenance link
```

Core does not infer dependencies from sequence numbers or timestamps. During
replay preparation it validates the explicit graph and fails closed for missing
references, duplicate runtime IDs, and cycles. The captured graph is source
provenance, not a replay script: a counterfactual execution may take a
different downstream path.

When a runtime cannot disclose evidence contents, an operator can select the
`opaque-reference/v1` intervention provider. It produces only a governed
counterfactual reference and digest; the external runtime validates and applies
the actual change inside its isolated replay boundary.

---

# Replay Endpoint Protection

An observed execution must not be allowed to make the Replay worker call arbitrary URLs. The external adapter therefore uses an approved endpoint:

```text
AI_GOVERNANCE_SYNTHETIC_RUNTIME_REPLAY_ENDPOINT
```

The persisted capability endpoint must exactly match the approved configuration. Conceptually:

```text
Execution says:
"Replay me at X"
      ↓
Core asks:
"Is X the approved runtime endpoint?"
      ↓
No
      → fail closed

Yes
      ↓
Replay
```

This prevents replay metadata from becoming an SSRF-style arbitrary network-call mechanism.

An optional service-to-service replay credential can protect the synthetic
runtime boundary:

```text
AI_GOVERNANCE_SYNTHETIC_RUNTIME_REPLAY_AUTH_TOKEN
```

The replay worker sends it as a Bearer token. It is not a Studio user token or
the Keycloak browser token; the runtime must configure the same secret for its
`/replay` endpoint.

---

# Replay Interventions

The simulator supports controlled evidence changes.

## Nullify

Remove the evidence.

Example:

```text
fraud evidence:
HIGH_RISK
```

becomes:

```text
no fraud evidence
```

## Replace

Replace the evidence with another valid synthetic result.

Example:

```text
claim history:
4 suspicious claims
```

becomes:

```text
claim history:
clean
```

## Perturb

Modify evidence deterministically.

Example:

```text
risk score:
0.81
```

becomes:

```text
risk score:
0.55
```

The same intervention configuration and seed must produce the same result.

---

# Causal Scenarios

The simulator contains known causal behaviours.

## Evidence aligned

Evidence changes and the decision changes appropriately.

```text
Evidence changes
      ↓
Outcome changes
```

Expected classification:

```text
EVIDENCE_ALIGNED
```

## Evidence ignored

The agent calls a tool but behaves the same regardless of what the tool returns.

```text
Tool evidence changes
      ↓
Outcome remains identical
```

Expected classification:

```text
EVIDENCE_IGNORED
```

## Over extended

The agent receives sufficient useful evidence but continues making unnecessary tool calls.

Example:

```text
Policy says claim is excluded
      ↓
Decision is already clear
      ↓
Agent still calls
fraud lookup
risk model
claim history
damage evaluator
```

Expected classification:

```text
OVER_EXTENDED
```

## No tool evidence

An execution has no auditable tool evidence.

Expected classification:

```text
NO_TOOL_EVIDENCE
```

---

# Replay Cost

A real client Replay may have a financial cost. If Replay requires:

```text
model inference
tool execution
sandbox infrastructure
evaluation
```

then Causal Audit produces additional workload.

Causal Audit should therefore not automatically run against every production execution. A production model should support:

```text
sampling
risk-based selection
manual investigation
policy-triggered audits
budgets
rate limits
cost attribution
```

The simulator does not have meaningful inference cost because its behaviour is deterministic. But it lets us validate the architecture required for real clients.

---

# Authentication

Synthetic Agent Runtime authenticates like an external service. It uses a dedicated machine identity through Keycloak rather than relying on a manually copied development token.

The flow is:

```text
Synthetic Agent Runtime
        ↓
OAuth client credentials
        ↓
Keycloak
        ↓
short-lived access token
        ↓
AI Governance Platform
```

The simulator caches the short-lived token and refreshes it when necessary. Authentication proves who the external runtime is. AI Governance Platform authorization determines what that identity is allowed to do.

---

# Authorization

The simulator receives only the permissions required for its integration.

Examples include:

```text
Agent execution ingestion
Agent execution reads
Runtime Findings reads
Replay operations
Causal Audit operations
```

Test-only capabilities such as changing compressed detector windows should be separately controlled. Machine authentication must not imply administrative access.

---

# Tenant scope

- Every runtime operation remains organization and project scoped.
- The simulator operates against an explicitly configured organization and project.
- Authentication identifies the caller.
- Organization/project context identifies the target scope.
- AI Governance Platform verifies that the caller has permission for that scope.
- The simulator cannot gain access merely by changing an organization header.

---

# Simulator State

The simulator owns a small SQLite database. This database stores simulator concerns such as:

```text
Simulation run
Scenario
Seed
Current phase
Generated execution
Replay state
Expected outcome
Ground truth
```

It does not duplicate AI Governance Platform runtime persistence. The distinction is:

```text
Simulator SQLite
    → what we intended to simulate

AI Governance Platform PostgreSQL
    → what the platform actually observed
```

This separation is essential for independent validation.

---

# Ground Truth

Ground truth is one of the most valuable parts of the simulator. For each controlled scenario, the simulator knows what should happen.

Example:

```text
Scenario says:

policy.lookup failure rate becomes 30%

Expected:
TOOL_FAILURE_RATE_INCREASE
```

Or:

```text
Original evidence:
HIGH_RISK

Counterfactual evidence:
LOW_RISK

Expected outcome transition:
REVIEW → APPROVE

Expected causal classification:
EVIDENCE_ALIGNED
```

The simulator persists this expected result independently. The validation step then compares:

```text
Expected
    vs
Observed
```

This is much stronger than checking whether the API returned HTTP 200.

---

# Validation

After a simulator run, validation checks the platform's conclusions. Conceptually:

```text
Runtime ingestion               PASS
Execution lifecycle             PASS
Tool failure finding            PASS
Agent failure finding           PASS
Latency finding                 PASS
Evaluation finding              PASS
Policy denial finding           PASS
Repeated error finding          PASS
Late evidence classification    PASS
Finding recovery                PASS
External Replay                 PASS
Evidence influence              PASS
Causal classifications          PASS
```

If something differs:

```text
Expected:
EVIDENCE_ALIGNED

Observed:
EVIDENCE_IGNORED
```

The validator reports the mismatch. That result becomes an engineering investigation rather than being silently accepted.

---

# Why this simulator matters

The simulator has already demonstrated its architectural value. It exposed core defects that normal seeded demo data had not revealed:

```text
Tool discovery did not discover actual tool IDs.

Latency observation count used the wrong value.

External Replay had no real runtime adapter.
```

The correct response was to repair core. The simulator payload was not changed to hide the defects. This establishes an important future rule:

> When realistic simulator behaviour exposes a platform defect, first investigate the platform contract rather than teaching the simulator to accommodate incorrect behaviour.

---

# Local Deployment

The current development topology can look like:

```text
Host
│
├── Synthetic Agent Runtime
│      :8090
│
└── Docker
       │
       ├── AI Governance API
       ├── PostgreSQL
       ├── Neo4j
       ├── workers
       └── Replay worker
```

Because the Replay worker runs inside Docker, it cannot use:

```text
127.0.0.1:8090
```

Inside the container, `127.0.0.1` refers to the container itself. The worker therefore uses:

```text
host.docker.internal:8090
```

The flow becomes:

```text
Replay worker container
        ↓
host.docker.internal
        ↓
host
        ↓
Synthetic Agent Runtime
```

If the simulator later runs inside the same Docker network, service-name routing should be preferred.

---

# Failure Behaviour

The simulator and core must assume failures will happen. Examples include:

```text
Core API unavailable
Keycloak unavailable
Network timeout
429 response
5xx response
Replay runtime unavailable
Unknown replay reference
Invalid replay response
Process restart
```

Transient failures may be retried with bounded backoff. Deterministic failures should fail quickly.

Examples:

```text
401 authentication failure
403 authorization failure
invalid replay reference
unsupported intervention
malformed request
```

Infinite retries are not acceptable.

---

# Idempotency

- Runtime delivery may be retried.
- That must not create duplicate executions or events.
- The simulator therefore generates stable idempotency identities.

Conceptually:

```text
same event
+ retry
=
same logical event
```

not:

```text
same event
+ retry
=
two persisted events
```

Replay follows the existing Kavach replay idempotency model rather than creating simulator-specific behaviour.

---

# Privacy

The simulator sends only bounded operational information into the runtime platform.

It should never emit:

```text
chain of thought
credentials
real customer information
raw prompts
private conversations
arbitrary production tool payloads
```

Evidence needed for simulation and replay remains synthetic. Core-facing events use references, digests, structured status, metrics and safe identifiers.

---

# Observability

The simulator should expose enough information to diagnose its own behaviour. Useful signals include:

```text
executions generated
events generated
events delivered
events retried
events failed
current phase
replays requested
replays succeeded
replays failed
core API latency
```

High-cardinality identifiers such as execution ID should remain in logs rather than metric dimensions.

---

# Scalability Model

The simulator starts at approximately:

```text
1 execution / second
```

This is primarily a functional validation workload. Later the same simulator can be used
depending on the purpose of the test.

```text
10 executions / second
100 executions / second
1000 executions / second
```

The important distinction is:

```text
Functional simulation
    → Is behaviour correct?

Load simulation
    → Where does the system break?
```

These should not be confused. A large event volume does not prove semantic correctness.

---

# Operational Ownership

Responsibilities remain clear.

| Component | Responsibility |
|---|---|
| Synthetic Agent Runtime | Generate realistic deterministic agent behaviour |
| Keycloak | Authenticate the external runtime |
| Agent Runtime ingestion | Validate and persist observed executions/events |
| PostgreSQL | Authoritative runtime history |
| Neo4j | Derived runtime relationships |
| Runtime Findings | Detect operational behavioural changes |
| Evidence finalization | Define when observation windows become immutable for findings |
| Replay | Own replay lifecycle and intervention orchestration |
| Synthetic Replay adapter | Translate Replay into simulator-specific execution |
| Synthetic Agent Runtime `/replay` | Re-execute synthetic agent behaviour |
| Evaluation | Score outcomes |
| Causal Audit | Measure evidence influence and classify behaviour |
| Simulator ground truth | Record what the platform is expected to discover |

No component should quietly absorb another component's responsibility.

---

# Key Architectural Invariants

The system should preserve these rules.

- The simulator never writes directly to Kavach runtime tables.
- PostgreSQL remains authoritative for observed runtime history.
- Neo4j remains derived and rebuildable.
- Runtime Findings remain deterministic.
- Finding resolution uses finalized evidence windows.
- Late events remain visible but cannot rewrite finalized decisions.
- Observed execution does not automatically mean replayable execution.
- Replay capability must be explicit.
- External replay destinations must be approved.
- Replay fails closed.
- Causal classification remains deterministic.
- The simulator owns ground truth but cannot dictate conclusions.
- Production Runtime Findings settings are not weakened to make local testing convenient.

---

# Current Maturity

The simulator now proves several important boundaries.

```text
External machine identity
        ✓

Authenticated Runtime ingestion
        ✓

Insurance/Fraud/Lending traffic
        ✓

All six Runtime Findings inputs
        ✓

Correct tool discovery
        ✓

Correct latency sample semantics
        ✓

Late-event finalization
        ✓

Finding reconciliation
        ✓

External replay adapter
        ✓

NULLIFY / REPLACE / PERTURB
        ✓

External Causal Audit path
        ✓

Four deterministic causal classifications
        ✓
```

The major remaining local validation concern is making Runtime Findings windows sufficiently compressed for a practical end-to-end simulator run while retaining the same production semantics.

---

# Future Evolution

The simulator should remain deliberately smaller than a real agent framework. Useful future extensions may include:

```text
Higher throughput testing
Multiple concurrent runtime instances
Additional scenarios
Agent version changes
Model version changes
Tool version changes
Dependency outages
Policy changes
Replay cost simulation
Replay budget enforcement
Long-running soak tests
Chaos scenarios
Cross-agent behaviour
```

These should be added only when they test a meaningful platform hypothesis. The simulator should not evolve into another production application merely because it can.

---

# Success Criteria

The simulator succeeds when the governance platform can independently reach the expected conclusions from realistic external agent behaviour.

The final thesis is:

```text
Realistic financial-services agents
        ↓
multiple tool calls
        ↓
models and evidence
        ↓
governance decisions
        ↓
runtime events
        ↓
deterministic findings
        ↓
evidence finalization
        ↓
recovery
        ↓
controlled replay
        ↓
counterfactual outcomes
        ↓
causal audit
        ↓
expected conclusions
```

The strongest validation is not:

> We generated thousands of events.

It is:

> We knew what behaviour occurred, platform observed only the permitted runtime evidence and independently reached the correct operational and causal conclusions.
