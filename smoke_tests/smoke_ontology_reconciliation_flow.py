from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from ai_governance.domain.prompts import Prompt, PromptStatus
from ai_governance.ontology import InMemoryOntologyGraphRepository, OntologyService
from ai_governance.ontology.synchronization import (
    DiffBasedOntologyReconciler,
    DiffRepositorySynchronizer,
    PromptOntologySynchronizer,
    ProjectionBuilder,
)
from ai_governance.ontology.synchronization.synchronizer import stable_relationship_id
from ai_governance.repositories.in_memory_prompt_repository import (
    InMemoryPromptRepository,
)


def main() -> None:
    repository = InMemoryPromptRepository()
    ontology_service = OntologyService(InMemoryOntologyGraphRepository())
    prompt = Prompt(
        prompt_id="prompt-smoke-1",
        name="support-response",
        version="v1",
        template="Answer the support question: {question}",
        variables=("question",),
        created_at=datetime(2026, 6, 30, tzinfo=UTC),
        created_by="governance-admin",
        status=PromptStatus.ACTIVE,
    )
    repository.save(prompt)

    prompt_synchronizer = PromptOntologySynchronizer(
        ontology_service,
        repository,
    )
    projection = ProjectionBuilder().build(
        synchronizer=prompt_synchronizer,
        entity=prompt,
        primary_entity=("PromptVersion", prompt.prompt_id),
        projection_source="prompt_registry",
    )
    print("Projection fingerprint:")
    print(f"  projection_hash={projection.fingerprint.projection_hash[:12]}")
    print(
        "  relationship_set_hash="
        f"{projection.fingerprint.relationship_set_hash[:12]}"
    )

    reconciler = DiffBasedOntologyReconciler(
        ontology_service,
        synchronizers=(
            DiffRepositorySynchronizer(
                synchronizer=prompt_synchronizer,
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

    first = reconciler.reconcile_all()
    print("First reconciliation:")
    print(f"  action={first.entries[0].action}")
    print(f"  metrics={first.metrics.to_dict()}")

    second = reconciler.reconcile_all()
    print("Second reconciliation:")
    print(f"  action={second.entries[0].action}")
    print(f"  metrics={second.metrics.to_dict()}")

    ontology_service.delete_relationship(
        stable_relationship_id(
            "PromptVersion",
            prompt.prompt_id,
            "VERSION_OF",
            "Prompt",
            "prompt:support-response",
        )
    )
    relationship_repair = reconciler.reconcile_entity(
        "PromptVersion",
        prompt.prompt_id,
    )
    print("Relationship drift reconciliation:")
    print(f"  action={relationship_repair.entries[0].action}")
    print(f"  metrics={relationship_repair.metrics.to_dict()}")

    updated_prompt = replace(
        prompt,
        template="Answer clearly and cite policy: {question}",
    )
    repository.save(updated_prompt)
    semantic_repair = reconciler.reconcile_scope("prompt_registry")
    repaired_entity = ontology_service.get_entity(
        "PromptVersion",
        prompt.prompt_id,
    )
    print("Semantic drift reconciliation:")
    print(f"  action={semantic_repair.entries[0].action}")
    print(f"  metrics={semantic_repair.metrics.to_dict()}")
    print(
        "  template="
        f"{repaired_entity.immutable_attributes['template'] if repaired_entity else 'missing'}"
    )

    metadata = repaired_entity.metadata if repaired_entity else {}
    print("Stored reconciliation metadata:")
    print(f"  projection_source={metadata.get('projection_source')}")
    print(f"  projection_version={metadata.get('projection_version')}")


if __name__ == "__main__":
    main()
