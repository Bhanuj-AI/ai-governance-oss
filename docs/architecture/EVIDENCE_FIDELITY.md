# Evidence Fidelity & Replay Information Loss

## Answer

The authoritative Agents Runtime source is the tenant-scoped `AgentExecution`
aggregate and its immutable, append-only `AgentExecutionEvent` records.
Replay source discovery is a search projection only. The controlled runtime
Replay bridge reads the original ordered events and creates a safe,
reference-only `WorkflowExecution` source.

**Replay reads ordered Agent Runtime trajectories. The ontology projection
preserves operational relationships but cannot independently support certain
behavioural or causal conclusions.**

The current runtime ontology projection is not a trajectory, trace, or span
store. It
projects model, tool, governance, evaluation, and resource relationships into
Neo4j. It does not retain event order, causation, evidence references, retry
history, error detail, token usage, score, or tool response provenance. It is
therefore unsuitable as the sole source for a trajectory-grade replay or
causal conclusion.

## Release scope and outstanding tool-runner work

Evidence Fidelity is release-ready for trajectory fidelity and fail-closed
analysis. A live two-sample Inspect run proved that Inspect results become
durable Agent Runtime trajectories and remain queryable after an API, worker,
and SQLite restart. The controlled recovery scenarios proved that the runtime
projection loses ordering, recovery, and causal information.

The tool-enabled Inspect path is not yet production-ready. Its live runs
failed or exceeded the configured timeout, so they do not prove that real
Inspect tool trajectories show the same information loss. The controlled
scenarios verify projection semantics; they are not observations of model
behaviour.

The precise conclusion is:

> Controlled trajectory evidence demonstrated that the runtime projection loses
> ordering, recovery and causal information. A live Inspect run proved the
> durable lineage path, but live tool-enabled behavioural validation remains
> outstanding.

The implementation addresses the three release conditions. A fresh live,
tool-enabled run is still required before making a production-ready claim.

1. **Hard cancellation boundary.** A provider's declared
   `timeout_seconds` is now enforced around the whole provider invocation by
   the worker. If a bounded call cannot be guarded by the worker main process,
   it fails closed instead of silently becoming unbounded. A timed-out run is
   recorded as failed with the deadline reason; it does not keep the job worker
   occupied indefinitely.
2. **Model capability validation.** A tool-using Inspect configuration must
   declare `requires_tools: true`. The known unsupported OpenAI GPT-5 + Inspect
   Chat Completions tool combination is rejected during installation validation
   and again before an asynchronous job is created. It therefore cannot spend
   time or money after dispatch merely to discover that incompatibility.
3. **Operational cancellation authority.** `POST /api/v1/jobs/{job_id}/cancel`
   already requires `job.cancel`; the built-in `PLATFORM_OPERATOR` role includes
   that permission. Assign that role to the designated emergency-operator identity
   in the required organization/project, then verify the deployed identity
   before running tools:

   ```bash
   curl --fail-with-body "$API/api/v1/context" | jq '.permissions | index("job.cancel")'
   # Expected output: a number (not null)
   ```

   An organization administrator can make the assignment through the existing
   role-assignment endpoint:

   ```bash
   curl --fail-with-body -X POST "$API/api/v1/organizations/$ORG_ID/role-assignments" \
     -H 'Content-Type: application/json' \
     -d '{"actor_id":"inspect-emergency-operator","role":"PLATFORM_OPERATOR","project_id":"'"$PROJECT_ID"'"}'
   ```

   Replace `inspect-emergency-operator` with the actual human or service
   identity. Do not share that identity with the normal worker unless its
   operational controls justify cancellation authority.

## Explanation

Imagine a robot solving a treasure hunt.

The robot leaves behind two records:

- **Trajectory = the robot's diary:** “I saw the map, opened box A, failed,
  tried box B, then found the treasure.”
- **Projection = the final report:** “The robot opened two boxes and found
  the treasure.”

The report preserves the outcome, but it cannot explain the robot's behaviour.

### What we proved

