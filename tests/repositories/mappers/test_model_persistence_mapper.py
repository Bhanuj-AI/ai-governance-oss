from datetime import UTC, datetime

from ai_governance.domain.models import (
    Model,
    ModelStatus,
)
from ai_governance.repositories.mappers.model_persistence_mapper import (
    ModelPersistenceMapper,
)


def test_model_persistence_mapper_round_trips_model() -> None:
    original = Model(
        model_id="model-1",
        provider="OpenAI",
        model_name="GPT-4.1",
        version="2026-06-25",
        parameters={
            "temperature": 0.0,
            "reasoning": "medium",
        },
        cost={
            "input_per_1k": 0.01,
        },
        latency=0.42,
        context_window=128000,
        creator="governance-admin",
        created_at=datetime(2026, 6, 25, tzinfo=UTC),
        status=ModelStatus.DRAFT,
    )

    record = ModelPersistenceMapper.to_persistence_record(original)
    reconstructed = ModelPersistenceMapper.from_persistence_record(record)

    assert record["status"] == "DRAFT"
    assert record["context_window"] == 128000
    assert reconstructed == original
