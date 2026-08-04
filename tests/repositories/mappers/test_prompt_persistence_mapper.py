from datetime import UTC, datetime

from kavach.domain.prompts import (
    Prompt,
    PromptStatus,
)
from kavach.repositories.mappers.prompt_persistence_mapper import (
    PromptPersistenceMapper,
)


def test_prompt_persistence_mapper_round_trips_prompt() -> None:
    original = Prompt(
        prompt_id="prompt-1",
        name="claim-decision",
        version="1.0.0",
        template="Classify claim: {{claim_text}}",
        variables=("claim_text",),
        created_at=datetime(2026, 6, 25, tzinfo=UTC),
        created_by="governance-admin",
        status=PromptStatus.DRAFT,
    )

    record = PromptPersistenceMapper.to_persistence_record(original)
    reconstructed = PromptPersistenceMapper.from_persistence_record(record)

    assert record["variables_json"] == '["claim_text"]'
    assert record["status"] == "DRAFT"
    assert record["content_available"] is True
    assert reconstructed == original