1. **A prompt variant is not automatically a planner–executor scaffold.**

   The original integration smoke run made one model call with an added
   instruction to plan internally. Across 20 attempts, direct generation used
   400 input + 80 output = **480 tokens**; the planning-instruction variant
   used 860 input + 239 output = **1,099 tokens** (2.29×). This proves that an
   instruction changes usage, not planner–executor overhead. The fixture is
   named `planning_instruction_generate` to make that boundary clear.

2. **A genuine planner–executor scaffold changes the measured result.**

   A controlled run used ten multi-step exact-answer tasks, the same model,
   scorer, limits, and two repetitions per candidate. Direct generation made
   one call per sample; `planner_executor_generate` made one structured-plan
   call and one answer call. The plan content was used by the answer call but
   persisted only as a versioned digest.

   | Candidate | Exact passes | Calls | Total tokens | Model latency |
   | --- | ---: | ---: | ---: | ---: |
   | Direct generation (20 samples) | 18 / 20 | 20 | 2,129 | 33.79 s |
   | Planner–executor (20 samples) | 19 / 20 | 40 | 9,143 | 59.57 s |

   Every baseline sample had one call, every planner–executor sample had two,
   and the sum of per-call usage equalled the reported sample total. Under
   these fixed conditions, the genuine scaffold changed accuracy from 90% to
   95%, token consumption by **4.29×**, and model latency by **1.76×**. This is
   a small controlled result, not a claim about all agent workloads.

3. **AI Governance Platform preserves the robot's diary.**

   Replay reads ordered Agent Runtime events, including actions, evidence,
   failures, and recovery order. Therefore, Replay is trajectory-grade.

4. **The ontology projection is only a summary.**

   It preserved:

   - final outcome;
   - duration;
   - operational relationships.

   But it lost:

   - exact ordering;
   - retry and recovery sequence;
   - token and score evidence;
   - evidence-before-action relationships;
   - enough information for causal conclusions.

   Therefore, platform correctly returned `INSUFFICIENT_EVIDENCE`. It refused
   to invent an explanation merely because it knew the final result.

### Impact on current agent frameworks

Many agent frameworks are excellent at **running agents**. They provide
planning, tools, memory, loops, and retries.

Some also produce traces, but a trace can tell you, “These operations
happened,” without reliably telling you, “This evidence caused this decision,
this failure triggered this retry, and this recovery produced the outcome.”

Frameworks can retain rich histories, but their schemas and completeness
guarantees vary. Ingesting LangGraph, CrewAI, AutoGen, or another framework's
spans does **not automatically provide governance-grade behavioural evidence**.

The rule is:

> If a framework supplies only traces, platform must limit its conclusions. If
> it supplies ordered trajectory events, platform can support stronger replay
> and causal analysis.

### Impact on BHANUJ - AI Governance Platform

Platform provides three valuable controls:

- **Reproducible evaluation:** identifies the exact model, scaffold, runner,
  task set, and limits behind a result.
- **Trajectory-grade replay:** preserves the ordered evidence needed to
  understand behaviour.
- **Honest uncertainty:** refuses causal claims when only a lossy projection
  is available.

That is the commercial and architectural value: other systems may tell an
enterprise that an agent succeeded or failed; platform can determine whether
enough evidence exists to explain **how and why**—and admit when it cannot.

## How the pieces fit together

Think of an evaluation as a short story about what happened while a model was
tested. Evidence Fidelity keeps the ordered version of that story, then checks
what is still visible after the story is reduced to graph relationships.

```text
evaluation provider runs a sample
        |
        | sends safe, ordered observable events
        v
Agent Runtime stores the execution and its events
        |
        +--> Replay reads the ordered events
        |
        +--> runtime ontology stores a smaller relationship view
                         |
                         v
              Evidence Fidelity says what that smaller view can,
              and cannot, prove
```

Inspect AI is one provider that can send these events. It is not special to
Evidence Fidelity: another provider can join by sending the same generic
artifact. The feature does not need an Inspect-only switch or a separate
Evidence Fidelity setting in an installation.

