from datetime import UTC, datetime

import pytest

from kavach.domain.experiments import (
    Experiment,
    ExperimentStatus,
)


def test_experiment_requires_non_empty_name() -> None:
    with pytest.raises(ValueError):
        Experiment(
            experiment_id="experiment-1",
            name="",
            description="Compare support prompts",
            owner="governance-team",
            created_at=datetime(2026, 6, 26, tzinfo=UTC),
            status=ExperimentStatus.DRAFT,
        )
