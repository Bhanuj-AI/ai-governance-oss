from kavach.repositories.in_memory_prompt_repository import (
    InMemoryPromptRepository,
)
from kavach.repositories.prompt_repository import PromptRepository
from tests.repositories.contract.test_prompt_repository_contract import (
    PromptRepositoryContract,
)


class TestInMemoryPromptRepository(PromptRepositoryContract):
    def repository(self) -> PromptRepository:
        return InMemoryPromptRepository()