For a provider integration, the hand-off is deliberately small:

1. Run the provider's evaluation sample.
2. Return an `EvaluationArtifact` named `observable_execution_events` with
   safe, ordered events.
3. The experiment service saves the sample result and creates the matching
   Agent Runtime execution.
4. Evidence Fidelity reads that stored execution later. It does not call the
   provider again and does not need to know which provider made the events.

The provider configuration still controls provider concerns such as the model,
task, solver, and time limits. It does not turn Evidence Fidelity on or off.
If a provider has no ordered events to share, the system records that honestly:
some conclusions will be `INSUFFICIENT_EVIDENCE` instead of guessed.

## What is stored

No `ExecutionTrajectory` aggregate exists. A full observable trajectory is a
deterministic view over existing Agent Runtime events. This avoids a second
owner for the same runtime facts.

`EvidenceFidelityComparison` is the only new durable record. It is
tenant-scoped and immutable, and stores:

- canonical source artifact digest and deterministic fingerprints for both
  views (the full trajectory and the runtime projection);
- retained and missing observable evidence types;
- preservation booleans for outcome, score, tokens, duration, action count,
  ordering, termination, recovery, failure classification, and causal
  completeness;
- explicit `INSUFFICIENT_EVIDENCE` conclusions where a view cannot support a
  claim.

It never stores prompts, model responses, tool inputs or results, credentials,
or hidden reasoning.

## Inspect evidence ingestion

New Inspect batch samples retain a safe, durable
`observable_execution_events` artifact inside the existing evaluation
result persistence boundary. It contains only event kind/order, safe identity,
timing, and SHA-256 digests of any tool arguments or responses. The worker
also creates a corresponding Agent Runtime execution and ordered events.

The artifact reference is stable:

```text
evaluation-artifact:{evaluation_id}:observable-events
```

An Inspect log on a worker-local path remains visible as a provider run
reference, but is marked `durable: false` and
`retrievable_after_worker_restart: false`. It is not accepted as durable
provenance. Remote `s3://`, `https://`, and `http://` references are marked
durable only at the reference layer; access policy remains the provider's
responsibility.

Existing Part 1 runs created before this feature do not acquire invented
events. Run the experiment once after deployment to create queryable sample
execution evidence.

### Where the Inspect connection lives

The Inspect adapter creates the generic artifact in
`src/ai_governance/providers/inspect_ai/adapter.py`. The shared experiment
service receives it in `src/ai_governance/services/experiment_api_service.py`
and records the Agent Runtime execution. Evidence Fidelity then reads only the
Agent Runtime execution and events; its service does not import Inspect AI.

This separation is important: Inspect AI supplies facts about an evaluation,
while Evidence Fidelity checks what the saved facts can support. Other
evaluation providers use the same hand-off without copying Inspect-specific
types into the experiment or fidelity domains.

## Recorded local release-gate evidence

The following records were captured from the local Docker release-gate run on
2026-09-08. They are useful examples of real REST responses and of the IDs
that connect an experiment sample to its Agent Runtime execution.

They are **not** included in the reusable demo seed. The two rich cases were
created as explicitly labelled `controlled_demo` records through the local
API. They live in the local database used for that release-gate run. A fresh
database, or a database reset, will not contain these IDs. This distinction
prevents example data from being mistaken for provider-run evidence.

| Record | Agent Runtime execution ID | Comparison ID | What it demonstrates |
| --- | --- | --- | --- |
| Inspect smoke sample 1 | `f19a42b9-f6f6-4a2e-8251-b8fb6dc546fe` | `a889883c-5b55-4935-a81a-01c8a243d5bd` | Live Inspect → durable Agent Runtime → comparison |
| Inspect smoke sample 2 | `6874344f-3b47-4ea3-aa3b-7f005f70829a` | `1cab69e8-9907-429c-b472-68a6b43896e6` | A second persisted Inspect sample |
| Controlled lookup/recovery | `1338a511-d140-431f-b8c6-a5391e30aa7a` | `74fd33c9-d9ff-4e32-87e8-29ec44b2e9d4` | Ordering, timeout, and retry/recovery loss |
| Controlled multi-action recovery | `38fc21ff-c79e-4af5-8741-f73a95433031` | `b340dfc2-8d37-4475-8a5a-ed1ea9891154` | Ordering and causal-evidence loss across several actions |

