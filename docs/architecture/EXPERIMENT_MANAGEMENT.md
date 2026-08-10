# Experiment Management

## Why Experiments Exist

Evaluation results on their own answer whether one execution scored well.
Experiment management answers the harder governance question: which governed AI
configuration should be recommended for a business use case.

An experiment creates a controlled comparison space for multiple candidates that
share a problem definition while varying prompts, model versions, datasets, or
runtime parameters.

## Core Objects

### WorkflowExecution

`WorkflowExecution` is runtime evidence. It captures what happened during a
workflow execution.

### EvaluationResult

`EvaluationResult` is metric evidence for a single execution. It records scores,
metadata, and evaluator identity.

### EvaluationRun

`EvaluationRun` is experiment evidence. It links an experiment candidate to a
governed evaluation attempt and tracks status and timestamps.

### Experiment

`Experiment` is the orchestration aggregate. It defines the comparison space and
its lifecycle.

### ExperimentCandidate

`ExperimentCandidate` is an immutable AI configuration. It binds prompt, model,
dataset, evaluation provider, and runtime parameters into one governed unit.

### Leaderboard

`Leaderboard` is the final experiment-facing governance artifact. It captures a
snapshot of ranked candidates under a defined ranking strategy.

## Registry Inputs

Experiment management does not duplicate asset governance. It references:

- Prompt Registry for prompt versions
- Model Registry for model versions
- Dataset Registry for dataset versions

This keeps governance state centralized and avoids drift between experiment
records and asset registries.

## Experiment Lifecycle

The experiment lifecycle is:

```text
DRAFT -> RUNNING -> COMPLETED
              \-> FAILED

ARCHIVED is a terminal governance state.
```

A fuller view is:

```text
DRAFT
  |
  v
RUNNING
  | \
  |  v
  | FAILED
  v
COMPLETED
  |
  v
ARCHIVED
```

## Candidate as Immutable AI Configuration

A candidate exists so that a ranking decision can be tied to an exact
configuration. The candidate should be read as a versioned contract:

- prompt identity and version
- model identity and version
- dataset identity and version
- evaluation provider
- runtime settings
- metadata

Changing any of those values should produce a new candidate record rather than
mutating the old one.

## Evaluation Run as Immutable Execution Evidence

Evaluation runs are the experiment-level proof that a candidate was evaluated.
Only completed runs should participate in ranking and winner selection.

That distinction matters:

- a candidate record says what was intended
- an evaluation run says what actually happened

## Candidate Comparison

Candidate comparison explains what changed between candidates before ranking
answers which candidate is preferred. It is useful for reviews because it keeps
configuration change and quality change visible together.

The Studio Comparison tab exposes this workflow through two selectors:

- **Baseline Candidate** — the reference configuration and evaluation result.
- **Comparison Candidate** — the configuration and evaluation result being
  assessed against the baseline.

Comparison is disabled until two different candidates are selected. The
backend uses the latest completed evaluation run for each selected candidate;
pending, running, or failed runs do not participate. If either candidate has
no completed run, the comparison is unavailable rather than displaying
fabricated values.

The configuration comparison is field-based and displays the following values
side by side:

- prompt identity and version
- model identity and version
- dataset identity and version
- evaluation provider
- temperature, top-p, and max-tokens runtime parameters

Changed configuration rows use neutral theme-aware highlighting. Evaluation
metrics are returned by the backend and displayed with baseline, comparison,
and delta values. The frontend does not create missing metrics or infer
ambiguous metrics. Known directional metrics use semantic status colors:

- green indicates an improvement
- red indicates a regression
- neutral indicates no change, missing values, or an unknown metric direction

Higher quality scores are treated as better; cost, latency, and hallucination
score are treated as better when lower.

The REST contract is:

```http
GET /api/v1/experiments/{experiment_id}/comparison
  ?baseline_candidate_id={candidate_id}
  &comparison_candidate_id={candidate_id}
```

The endpoint rejects identical candidates, candidates from another experiment,
and comparisons without completed evaluation evidence.

## Winner Selection

Winner selection is a narrow decision over ranked candidates. It answers which
candidate wins according to a selection rule, such as highest overall score.

## Ranking Strategy

Ranking strategies allow the platform to optimize for different objectives
without rewriting experiment models. Current strategies include overall score,
groundedness, answer relevance, latency, cost, and hallucination-aware ranking.

## Leaderboard as Final Governance Artifact

The leaderboard is the artifact that downstream systems should consume when they
need an experiment recommendation. It is a snapshot, not a live computation.

```text
Experiment
    |
    v
Candidates
    |
    v
Evaluation Runs
    |
    v
Comparison
    |
    v
Ranking Strategy
    |
    v
Leaderboard
    |
    v
Recommendation
```

## Recommendation Is Not Deployment

A recommended candidate is not a deployed candidate. AI Governance Control Plane identifies the
highest-ranked candidate and records the reason. Another system may choose to
consume that recommendation as one input into promotion or release logic.

## Related Documents

- [Architecture](./ARCHITECTURE.md)
- [Design Principles](./DESIGN_PRINCIPLES.md)
- [Public API](../reference/PUBLIC_API.md)
