from datetime import UTC, datetime

from ai_governance.domain.prompts import Prompt, PromptStatus
from ai_governance.ontology import InMemoryOntologyGraphRepository, OntologyService
from ai_governance.ontology.synchronization import (
    OntologyReconciler,
    PromptOntologySynchronizer,
    RepositorySynchronizer,
)
from ai_governance.repositories.in_memory_prompt_repository import (
    InMemoryPromptRepository,
)


def test_reconciler_repairs_missing_projection() -> None:
    repository = InMemoryPromptRepository()
    prompt = Prompt(
        prompt_id="prompt-1",
        name="support",
        version="v1",
        template="Hello",
        variables=(),
        created_at=datetime(2026, 6, 30, tzinfo=UTC),
        created_by="owner",
        status=PromptStatus.ACTIVE,
    )
    repository.save(prompt)
    service = OntologyService(InMemoryOntologyGraphRepository())
    reconciler = OntologyReconciler(
        service,
        synchronizers=(
            RepositorySynchronizer(
                synchronizer=PromptOntologySynchronizer(service, repository),
                list_entities=repository.find_all,
                primary_entity_resolver=lambda item: (
                    "PromptVersion",
                    item.prompt_id,
                ),
            ),
        ),
    )

    result = reconciler.reconcile()

    assert len(result.issues) == 1
    assert result.issues[0].repaired is True
    assert service.get_entity("PromptVersion", "prompt-1") is not None
