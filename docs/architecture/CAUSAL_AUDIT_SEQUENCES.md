# Causal Audit & Controlled Replay Sequence Diagrams

This companion to [Causal Audit](CAUSAL_AUDIT.md) describes the durable
interactions between Studio, policy governance, Causal Audit, Replay, and a
runtime-owned controlled Replay adapter. It is intentionally split into small
diagrams: policy governance, audit submission, counterfactual execution,
review, and failure handling have different owners and terminal conditions.

## 1. Govern Intervention Policy

An intervention policy authorizes exactly one controlled evidence strategy for
one runtime-declared evidence identity. Validation and preview are safety
operations; neither creates a Replay or Evidence Influence record.

```mermaid
sequenceDiagram
    autonumber

    actor Operator
    participant Studio
    participant PolicyAPI as Intervention Policy REST API
    participant PolicyService as Policy Governance Service
    participant RuntimeRepo as Agent Runtime Repository
    participant PolicyRepo as Policy Repository

    Operator->>Studio: Create intervention policy
    Studio->>PolicyAPI: Submit target, evidence identity,<br/>provider, configuration, strategy
    PolicyAPI->>PolicyService: Create DRAFT policy
    PolicyService->>RuntimeRepo: Resolve runtime capability<br/>and evidence descriptor
    RuntimeRepo-->>PolicyService: Capability + evidence contract
    PolicyService->>PolicyRepo: Persist immutable DRAFT version
    PolicyRepo-->>PolicyService: Policy ID + version
    PolicyService-->>PolicyAPI: DRAFT policy
    PolicyAPI-->>Studio: Render policy

    Operator->>Studio: Validate policy
    Studio->>PolicyAPI: Validate exact policy version
    PolicyAPI->>PolicyService: Validate policy
    PolicyService->>RuntimeRepo: Verify target, evidence identity,<br/>strategy and provider compatibility
    RuntimeRepo-->>PolicyService: Validation result

    alt Validation fails
        PolicyService-->>PolicyAPI: Validation errors
        PolicyAPI-->>Studio: Show fail-closed diagnostics
        Note over Studio,PolicyRepo: Policy remains DRAFT
    else Validation succeeds
        PolicyService-->>PolicyAPI: VALID
        PolicyAPI-->>Studio: Validation succeeded
    end

    Operator->>Studio: Preview intervention
    Studio->>PolicyAPI: Preview exact policy version
    PolicyAPI->>PolicyService: Generate non-executing preview
    PolicyService-->>PolicyAPI: Preview + expected evidence transformation
    PolicyAPI-->>Studio: Render preview
    Note over Studio,PolicyRepo: Preview creates no Replay and no Evidence Influence

    Operator->>Studio: Activate policy
    Studio->>PolicyAPI: Activate exact validated version
    PolicyAPI->>PolicyService: Activate policy
    PolicyService->>PolicyRepo: Persist ACTIVE immutable version
    PolicyRepo-->>PolicyService: ACTIVE policy
    PolicyService-->>PolicyAPI: ACTIVE
    PolicyAPI-->>Studio: Render ACTIVE policy
```

## 2. Submit Causal Audit

The API only accepts an audit when the source execution, selected policy, and
runtime capability prove that a safe controlled Replay can be run. It returns
after queueing durable work; the observed execution is never changed.

```mermaid
%%{init: {"theme":"base","themeVariables":{"background":"#ffffff","primaryColor":"#f8fafc","primaryTextColor":"#111827","primaryBorderColor":"#94a3b8","lineColor":"#64748b","secondaryColor":"#eff6ff","tertiaryColor":"#f8fafc","actorBkg":"#ffffff","actorBorder":"#64748b","actorTextColor":"#111827","signalColor":"#334155","signalTextColor":"#111827","noteBkgColor":"#f8fafc","noteBorderColor":"#93c5fd","noteTextColor":"#111827","activationBkgColor":"#dbeafe","activationBorderColor":"#2563eb"}}}%%
sequenceDiagram
    autonumber
    actor Caller as Studio or API Client
    participant AuditAPI as Causal Audit REST API
    participant Tenant as Tenant Context
    participant AuditService as Causal Audit Service
    participant RuntimeStore as Agent Runtime Repository
    participant PolicyStore as Policy Repository
    participant AuditStore as Causal Audit Repository
    participant Jobs as Durable Job Queue

    Caller->>AuditAPI: Submit execution, policy version, strategy, samples, and seed
    AuditAPI->>Tenant: Authenticate and resolve organization + project scope
    Tenant-->>AuditAPI: Authorized TenantContext
    AuditAPI->>AuditService: Create or return idempotent audit
    AuditService->>RuntimeStore: Read succeeded source execution + tool evidence
    RuntimeStore-->>AuditService: Outcome artifact + capability + evidence descriptors
    AuditService->>PolicyStore: Read exact ACTIVE immutable policy version
    PolicyStore-->>AuditService: Target, provider, configuration, strategy permission

    AuditService-->>AuditAPI: If ineligible, return explicit fail-closed error
    AuditAPI-->>Caller: Ineligible: no Replay and no influence
    AuditService->>AuditStore: If eligible, persist QUEUED audit and immutable inputs
    AuditService->>Jobs: Submit idempotent causal-audit job
    Jobs-->>AuditAPI: Durable job accepted
    AuditAPI-->>Caller: Eligible: audit_id + QUEUED status
```

