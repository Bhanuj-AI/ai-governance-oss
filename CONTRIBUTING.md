# Contributing to Kavach

Thank you for your interest in contributing to Kavach.

Kavach is an AI governance and experiment management platform. Contributions are most useful when they preserve the project boundaries: Kavach records governed assets, evaluation evidence, replayable history, comparisons, drift analysis, rankings, and recommendations. Downstream systems remain responsible for deployment and runtime orchestration.

## Ways to Contribute

- Fix bugs in governance, replay, evaluation, registries, repositories, or APIs.
- Add focused tests for existing behavior.
- Improve documentation, examples, and terminology.
- Propose new evaluation providers, storage repositories, or adapters.
- Discuss governance semantics before implementing broad behavior changes.

## Development Setup

Kavach uses Python 3.12 or newer and `uv` for dependency management.

```bash
uv sync
```

Run the test suite:

```bash
uv run pytest
```

Run linting:

```bash
uv run ruff check .
```

## Contribution Workflow

1. Open or comment on an issue for non-trivial changes.
2. Keep pull requests focused on one behavior change or documentation topic.
3. Add or update tests when behavior changes.
4. Update public documentation when APIs, lifecycle rules, schemas, or workflows change.
5. Include compatibility notes for persistence, API, or governance semantics.
6. Before creating a commit or pull request, run the local preflight:

   ```bash
   ./scripts/dev/preflight.sh
   ```

   It collects a [Conventional Commit](https://www.conventionalcommits.org/en/v1.0.0/)
   message and release-note bullets, checks the working-tree patch, runs Python
   linting and unit tests, and type-checks Studio when console files changed.
   Resolve every reported failure before opening the pull request.

## Design Guidelines

- Prefer framework-neutral APIs and provider-neutral abstractions.
- Keep governance recommendations separate from deployment execution.
- Preserve immutable asset history for prompts, models, datasets, and experiments.
- Treat replay and evaluation history as evidence that must remain interpretable over time.
- Avoid coupling core governance behavior to a single storage engine, model provider, or orchestration framework.

## Testing Guidelines

Use focused tests for the behavior being changed. Broaden test coverage when touching shared contracts such as repositories, public APIs, lifecycle rules, comparison logic, ranking, or drift analysis.

When adding integrations, include unit tests for core behavior and isolate external service calls behind testable boundaries.

## Documentation Guidelines

Documentation should use stable project terminology:

- governed asset
- evaluation evidence
- workflow replay
- drift analysis
- recommendation
- lifecycle status
- experiment candidate
- leaderboard

Roadmap items should be described as direction rather than release commitments unless a release plan exists.

## Security and Sensitive Data

Do not include secrets, tokens, credentials, customer data, proprietary prompts, private datasets, or confidential evaluation results in issues, pull requests, tests, logs, or fixtures.

For suspected vulnerabilities, follow the process in [SECURITY.md](SECURITY.md).

## License

By contributing to Kavach, you agree that your contributions are licensed under the Apache License 2.0, unless explicitly stated otherwise by the maintainers.
