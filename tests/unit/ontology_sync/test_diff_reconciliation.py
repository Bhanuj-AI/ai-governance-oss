from datetime import UTC, datetime

from ai_governance.domain.prompts import Prompt, PromptStatus
from ai_governance.ontology import InMemoryOntologyGraphRepository, OntologyService
from ai_governance.ontology.synchronization import (
    DiffBasedOntologyReconciler,
    DiffReconciliationEntry,
    DiffReconciliationReport,
    DiffRepositorySynchronizer,
    PromptOntologySynchronizer,
    ProjectionBuilder,
    SynchronizationResult,
    SynchronizationStats,
)
from ai_governance.ontology.synchronization.projection import (
    fingerprint_relationships,
)
from ai_governance.ontology.synchronization.synchronizer import (
    stable_relationship_id,
)
from ai_governance.repositories.in_memory_prompt_repository import (
    InMemoryPromptRepository,
)


def test_projection_builder_does_not_write_to_graph() -> None:
    repository = InMemoryPromptRepository()
    prompt = _prompt("prompt-1", template="Hello")
    repository.save(prompt)
    service = OntologyService(InMemoryOntologyGraphRepository())
    synchronizer = PromptOntologySynchronizer(service, repository)

    projection = ProjectionBuilder().build(
        synchronizer=synchronizer,
        entity=prompt,
        primary_entity=("PromptVersion", prompt.prompt_id),
        projection_source="prompt_registry",
    )

    assert projection.primary_entity_id == "prompt-1"
    assert service.get_entity("PromptVersion", "prompt-1") is None


def test_relationship_fingerprint_is_order_independent() -> None:
    repository = InMemoryPromptRepository()
    prompt = _prompt("prompt-1", template="Hello")
    repository.save(prompt)
    service = OntologyService(InMemoryOntologyGraphRepository())
    projection = ProjectionBuilder().build(
        synchronizer=PromptOntologySynchronizer(service, repository),
        entity=prompt,
        primary_entity=("PromptVersion", prompt.prompt_id),
        projection_source="prompt_registry",
    )

    assert fingerprint_relationships(projection.relationships) == (
        fingerprint_relationships(tuple(reversed(projection.relationships)))
    )


def test_diff_reconciler_repairs_missing_projection_then_skips_unchanged() -> None:
    repository = InMemoryPromptRepository()
    prompt = _prompt("prompt-1", template="Hello")
    repository.save(prompt)
    service = OntologyService(InMemoryOntologyGraphRepository())
    reconciler = _prompt_reconciler(service, repository)

    first = reconciler.reconcile_all()
    second = reconciler.reconcile_all()

    assert first.entries[0].action == "repaired"
    assert first.metrics.entities_scanned == 1
    assert first.metrics.entities_repaired == 1
    assert first.metrics.relationship_repairs == 4
    assert first.metrics.repair_failures == 0
    assert first.metrics.skip_ratio == 0
    assert second.entries[0].action == "skipped"
    assert second.stats.entities_synchronized == 0
    assert second.metrics.entities_scanned == 1
    assert second.metrics.entities_skipped == 1
    assert second.metrics.entities_repaired == 0
    assert second.metrics.relationship_repairs == 0
    assert second.metrics.skip_ratio == 1


def test_diff_reconciler_updates_missing_metadata_without_full_repair() -> None:
    repository = InMemoryPromptRepository()
    prompt = _prompt("prompt-1", template="Hello")
    repository.save(prompt)
    service = OntologyService(InMemoryOntologyGraphRepository())
    PromptOntologySynchronizer(service, repository).synchronize(prompt)
    primary_before = service.get_entity("PromptVersion", "prompt-1")
    assert primary_before is not None
    assert "projection_hash" not in primary_before.metadata

    report = _prompt_reconciler(service, repository).reconcile_all()

    primary_after = service.get_entity("PromptVersion", "prompt-1")
    assert report.entries[0].action == "metadata_updated"
    assert report.metrics.entities_repaired == 0
    assert report.metrics.relationship_repairs == 0
    assert primary_after is not None
    assert "projection_hash" in primary_after.metadata


