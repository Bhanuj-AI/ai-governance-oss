from __future__ import annotations

from abc import ABC, abstractmethod

from kavach.domain.datasets import Dataset


class DatasetRepository(ABC):
    """
    Persistence contract for governed dataset versions.

    Repositories store immutable dataset records. Lifecycle and governance
    rules are owned by DatasetRegistryService.
    """

    @abstractmethod
    def save(
        self,
        dataset: Dataset,
    ) -> None:
        pass

    @abstractmethod
    def find_by_id(
        self,
        dataset_id: str,
    ) -> Dataset | None:
        pass

    @abstractmethod
    def find_by_name(
        self,
        name: str,
    ) -> list[Dataset]:
        pass

    @abstractmethod
    def find_by_name_and_version(
        self,
        name: str,
        version: str,
    ) -> Dataset | None:
        pass

    @abstractmethod
    def find_all(self) -> list[Dataset]:
        pass