The live Inspect run was job
`1141af60-31a1-43d2-845f-546330bb470c`, experiment
`fdad16d0-ae99-4242-b679-e8025b37c9ba`, and evaluation run
`cf47b708-1c0a-4655-acac-0f0ae801d7bf`. It completed two samples. The
API and worker were restarted before the recorded comparisons were read back.

These commands use the same headers as the local authenticated API. They only
read a saved comparison; they do not run a model or create new evidence.

```bash
curl -sS \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "X-AI-Governance-Organization-Id: org_default" \
  -H "X-AI-Governance-Project-Id: project_default" \
  "$API/api/v1/agents-runtime/evidence-fidelity/comparisons/74fd33c9-d9ff-4e32-87e8-29ec44b2e9d4"
```

The captured response was:

```json
{
  "comparison_id": "74fd33c9-d9ff-4e32-87e8-29ec44b2e9d4",
  "source_execution_id": "1338a511-d140-431f-b8c6-a5391e30aa7a",
  "request_fingerprint": "1974df9218894b215ba3e9638b50a6a4da134d3f75aeb3e8ee74ddbaa39e4b6d",
  "created_at": "2026-09-08T12:36:26.603317Z",
  "status": "SUCCEEDED",
  "trajectory": {
    "source_execution_id": "1338a511-d140-431f-b8c6-a5391e30aa7a",
    "source_artifact_digest": "7c021df8e3501d4ce2011420bfa76e9c4a3cd3a4735854439176ed7aa5b3e05d",
    "projection_type": "full_observable_trajectory",
    "projection_version": "1",
    "projection_fingerprint": "fca2c38179b619997efdd13b179e9b78519534744d23a87b889b367ab7d805e7",
    "retained_evidence_types": [
      "actor_identity", "error_timeout", "execution_identity", "observation_evidence",
      "ordered_events", "retry_recovery", "runner_model_scaffold_provenance",
      "sample_identity", "schema_version", "score", "source_artifact_digest",
      "termination", "timestamps_duration", "token_usage", "tool_action",
      "tool_arguments_reference", "tool_response_reference"
    ],
    "missing_evidence_types": [],
    "completeness": "COMPLETE",
    "event_count": 6
  },
  "runtime_projection": {
    "source_execution_id": "1338a511-d140-431f-b8c6-a5391e30aa7a",
    "source_artifact_digest": "7c021df8e3501d4ce2011420bfa76e9c4a3cd3a4735854439176ed7aa5b3e05d",
    "projection_type": "runtime_ontology_projection",
    "projection_version": "1",
    "projection_fingerprint": "b1ab99163c2d12f16127191c6700794371f62059e84e806c4da2ab259265f3f3",
    "retained_evidence_types": [
      "actor_identity", "execution_identity", "runner_model_scaffold_provenance",
      "termination", "timestamps_duration", "tool_action"
    ],
    "missing_evidence_types": [
      "error_timeout", "observation_evidence", "ordered_events", "retry_recovery",
      "sample_identity", "schema_version", "score", "source_artifact_digest",
      "token_usage", "tool_arguments_reference", "tool_response_reference"
    ],
    "completeness": "INCOMPLETE",
    "event_count": 3
  },
  "outcome_preserved": true,
  "score_preserved": false,
  "token_usage_preserved": false,
  "duration_preserved": true,
  "action_count_preserved": true,
  "ordering_preserved": false,
  "termination_reason_preserved": true,
  "recovery_sequence_preserved": false,
  "failure_classification_preserved": false,
  "causal_evidence_complete": false,
  "trajectory_classification": "SUPPORTED",
  "runtime_projection_classification": "INSUFFICIENT_EVIDENCE",
  "retained_evidence_types": [
    "actor_identity", "execution_identity", "runner_model_scaffold_provenance",
    "termination", "timestamps_duration", "tool_action"
  ],
  "missing_evidence_types": [
    "error_timeout", "observation_evidence", "ordered_events", "retry_recovery",
    "sample_identity", "schema_version", "score", "source_artifact_digest",
    "token_usage", "tool_arguments_reference", "tool_response_reference"
  ],
  "unsupported_conclusions": [
    "score",
    "token_usage",
    "event_ordering",
    "evidence_before_action",
    "retry_recovery",
    "failure_classification",
    "causal_evidence"
  ],
  "failure_code": null,
  "failure_reason": null,
  "provenance": {
    "analysis_version": "evidence-fidelity/v1",
    "runtime_projection": "runtime_ontology_projection",
    "trajectory_projection": "full_observable_trajectory"
  }
}
```

