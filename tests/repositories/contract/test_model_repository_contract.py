from abc import ABC, abstractmethod
from datetime import UTC, datetime

from kavach.domain.models import (
    Model,
    ModelStatus,
)
from kavach.repositories.model_repository import ModelRepository


class ModelRepositoryContract(ABC):
    """
    Behavioral contract every ModelRepository implementation must satisfy.
    """

    @abstractmethod
    def repository(self) -> ModelRepository:
        """
        Return a fresh model repository instance.
        """

    def create_model(self) -> Model:
        return Model(
            model_id="model-1",
            provider="OpenAI",
            model_name="GPT-4.1",
            version="2026-06-25",
            parameters={
                "temperature": 0.0,
            },
            cost={
                "input_per_1k": 0.01,
                "output_per_1k": 0.03,
            },
            latency=0.42,
            context_window=128000,
            creator="governance-admin",
            created_at=datetime(2026, 6, 25, tzinfo=UTC),
            status=ModelStatus.DRAFT,
        )

    def test_should_save_and_load_model(self) -> None:
        repository = self.repository()
        expected = self.create_model()

        repository.save(expected)

        assert repository.find_by_id(expected.model_id) == expected

    def test_should_find_versions_for_logical_model(self) -> None:
        repository = self.repository()
        expected = self.create_model()

        repository.save(expected)

        assert repository.find_by_logical_model(
            expected.provider,
            expected.model_name,
        ) == [expected]
        assert repository.find_by_logical_model("missing", "missing") == []

    def test_should_find_model_by_provider_name_and_version(self) -> None:
        repository = self.repository()
        expected = self.create_model()

        repository.save(expected)

        assert (
            repository.find_by_provider_name_and_version(
                expected.provider,
                expected.model_name,
                expected.version,
            )
            == expected
        )
        assert (
            repository.find_by_provider_name_and_version(
                expected.provider,
                expected.model_name,
                "missing",
            )
            is None
        )

    def test_should_replace_model_with_same_id(self) -> None:
        repository = self.repository()
        expected = self.create_model()
        replacement = Model(
            model_id=expected.model_id,
            provider=expected.provider,
            model_name=expected.model_name,
            version=expected.version,
            parameters=expected.parameters,
            cost=expected.cost,
            latency=expected.latency,
            context_window=expected.context_window,
            creator=expected.creator,
            created_at=expected.created_at,
            status=ModelStatus.ACTIVE,
        )

        repository.save(expected)
        repository.save(replacement)

        assert repository.find_by_id(expected.model_id) == replacement

    def test_should_find_all_models(self) -> None:
        repository = self.repository()
        expected = self.create_model()

        repository.save(expected)

        assert repository.find_all() == [expected]
