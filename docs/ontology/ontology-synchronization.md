# Ontology Synchronization

## Overview

Ontology synchronization projects existing Kavach governance domain objects
into the `kavach.governance` ontology graph. Domain repositories and services
remain the systems of record; the graph is a deterministic semantic projection
used for lineage, provenance, and future traversal workflows.

The synchronization layer is one-way:

```text
Domain object -> Ontology synchronizer -> OntologyService -> Graph repository
```

Synchronizers never talk directly to Neo4j. All graph writes go through
`OntologyService`, which preserves relationship validation and idempotency.

## Package Layout

```text
src/kavach/ontology/synchronization/
  __init__.py
  audit_sync.py
  dataset_sync.py
  evaluation_sync.py
  experiment_sync.py
  governance_sync.py
  job_sync.py
  model_sync.py
  prompt_sync.py
  replay_sync.py
  synchronizer.py
```

## Synchronization Contract

Every synchronizer implements:

```python
class OntologySynchronizer:
    def synchronize(entity) -> SynchronizationResult: ...
    def delete(entity) -> SynchronizationResult: ...
    def resynchronize(entity_id: str) -> SynchronizationResult: ...
```

`synchronize` projects the current domain state. `delete` archives the ontology
projection without hard-deleting graph nodes. `resynchronize` reloads an object
through a configured repository loader when one is available.

`SynchronizationResult` includes synchronized entity IDs, synchronized
relationship IDs, archived entity IDs, errors, duration, failure count, 
retry count, and entity/relationship counters.

## Idempotency

Synchronization is repeatable:

- entity projections use stable domain IDs
- logical registry assets use deterministic IDs such as `prompt:{name}`
- relationships use deterministic IDs derived from source, relationship type and target
- repeated sync updates mutable ontology properties and does not duplicate relationships

## Synchronizers

Registry synchronizers:

- `PromptOntologySynchronizer`
- `ModelOntologySynchronizer`
- `DatasetOntologySynchronizer`

These create logical asset entities, version entities, actor provenance, and
version relationships: `HAS_VERSION`, `VERSION_OF`, `CREATED_BY`, `OWNED_BY`,
and `SUPERSEDES` when the source repository can determine prior versions.

Experiment synchronizers:

- `ExperimentOntologySynchronizer`
- `CandidateOntologySynchronizer`

These create experiments, candidates, provider nodes, ownership relationships,
experiment membership, and candidate `USES` links to prompt/model/dataset
versions. Candidate sync expects referenced asset versions to have already
been synchronized by their owning registry synchronizers.

Evaluation synchronizers:

- `EvaluationRunOntologySynchronizer`
- `EvaluationResultOntologySynchronizer`

These create evaluation runs, results, provider nodes, metric nodes, artifact
nodes, and evidence relationships including `EXECUTES`, `PRODUCES`,
`HAS_METRIC`, `HAS_ARTIFACT`, and `EVALUATED_BY`.

Operational synchronizers:

- `JobOntologySynchronizer`
- `MCPAuditOntologySynchronizer`
- `WorkflowExecutionOntologySynchronizer`
- `ReplayOntologySynchronizer`

These project jobs, MCP audit records, workflow executions, and replay
investigations. String result references such as `evaluation:eval-1` are linked
only when the target ontology entity already exists.

Governance synchronizers:

- `GovernanceDecisionOntologySynchronizer`
- `GovernanceInsightOntologySynchronizer`
- `GovernanceReportOntologySynchronizer`
- `DriftOntologySynchronizer`

Kavach has a first-class governance decision domain model in
`kavach.decisions`. The current synchronizer still accepts
`GovernanceDecisionProjection`, which remains the ontology-facing projection
shape until durable decision repositories and service workflows are introduced.
Projection code should preserve the domain contract: decisions are
evidence-backed, target ontology-aligned entities, carry producer provenance,
and express supersession without embedding evidence payloads.

## Reconciliation

`DiffBasedOntologyReconciler` is the primary reconciliation engine. It builds
the expected ontology projection from domain repositories, fingerprints the
semantic projection, loads the current graph snapshot, and repairs only
detected drift.

The reconciliation workflow is:

1. Build expected projection with `ProjectionBuilder`.
2. Compute `projection_hash` for semantic entity state.
3. Compute `relationship_set_hash` for the unordered relationship set.
4. Load the current graph projection snapshot.
5. Skip projections with matching stored hashes.
6. Update missing projection metadata when semantic state already matches.
7. Run the synchronizer only when entities or relationships have semantic
   drift.

Fingerprints ignore timestamps, synchronization metadata, and implementation
details. Relationship order does not affect `relationship_set_hash`.

Example:

```python
reconciler = DiffBasedOntologyReconciler(
    ontology_service,
    synchronizers=(
        DiffRepositorySynchronizer(
            synchronizer=PromptOntologySynchronizer(
                ontology_service,
                prompt_repository,
            ),
            list_entities=prompt_repository.find_all,
            primary_entity_resolver=lambda prompt: (
                "PromptVersion",
                prompt.prompt_id,
            ),
            projection_source="prompt_registry",
            scope_identifier="prompt_registry",
            entity_type="PromptVersion",
            entity_id_resolver=lambda prompt: prompt.prompt_id,
        ),
    ),
)

report = reconciler.reconcile_all()
```

