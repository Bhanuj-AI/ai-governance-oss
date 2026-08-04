---
name: domain-feature
description: Add or change a deterministic Kavach domain entity, value object, lifecycle transition, validation rule, domain error, or domain-level invariant. Use when work belongs in src/kavach/domain or a domain-focused package and must remain independent of transport, persistence, workers, and provider SDKs.
---

# Domain Feature

Model the business rule before choosing a route, database schema, worker, or
provider integration.

## Workflow

1. Read root `AGENTS.md` and `src/kavach/domain/AGENTS.md`. Read the scoped
   instruction file for any other layer that will consume the model.
2. Identify the durable concepts, their valid states, and invalid transitions.
   Prefer named types over an unstructured dictionary for stored or public
   contracts.
3. Implement validation in the value object or entity constructor and make
   invalid transitions fail explicitly.
4. Keep the model deterministic and free of I/O. Do not import FastAPI,
   database drivers, HTTP clients, worker code, environment configuration,
   concrete repositories, or provider SDKs.
5. Add a focused unit test for every new invariant and transition. Use a
   service test only when the rule requires application orchestration.
6. Adapt the new type at the service and transport boundaries rather than
   leaking persistence representation into the domain.

## Invariant pattern

Place the rule beside the data it protects. The existing dataset test shows the
desired shape: construct the named model and assert the invariant directly.

```python
def test_dataset_requires_non_negative_record_count() -> None:
    with pytest.raises(ValueError):
        Dataset(
            dataset_id="dataset-1",
            name="support-faq",
            version="2026-06-26",
            description="Evaluation baseline",
            storage_uri="s3://datasets/support-faq/2026-06-26.parquet",
            storage_type="S3",
            schema_version="v1",
            record_count=-1,
            checksum="sha256:abc123",
            creator="dataset-owner",
            created_at=datetime(2026, 6, 26, tzinfo=UTC),
            status=DatasetStatus.DRAFT,
        )
```

Keep lifecycle methods narrow: validate the current state, construct the next
valid state, and return or persist it through the owning application service.

## Done when

- Every new invariant has an isolated test.
- The domain package has no infrastructure imports.
- A transition cannot silently enter an invalid state.
- The model does not expose a database row, API payload, or provider object as
  its public representation.

## Verify

Use the nearest unit test. The following current command validates a domain
invariant end to end:

```bash
uv run ruff check src/kavach/domain
uv run pytest tests/unit/test_dataset_domain.py
```

Also run the focused service test whenever the new domain rule changes a
use-case outcome.
