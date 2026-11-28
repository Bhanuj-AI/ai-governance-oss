## Summary

Describe what this pull request changes and why.

## Type of Change

- [ ] Bug fix
- [ ] Feature
- [ ] API change
- [ ] SPI or plugin contract change
- [ ] Documentation
- [ ] Refactor
- [ ] Test coverage
- [ ] Maintenance

## Areas Affected

- [ ] Execution audit
- [ ] Agent Runtime
- [ ] Workflow replay
- [ ] Causal Audit or intervention policies
- [ ] Authorization or tenant isolation
- [ ] Evaluation framework
- [ ] Persistence or repositories
- [ ] Governance APIs
- [ ] MCP or CLI
- [ ] Plugins or SPI
- [ ] Studio
- [ ] Leaderboard APIs
- [ ] Prompt registry
- [ ] Model registry
- [ ] Dataset registry
- [ ] Experiment management
- [ ] Documentation
- [ ] Project infrastructure

## Validation

- [ ] `uv run ruff check .`
- [ ] `uv run pytest`
- [ ] Added or updated tests, if behavior changed
- [ ] Updated docs, if public behavior changed

List commands run and their results, including focused or integration tests.
Explain any relevant checks not run and why.

## Compatibility Notes

Describe affected REST, MCP, CLI, SPI, event, configuration, and persisted
artifact contracts, including migrations or rollout requirements where relevant.
State whether existing consumers and historical records remain compatible.

## Governance Notes

Describe relevant effects on tenant isolation, authorization, evidence privacy
and history, replay semantics and failure behavior, evaluation, ranking,
promotion recommendations, or governed asset lifecycle rules.

## Checklist

- [ ] Public APIs and docs use consistent terminology.
- [ ] Security-sensitive details are not included in logs, fixtures, or examples.
