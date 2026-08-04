from abc import ABC, abstractmethod
from datetime import UTC, datetime

from kavach.domain.prompts import (
    Prompt,
    PromptStatus,
)
from kavach.repositories.prompt_repository import PromptRepository


class PromptRepositoryContract(ABC):
    """
    Behavioral contract every PromptRepository implementation must satisfy.
    """

    @abstractmethod
    def repository(self) -> PromptRepository:
        """
        Return a fresh prompt repository instance.
        """

    def create_prompt(self) -> Prompt:
        return Prompt(
            prompt_id="prompt-1",
            name="claim-decision",
            version="1.0.0",
            template="Classify claim: {{claim_text}}",
            variables=("claim_text",),
            created_at=datetime(2026, 6, 25, tzinfo=UTC),
            created_by="governance-admin",
            status=PromptStatus.DRAFT,
        )

    def test_should_save_and_load_prompt(self) -> None:
        repository = self.repository()
        expected = self.create_prompt()

        repository.save(expected)

        assert repository.find_by_id(expected.prompt_id) == expected

    def test_should_find_prompts_by_name(self) -> None:
        repository = self.repository()
        expected = self.create_prompt()

        repository.save(expected)

        assert repository.find_by_name(expected.name) == [expected]
        assert repository.find_by_name("missing") == []

    def test_should_find_prompt_by_name_and_version(self) -> None:
        repository = self.repository()
        expected = self.create_prompt()

        repository.save(expected)

        assert (
            repository.find_by_name_and_version(
                expected.name,
                expected.version,
            )
            == expected
        )
        assert (
            repository.find_by_name_and_version(
                expected.name,
                "missing",
            )
            is None
        )

    def test_should_replace_prompt_with_same_id(self) -> None:
        repository = self.repository()
        expected = self.create_prompt()
        replacement = Prompt(
            prompt_id=expected.prompt_id,
            name=expected.name,
            version=expected.version,
            template=expected.template,
            variables=expected.variables,
            created_at=expected.created_at,
            created_by=expected.created_by,
            status=PromptStatus.ACTIVE,
        )

        repository.save(expected)
        repository.save(replacement)

        assert repository.find_by_id(expected.prompt_id) == replacement

    def test_should_find_all_prompts(self) -> None:
        repository = self.repository()
        expected = self.create_prompt()

        repository.save(expected)

        assert repository.find_all() == [expected]
