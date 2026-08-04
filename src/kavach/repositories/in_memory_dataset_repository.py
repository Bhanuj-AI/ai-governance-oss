from __future__ import annotations

from kavach.domain.datasets import Dataset
from kavach.repositories.dataset_repository import DatasetRepository


class InMemoryDatasetRepository(DatasetRepository):
    """
    In-memory DatasetRepository used by tests and local workflows.
    """

    def __init__(self) -> None:
        self._datasets_by_id: dict[str, Dataset] = {}

    def save(
        self,
        dataset: Dataset,
    ) -> None:
        self._datasets_by_id[dataset.dataset_id] = dataset

    def find_by_id(
        self,
        dataset_id: str,
    ) -> Dataset | None:
        return self._datasets_by_id.get(dataset_id)

    def find_by_name(
        self,
        name: str,
    ) -> list[Dataset]:
        return [
            dataset
            for dataset in self._datasets_by_id.values()
            if dataset.name == name
        ]

    def find_by_name_and_version(
        self,
        name: str,
        version: str,
    ) -> Dataset | None:
        return next(
            (
                dataset
                for dataset in self._datasets_by_id.values()
                if dataset.name == name and dataset.version == version
            ),
            None,
        )

    def find_all(self) -> list[Dataset]:
        return list(self._datasets_by_id.values())
