# Vision

## The Governance Problem

Evaluation alone is not enough for production AI systems. A high score on one
run does not explain which governed configuration produced that score, whether
quality regressed over time, or whether a candidate should be recommended for
promotion.

AI systems change continuously:

- prompts evolve
- models are upgraded
- datasets change
- evaluation criteria shift

Those changes require a governance control plane, not only an evaluator.

## Governance Control Plane

Kavach exists to provide that control plane. It records governed assets,
collects evaluation evidence, reconstructs historical behavior, analyzes
quality change, ranks experiment candidates, and produces recommendations that
other systems can consume.

## What Kavach Owns

Kavach owns:

- AI asset governance for prompts, models, and datasets
- experiment management and candidate tracking
- evaluation history and comparison
- drift detection
- ranking and leaderboard generation
- framework-neutral governance and leaderboard APIs

## What Kavach Does Not Own

Kavach intentionally does not own:

- prompt deployment
- model deployment
- infrastructure management
- CI/CD execution
- application runtime orchestration

The platform should remain usable across those systems instead of becoming one
of them.

## Long-Term Positioning

Kavach is aimed at a durable governance layer for AI systems, with emphasis on:

- AI asset governance
- experiment management
- evaluation history
- drift detection
- deployment recommendations

The long-term value is not a single evaluator or storage engine. It is a stable
governance model that survives changes in providers, runtimes, and transport
frameworks.

## Recommendation Boundary

Kavach recommends and governs; downstream systems deploy.

That boundary is deliberate. Governance evidence should be portable across CLI
tools, the REST control plane, release systems, and human review flows without
forcing a particular deployment mechanism.

## Related Documents

- [Roadmap](./ROADMAP.md)
- [Architecture](../architecture/ARCHITECTURE.md)
- [Experiment Management](../architecture/EXPERIMENT_MANAGEMENT.md)
