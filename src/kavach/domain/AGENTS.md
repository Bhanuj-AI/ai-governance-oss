# Scope

This directory owns framework-independent domain entities, value objects,
lifecycle rules, validation, and domain-specific errors.

## Dependency Boundaries

Domain code may depend on the Python standard library, other Kavach domain
modules, and stable shared primitives with no infrastructure dependency. It
must not depend on FastAPI, database drivers, HTTP clients, MCP SDKs, workers,
environment configuration, concrete repositories, or provider SDKs.

## Architectural Invariants

- Model durable concepts with named types rather than unstructured dictionaries
  when they cross persistence or public-contract boundaries.
- Domain transitions are deterministic. Invalid state or invalid transitions
  fail explicitly instead of being repaired by a caller.
- Domain objects do not perform I/O or open connections. Persistence and
  transport representations remain outside the public domain model.

## Validation

Add the closest focused unit coverage under `tests/unit/`; for example,
`tests/unit/test_dataset_domain.py` encodes dataset invariants.

For the task workflow, use `skills/domain-feature/SKILL.md`.