The second rich scenario returned the same important conclusion after restart:

```bash
curl -sS \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "X-AI-Governance-Organization-Id: org_default" \
  -H "X-AI-Governance-Project-Id: project_default" \
  "$API/api/v1/agents-runtime/evidence-fidelity/comparisons/b340dfc2-8d37-4475-8a5a-ed1ea9891154"
```

```json
{
  "comparison_id": "b340dfc2-8d37-4475-8a5a-ed1ea9891154",
  "source_execution_id": "38fc21ff-c79e-4af5-8741-f73a95433031",
  "request_fingerprint": "a77736b5abe7c70acf898858546cdb8117221d902165e43e6bebb207cec1671a",
  "created_at": "2026-09-08T12:37:14.716010Z",
  "status": "SUCCEEDED",
  "trajectory": {
    "source_execution_id": "38fc21ff-c79e-4af5-8741-f73a95433031",
    "source_artifact_digest": "6722daa2f247c89ee4d4e92bf0e26b16c96dcc25fd30cf77cd92bbaca9436180",
    "projection_type": "full_observable_trajectory",
    "projection_version": "1",
    "projection_fingerprint": "7ed920d998bd0863ea6e54e6e4548f72141949cda716a02b1a06c071c18ee31b",
    "retained_evidence_types": [
      "actor_identity", "error_timeout", "execution_identity", "observation_evidence",
      "ordered_events", "retry_recovery", "runner_model_scaffold_provenance",
      "sample_identity", "schema_version", "score", "source_artifact_digest",
      "termination", "timestamps_duration", "token_usage", "tool_action",
      "tool_arguments_reference", "tool_response_reference"
    ],
    "missing_evidence_types": [],
    "completeness": "COMPLETE",
    "event_count": 7
  },
  "runtime_projection": {
    "source_execution_id": "38fc21ff-c79e-4af5-8741-f73a95433031",
    "source_artifact_digest": "6722daa2f247c89ee4d4e92bf0e26b16c96dcc25fd30cf77cd92bbaca9436180",
    "projection_type": "runtime_ontology_projection",
    "projection_version": "1",
    "projection_fingerprint": "e40da9d6f34aa520691134abbdace24a2f94798d017864496911e51743ad5587",
    "retained_evidence_types": [
      "actor_identity", "execution_identity", "runner_model_scaffold_provenance",
      "termination", "timestamps_duration", "tool_action"
    ],
    "missing_evidence_types": [
      "error_timeout", "observation_evidence", "ordered_events", "retry_recovery",
      "sample_identity", "schema_version", "score", "source_artifact_digest",
      "token_usage", "tool_arguments_reference", "tool_response_reference"
    ],
    "completeness": "INCOMPLETE",
    "event_count": 4
  },
  "outcome_preserved": true,
  "score_preserved": false,
  "token_usage_preserved": false,
  "duration_preserved": true,
  "action_count_preserved": true,
  "ordering_preserved": false,
  "termination_reason_preserved": true,
  "recovery_sequence_preserved": false,
  "failure_classification_preserved": false,
  "causal_evidence_complete": false,
  "trajectory_classification": "SUPPORTED",
  "runtime_projection_classification": "INSUFFICIENT_EVIDENCE",
  "retained_evidence_types": [
    "actor_identity", "execution_identity", "runner_model_scaffold_provenance",
    "termination", "timestamps_duration", "tool_action"
  ],
  "missing_evidence_types": [
    "error_timeout", "observation_evidence", "ordered_events", "retry_recovery",
    "sample_identity", "schema_version", "score", "source_artifact_digest",
    "token_usage", "tool_arguments_reference", "tool_response_reference"
  ],
  "unsupported_conclusions": [
    "score", "token_usage", "event_ordering", "evidence_before_action",
    "retry_recovery", "failure_classification", "causal_evidence"
  ],
  "failure_code": null,
  "failure_reason": null,
  "provenance": {
    "analysis_version": "evidence-fidelity/v1",
    "runtime_projection": "runtime_ontology_projection",
    "trajectory_projection": "full_observable_trajectory"
  }
}
```