## 3. Execute Controlled Evidence & Finalize Audit

This is the causal mechanism. Causal Audit composes Replay; it does not create
another execution engine. The runtime adapter owns evidence resolution and
safe isolated re-execution using the frozen source reference.

```mermaid
%%{init: {"theme":"base","themeVariables":{"background":"#ffffff","primaryColor":"#f8fafc","primaryTextColor":"#111827","primaryBorderColor":"#94a3b8","lineColor":"#64748b","secondaryColor":"#eff6ff","tertiaryColor":"#f8fafc","actorBkg":"#ffffff","actorBorder":"#64748b","actorTextColor":"#111827","signalColor":"#334155","signalTextColor":"#111827","noteBkgColor":"#f8fafc","noteBorderColor":"#93c5fd","noteTextColor":"#111827","activationBkgColor":"#dbeafe","activationBorderColor":"#2563eb"}}}%%
sequenceDiagram
    autonumber
    participant AuditWorker as Causal Audit Worker
    participant AuditStore as Causal Audit Repository
    participant RuntimeStore as Agent Runtime Repository
    participant PolicyStore as Policy Repository
    participant Provider as Intervention Provider
    participant Resolver as Runtime Evidence Resolver
    participant ReplayService as Replay Application Service
    participant ReplayStore as Replay Repository
    participant ReplayJobs as Replay Job Queue
    participant ReplayWorker as Replay Worker
    participant Adapter as Controlled Replay Adapter
    participant Scorer as Outcome Scorer

    AuditWorker->>AuditStore: Claim QUEUED audit
    AuditWorker->>RuntimeStore: Freeze source execution + auditable tool calls
    AuditWorker->>PolicyStore: Read policy id + immutable version
    AuditWorker->>Scorer: Score observed outcome artifact
    Scorer-->>AuditWorker: Baseline score

    AuditWorker->>Resolver: For each tool call and requested sample, resolve evidence
    Resolver-->>AuditWorker: Opaque evidence reference + digest
    AuditWorker->>Provider: Apply NULLIFY, REPLACE, or PERTURB
    Provider-->>AuditWorker: Schema-valid control + intervention digest
    AuditWorker->>ReplayService: Create controlled Replay with frozen source and policy lineage
    ReplayService->>ReplayStore: Persist controlled_replay metadata
    ReplayService->>ReplayJobs: Submit Replay execution job
    ReplayJobs->>ReplayWorker: Execute controlled Replay
    ReplayWorker->>Adapter: Re-execute isolated source with controlled evidence
    Adapter-->>ReplayWorker: Counterfactual execution + bounded outcome artifact
    ReplayWorker->>ReplayStore: Persist EXECUTION_COMPLETED + produced execution

    ReplayWorker->>AuditWorker: Signal controlled Replay completion
    AuditWorker->>ReplayStore: Read every Replay and produced execution
    AuditWorker->>Scorer: Score every counterfactual outcome artifact
    Scorer-->>AuditWorker: Counterfactual scores
    AuditWorker->>AuditWorker: Calculate influence: baseline minus aggregate counterfactual score
    AuditWorker->>AuditWorker: Apply deterministic classification + saturation rules
    AuditWorker->>AuditStore: Persist SUCCEEDED audit, results, and complete lineage
    AuditWorker->>AuditWorker: Skip generic Replay evaluation and drift comparison
```

## 4. Inspect Result & Follow Lineage

Studio renders persisted state. It does not recalculate Evidence Influence in
the browser. A controlled Replay links back to the exact Causal Audit, where
the policy version, intervention digest, counterfactual execution, and
evaluator score can be inspected together.

