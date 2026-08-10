# Testing Strategy

## Overview

AI Governance Control Plane adopts a layered testing strategy that aligns with the architecture of the platform. Each layer validates a single responsibility, allowing failures to be isolated quickly while keeping the test suite fast, deterministic, and easy to maintain.

The guiding principles are:

* Test behaviour rather than implementation details.
* Validate every architectural boundary independently.
* Keep unit tests independent of infrastructure.
* Verify integration points with real implementations.
* Ensure all pluggable implementations satisfy the same contract.

---

# Testing Pyramid

```
                    End-to-End Tests
                           ▲
                           │
                  Integration Tests
                           ▲
                           │
                 Repository Tests
                           ▲
                           │
                    Mapper Tests
                           ▲
                           │
                     Unit Tests
```

Each layer increases confidence while reducing the amount of mocking required.

---

# Test Categories

```
tests/

├── unit/
│
├── integration/
│
├── repositories/
│   ├── contract/
│   ├── mappers/
│   ├── postgres/
│   └── sqlite/
│
└── providers/
```

---

# Unit Tests

## Purpose

Validate a single component in isolation.

Infrastructure such as databases, filesystems, or external services should never be involved.

Typical dependencies are replaced with lightweight in-memory implementations or fake providers.

## Examples

```
tests/unit/

test_evaluation_service.py
test_evaluation_worker.py
test_trulens_setup.py
```

### Example dependency graph

```
EvaluationWorker
        │
        ▼
EvaluationService
        │
        ▼
FakeEvaluationProvider

EvaluationRepository
        │
        ▼
InMemoryEvaluationRepository
```

Unit tests should execute in milliseconds.

---

# Mapper Tests

## Purpose

Verify serialization between domain objects and persistence records.

These tests validate:

* serialization
* deserialization
* grouping
* metadata preservation
* round-trip integrity

No database is involved.

## Examples

```
tests/repositories/mappers/

test_evaluation_persistence_mapper.py
```

Architecture

```
EvaluationResult
        │
        ▼
Persistence Mapper
        │
        ▼
Persistence Records
```

---

# Repository Tests

## Purpose

Validate persistence behaviour using a real storage engine.

Repository tests verify:

* save()
* retrieval
* updates
* idempotency
* schema correctness

The repository is tested independently from higher-level services.

## Examples

```
tests/repositories/sqlite/

test_sqlite_database.py
test_sqlite_evaluation_repository.py
```

Architecture

```
Repository
        │
        ▼
SQLite / PostgreSQL
```

PostgreSQL repository tests require `AI_GOVERNANCE_POSTGRES_DSN`. When the variable is
not set, those tests are skipped cleanly. Each PostgreSQL test creates and drops
a unique schema to avoid cross-test contamination.

---

# Repository Contract Tests

AI Governance Control Plane treats repositories as interchangeable implementations.

Every repository must satisfy the same behavioural contract.

Current implementations

```
SQLiteEvaluationRepository

PostgresEvaluationRepository
```

Future implementations

```
SnowflakeEvaluationRepository

DuckDBEvaluationRepository
```

Repository contract tests define expected behaviour once.

Each repository implementation inherits the same contract to ensure behavioural consistency.

Example

```
EvaluationRepositoryContract

        ▲
        │

SQLiteEvaluationRepository

PostgresEvaluationRepository

SnowflakeEvaluationRepository
```

This allows storage implementations to change without affecting application behaviour.

---

# Integration Tests

## Purpose

Validate collaboration between multiple architectural components.

Real infrastructure is used where appropriate.

Example

```
WorkflowExecution
        │
        ▼
EvaluationWorker
        │
        ▼
EvaluationService
        │
        ▼
FakeEvaluationProvider
        │
        ▼
SQLiteEvaluationRepository
        │
        ▼
SQLite Database
```

Examples

```
tests/integration/

test_trulens_provider.py

test_sqlite_evaluation_worker.py
```

Integration tests validate the complete workflow while remaining deterministic.

---

# End-to-End Tests

Future milestones will introduce end-to-end tests covering complete platform workflows.

Example

```
Workflow Execution

↓

Dataset Builder

↓

Evaluation Service

↓

Evaluation Provider

↓

Evaluation Repository

↓

History Retrieval

↓

Governance APIs
```

These tests validate complete user scenarios rather than individual components.

---

# In-Memory Implementations

In-memory implementations exist solely to support fast unit testing.

Examples

```
InMemoryExecutionRepository

InMemoryEvaluationRepository
```

They must implement the same repository contracts as production implementations.

---

# Fake Providers

Fake providers remove external dependencies from unit and integration tests.

Current examples

```
FakeEvaluationProvider
```

Future examples may include

```
FakeLLMProvider

FakeEmbeddingProvider

FakeStorageProvider
```

---

# Design Principles

The testing strategy follows the same architectural principles as the production code.

* Unit tests validate orchestration.
* Mapper tests validate serialization.
* Repository tests validate persistence.
* Integration tests validate collaboration.
* End-to-end tests validate complete workflows.

Each layer owns one responsibility.

No layer duplicates another.

---

# Future Evolution

As AI Governance Control Plane grows, new implementations should extend the existing architecture without changing the testing philosophy.

Examples include:

* PostgreSQL repositories
* Snowflake repositories
* Additional evaluation providers
* Governance APIs
* Replay framework
* Drift analysis
* Evaluation history

The existing test pyramid should naturally accommodate these additions while maintaining fast feedback and high confidence.

---

# Guiding Principle

> Test behaviour at architectural boundaries, not implementation details.

A component should only be tested once at the level where its responsibility is owned. This minimizes duplication, reduces maintenance effort, and ensures every architectural boundary is validated independently.