`DiffReconciliationReport.metrics` exposes an operator-facing reconciliation
summary and the reconciler logs the same JSON-friendly payload at info level
after each run:

- `entities_scanned`
- `entities_skipped`
- `entities_repaired`
- `relationship_repairs`
- `repair_failures`
- `execution_duration_ms`
- `skip_ratio`

The metric payload is transport-neutral, so REST handlers, MCP tools,
schedulers, or CLI scripts can return the same fields without reinterpreting
low-level synchronization counters.

Supported scopes reuse the same comparison and repair logic:

- `reconcile_all()`
- `reconcile_entity_type(entity_type)`
- `reconcile_scope(scope_identifier)`
- `reconcile_entity(entity_type, entity_id)`

Successful diff reconciliation persists this metadata on the primary ontology
entity:

- `projection_hash`
- `relationship_set_hash`
- `projection_source`
- `projection_version`
- `last_synchronized_at`

Reconciliation is safe to run repeatedly. When domain state and graph state are
unchanged, the diff engine skips the projection and performs zero graph writes.

## Event-Driven Synchronization

Event-driven synchronization records ontology work as durable events and lets a
background worker process those events asynchronously. Domain services publish
events after authoritative state changes, but they remain unaware of Neo4j and
never write graph state directly.

```text
Domain service -> OntologySyncEventPublisher -> event repository
event repository -> OntologySynchronizationWorker -> DiffBasedOntologyReconciler
```

Core types:

- `OntologySyncEvent` captures the event ID, type, target entity or scope,
  correlation ID, payload, lifecycle status, retry metadata, and reconciliation
  report.
- `OntologySyncEventPublisher` records entity or scope events in the repository.
- `OntologySynchronizationWorker` leases due events, invokes
  `reconcile_entity()` or `reconcile_scope()`, stores report metrics, and marks
  events `COMPLETED`, `FAILED`, or `DEAD_LETTER`.
- `OntologySyncEventService` provides operational list/get/retry/cancel/metrics
  behavior for REST or MCP adapters.

Supported statuses are `PENDING`, `PROCESSING`, `COMPLETED`, `FAILED`,
`DEAD_LETTER`, and `CANCELLED`. Failed retryable events are rescheduled with
exponential backoff according to `OntologySyncRetryPolicy`; permanently failed
or exhausted events move to `DEAD_LETTER`.

The event store has in-memory and SQLite implementations. SQLite persists the
event lifecycle, retry metadata, lock metadata, payload, and reconciliation
report so events survive process restarts.

REST monitoring endpoints:

- `GET /api/v1/ontology/synchronization/events`
- `GET /api/v1/ontology/synchronization/events/{event_id}`
- `GET /api/v1/ontology/synchronization/events/{event_id}/status`
- `POST /api/v1/ontology/synchronization/events/{event_id}/retry`
- `POST /api/v1/ontology/synchronization/events/{event_id}/cancel`
- `GET /api/v1/ontology/synchronization/events/metrics`

Events can be filtered by status, entity type, entity ID, correlation ID, and
event type. Duplicate events are safe: reconciliation fingerprints determine
whether graph repair is necessary, so unchanged projections are skipped.

## Deletion Strategy

Synchronizers do not hard-delete ontology entities. `delete(entity)` marks the
projected entity lifecycle as `ARCHIVED`, records archival metadata, and
preserves historical relationships.

Physical cleanup remains an explicit orphan cleanup concern outside ontology
synchronization.

## Error Handling

Synchronizers return structured errors in `SynchronizationResult`. Failures:

- do not mutate domain repositories
- are logged by the base synchronizer
- can be retried with the same domain object
- can be repaired through reconciliation

## Running Tests

For local setup, persistence, operational recovery, and troubleshooting, see
the [Neo4j Operations Guide](./neo4j-operations-guide.md).

Run synchronization unit tests:

```bash
uv run pytest tests/unit/ontology_sync
```

Run synchronization plus foundation ontology tests:

```bash
uv run pytest tests/unit/ontology_sync tests/unit/ontology
```

Run opt-in Neo4j synchronization integration tests:

```bash
export KAVACH_RUN_NEO4J_TESTS=true
uv run pytest tests/integration/ontology_sync
```

Neo4j integration tests are skipped unless `KAVACH_RUN_NEO4J_TESTS=true` and
the Neo4j Python driver/server are available.

## Guardrails

- Domain services own business state.
- The ontology owns semantic projection and relationships.
- Synchronization is one-way from domain state to ontology state.
- All graph writes go through `OntologyService`.
- Synchronizers must be deterministic and idempotent.
- Missing relationship targets are skipped when the source only has a string
  reference; reconciliation can repair them after the target is synchronized.