```mermaid
%%{init: {"theme":"base","themeVariables":{"background":"#ffffff","primaryColor":"#f8fafc","primaryTextColor":"#111827","primaryBorderColor":"#94a3b8","lineColor":"#64748b","secondaryColor":"#eff6ff","tertiaryColor":"#f8fafc","actorBkg":"#ffffff","actorBorder":"#64748b","actorTextColor":"#111827","signalColor":"#334155","signalTextColor":"#111827","noteBkgColor":"#f8fafc","noteBorderColor":"#93c5fd","noteTextColor":"#111827","activationBkgColor":"#dbeafe","activationBorderColor":"#2563eb"}}}%%
sequenceDiagram
    autonumber
    actor Reviewer
    participant Studio as Studio Causal Audit
    participant AuditAPI as Causal Audit REST API
    participant AuditStore as Causal Audit Repository
    participant ReplayAPI as Replay REST API
    participant ReplayStore as Replay Repository

    Reviewer->>Studio: Select audit or choose Explain
    Studio->>AuditAPI: Get causal audit by audit ID
    AuditAPI->>AuditStore: Read immutable audit in tenant scope
    AuditStore-->>Studio: Classification reason + per-call score chains
    Studio->>Studio: Inspect original score, counterfactual score, and influence

    Reviewer->>Studio: Expand controlled Replay lineage
    Studio->>ReplayAPI: Get controlled Replay by replay ID
    ReplayAPI->>ReplayStore: Read controlled Replay in tenant scope
    ReplayStore-->>Studio: Frozen source + counterfactual execution + status

    Reviewer->>Studio: Open Controlled Causal Replay
    Studio->>Studio: Show Overview, Configuration, Execution, Lineage, and Audit only
    Studio->>Studio: Hide generic Evaluation and Comparison
```

## 5. Partial Evidence or Execution Failure

There is no best-effort influence. If policy validation, evidence resolution,
counterfactual generation, isolated execution, or scoring fails for a required
sample, the audit becomes `FAILED` and persists diagnostics without a
classification or influence record.

```mermaid
sequenceDiagram
    autonumber

    participant AuditWorker as Causal Audit Worker
    participant AuditRepo as Causal Audit Repository
    participant PolicyRepo as Policy Repository
    participant Resolver as Runtime Evidence Resolver
    participant Provider as Intervention Provider
    participant ReplayService as Replay Application Service
    participant ReplayRepo as Replay Repository
    participant Adapter as Controlled Replay Adapter
    participant Scorer as Outcome Scorer

    AuditWorker->>AuditRepo: Claim QUEUED audit
    AuditRepo-->>AuditWorker: Immutable audit inputs

    AuditWorker->>PolicyRepo: Resolve exact ACTIVE policy version

    alt Policy missing, inactive, stale, or invalid
        PolicyRepo-->>AuditWorker: Policy validation failure
        AuditWorker->>AuditRepo: Persist FAILED + diagnostics
        Note over AuditWorker,ReplayRepo: No Replay created
    else Policy valid
        PolicyRepo-->>AuditWorker: Valid immutable policy

        AuditWorker->>Resolver: Resolve required evidence

        alt Evidence cannot be resolved or verified
            Resolver-->>AuditWorker: Resolution failure
            AuditWorker->>AuditRepo: Persist FAILED + diagnostics
            Note over AuditWorker,ReplayRepo: No influence or classification persisted
        else Evidence resolved
            Resolver-->>AuditWorker: Evidence reference + digest

            AuditWorker->>Provider: Generate controlled evidence

            alt Intervention fails schema or policy constraints
                Provider-->>AuditWorker: Intervention failure
                AuditWorker->>AuditRepo: Persist FAILED + diagnostics
                Note over AuditWorker,ReplayRepo: No influence or classification persisted
            else Controlled evidence valid
                Provider-->>AuditWorker: Controlled evidence<br/>+ intervention digest

                AuditWorker->>ReplayService: Create controlled Replay
                ReplayService->>ReplayRepo: Persist policy and intervention lineage
                ReplayRepo-->>ReplayService: Replay ID

                AuditWorker->>Adapter: Execute isolated controlled Replay

                alt Runtime execution fails
                    Adapter-->>AuditWorker: Execution failure
                    AuditWorker->>ReplayRepo: Persist Replay FAILED
                    AuditWorker->>AuditRepo: Persist audit FAILED + diagnostics
                    Note over AuditWorker,AuditRepo: Partial samples are not aggregated
                else Runtime execution succeeds
                    Adapter-->>AuditWorker: Counterfactual execution<br/>+ outcome artifact

                    AuditWorker->>Scorer: Score counterfactual outcome

                    alt Scoring fails
                        Scorer-->>AuditWorker: Evaluation failure
                        AuditWorker->>AuditRepo: Persist FAILED + diagnostics
                        Note over AuditWorker,AuditRepo: No influence or classification persisted
                    else Scoring succeeds
                        Scorer-->>AuditWorker: Counterfactual score
                        AuditWorker->>AuditRepo: Continue only when every<br/>required sample has succeeded
                    end
                end
            end
        end
    end
```

## Lineage Invariant

Evidence Influence is persisted only when every required value below is
available and tenant-scoped:

```text
active policy id + immutable version
  -> intervention digest
  -> original and counterfactual evidence references + digests
  -> successful controlled Replay id + counterfactual execution id
  -> evaluator score
  -> aggregate Evidence Influence
  -> deterministic classification and explanation
```

An incomplete chain is an audit failure, not a reduced-confidence result.
