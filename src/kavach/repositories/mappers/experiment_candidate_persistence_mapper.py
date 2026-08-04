from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from kavach.domain.experiments import ExperimentCandidate


class ExperimentCandidatePersistenceMapper:
    """
    Maps ExperimentCandidate domain objects to and from persistence records.
    """

    @staticmethod
    def to_persistence_record(
        candidate: ExperimentCandidate,
    ) -> dict[str, Any]:
        return {
            "candidate_id": candidate.candidate_id,
            "experiment_id": candidate.experiment_id,
            "name": candidate.name,
            "prompt_id": candidate.prompt_id,
            "prompt_version": candidate.prompt_version,
            "model_id": candidate.model_id,
            "model_version": candidate.model_version,
            "dataset_id": candidate.dataset_id,
            "dataset_version": candidate.dataset_version,
            "evaluation_provider": candidate.evaluation_provider,
            "temperature": candidate.temperature,
            "top_p": candidate.top_p,
            "max_tokens": candidate.max_tokens,
            "metadata_json": json.dumps(candidate.metadata),
            "created_at": candidate.created_at.isoformat(),
        }

    @staticmethod
    def from_persistence_record(
        record: Mapping[str, Any],
    ) -> ExperimentCandidate:
        return ExperimentCandidate(
            candidate_id=record["candidate_id"],
            experiment_id=record["experiment_id"],
            name=record["name"],
            prompt_id=record["prompt_id"],
            prompt_version=record["prompt_version"],
            model_id=record["model_id"],
            model_version=record["model_version"],
            dataset_id=record["dataset_id"],
            dataset_version=record["dataset_version"],
            evaluation_provider=record["evaluation_provider"],
            temperature=record["temperature"],
            top_p=record["top_p"],
            max_tokens=record["max_tokens"],
            metadata=json.loads(record["metadata_json"] or "{}"),
            created_at=datetime.fromisoformat(record["created_at"]),
        )

    @classmethod
    def from_persistence_records(
        cls,
        records: list[Mapping[str, Any]],
    ) -> list[ExperimentCandidate]:
        return [
            cls.from_persistence_record(record)
            for record in records
        ]