The JSON blocks above are the complete captured comparison responses. Query the
same IDs in the release-gate database, or use the same command with an ID from
your own environment, to inspect a record.

## Controlled task

The packaged fixture is:

```text
ai_governance.inspect_tasks:trajectory_fidelity_smoke
```

Use its `ai_governance.inspect_tasks:controlled_trajectory_solver`. It offers
deterministic local lookup tools and a controlled failure/recovery route, so
the runner can emit real tool and error events without external paid tooling.
It is an evidence fixture, not a benchmark.

Some tool-capable models require a Responses API transport or special
reasoning settings. Use a model/transport combination that Inspect supports
for function tools. A provider rejection is a runner failure, not behavioural
evidence.

## API flow

After an updated Inspect experiment has completed, first find the sample's
Agent Runtime execution (the evaluation result metadata and execution metadata
link it to the evaluation run), then request a comparison:

```bash
curl -X POST "$API/api/v1/agents-runtime/evidence-fidelity/comparisons" \
  -H "Content-Type: application/json" \
  -H "X-Organization-Id: org_default" \
  -H "X-Project-Id: project_default" \
  -d '{"execution_id":"<agent-runtime-execution-id>"}'
```

The response is immediately immutable and includes `status`, both projection
provenance records, retained/missing fields, and unsupported conclusions.
Repeat the identical request to receive the existing record. Retrieve it with:

```bash
curl "$API/api/v1/agents-runtime/evidence-fidelity/comparisons/<comparison-id>" \
  -H "X-Organization-Id: org_default" \
  -H "X-Project-Id: project_default"
```

To list the evidence chain for an execution:

```bash
curl "$API/api/v1/agents-runtime/evidence-fidelity/executions/<execution-id>/comparisons" \
  -H "X-Organization-Id: org_default" \
  -H "X-Project-Id: project_default"
```

Use an optional `expected_source_digest` (64 hex characters) in the POST body
when a caller needs to pin a review to an exact source artifact. A mismatch is
persisted with `SOURCE_DIGEST_MISMATCH`; an order gap, missing terminal event,
or unsupported event schema similarly produces explicit fail-closed status.

## Interpretation

For the current production graph projection, final execution outcome and
duration survive. Tool action count may survive as an aggregate relationship
count. Score, token usage, ordering, evidence-before-action, retry/recovery,
failure classification, and causal evidence provenance do not survive. Their
runtime-projection conclusion is `INSUFFICIENT_EVIDENCE`, never an inferred
result.

## Controlled demo evidence

For local release-gate work, two explicitly labelled `controlled_demo` Agent
Runtime scenarios cover lookup/action and ordered multi-action
failure/recovery. They are useful to verify the durable REST ingestion,
projection, comparison, restart, and retrieval path without a paid model.
They are not Inspect executions and must never be presented as provider-run
evidence. A live Inspect run remains required to validate a specific
model/transport/tool combination.