def test_diff_reconciler_repairs_semantic_entity_drift() -> None:
    repository = InMemoryPromptRepository()
    prompt = _prompt("prompt-1", template="Hello")
    repository.save(prompt)
    service = OntologyService(InMemoryOntologyGraphRepository())
    reconciler = _prompt_reconciler(service, repository)
    reconciler.reconcile_all()

    changed = _prompt("prompt-1", template="Changed")
    repository.save(changed)
    report = reconciler.reconcile_all()

    entity = service.get_entity("PromptVersion", "prompt-1")
    assert report.entries[0].action == "repaired"
    assert report.metrics.entities_repaired == 1
    assert entity is not None
    assert entity.immutable_attributes["template"] == "Changed"


def test_diff_reconciler_supports_entity_type_scope_and_single_entity() -> None:
    repository = InMemoryPromptRepository()
    repository.save(_prompt("prompt-1", template="One"))
    repository.save(_prompt("prompt-2", template="Two"))
    service = OntologyService(InMemoryOntologyGraphRepository())
    reconciler = _prompt_reconciler(service, repository)

    type_report = reconciler.reconcile_entity_type("PromptVersion")
    single_report = reconciler.reconcile_entity("PromptVersion", "prompt-1")
    scope_report = reconciler.reconcile_scope("prompt_registry")

    assert len(type_report.entries) == 2
    assert len(single_report.entries) == 1
    assert single_report.entries[0].entity_id == "prompt-1"
    assert len(scope_report.entries) == 2


def test_diff_reconciler_repairs_relationship_drift() -> None:
    repository = InMemoryPromptRepository()
    prompt = _prompt("prompt-1", template="Hello")
    repository.save(prompt)
    service = OntologyService(InMemoryOntologyGraphRepository())
    reconciler = _prompt_reconciler(service, repository)
    reconciler.reconcile_all()
    service.delete_relationship(
        stable_relationship_id(
            "PromptVersion",
            "prompt-1",
            "VERSION_OF",
            "Prompt",
            "prompt:support",
        )
    )

    report = reconciler.reconcile_all()

    assert report.entries[0].action == "repaired"
    assert report.metrics.relationship_repairs == 4
    assert service.find_relationships(
        "PromptVersion",
        "prompt-1",
        direction="outgoing",
        relationship_type="VERSION_OF",
    )


def test_diff_reconciliation_report_metrics_count_failures() -> None:
    report = DiffReconciliationReport(
        entries=(
            DiffReconciliationEntry(
                entity_type="PromptVersion",
                entity_id="prompt-1",
                projection_source="prompt_registry",
                action="failed",
                diff=None,
                result=SynchronizationResult(
                    errors=("repair failed",),
                    stats=SynchronizationStats(failures=1),
                ),
            ),
        ),
        stats=SynchronizationStats(duration_ms=12.5, failures=1),
    )

    assert report.failed_count == 1
    assert report.metrics.repair_failures == 1
    assert report.metrics.execution_duration_ms == 12.5
    assert report.metrics.to_dict() == {
        "entities_scanned": 1,
        "entities_skipped": 0,
        "entities_repaired": 0,
        "relationship_repairs": 0,
        "repair_failures": 1,
        "execution_duration_ms": 12.5,
        "skip_ratio": 0.0,
    }


def _prompt(prompt_id: str, *, template: str) -> Prompt:
    return Prompt(
        prompt_id=prompt_id,
        name="support",
        version=prompt_id,
        template=template,
        variables=(),
        created_at=datetime(2026, 6, 30, tzinfo=UTC),
        created_by="owner",
        status=PromptStatus.ACTIVE,
    )


def _prompt_reconciler(
    service: OntologyService,
    repository: InMemoryPromptRepository,
) -> DiffBasedOntologyReconciler:
    synchronizer = PromptOntologySynchronizer(service, repository)
    return DiffBasedOntologyReconciler(
        service,
        synchronizers=(
            DiffRepositorySynchronizer(
                synchronizer=synchronizer,
                list_entities=repository.find_all,
                primary_entity_resolver=lambda item: (
                    "PromptVersion",
                    item.prompt_id,
                ),
                projection_source="prompt_registry",
                scope_identifier="prompt_registry",
                entity_type="PromptVersion",
                entity_id_resolver=lambda item: item.prompt_id,
            ),
        ),
    )
