from datetime import UTC, datetime

import pytest

from ai_governance.domain.experiments import (
    CandidateComparison,
    ExperimentCandidate,
)


def test_experiment_candidate_requires_positive_max_tokens() -> None:
    with pytest.raises(ValueError):
        ExperimentCandidate(
            candidate_id="candidate-1",
            experiment_id="experiment-1",
            name="Baseline",
            prompt_id="prompt-1",
            prompt_version="v1",
            model_id="model-1",
            model_version="2026-06-25",
            dataset_id="dataset-1",
            dataset_version="2026-06-26",
            evaluation_provider="TruLens",
            temperature=0.0,
            top_p=1.0,
            max_tokens=0,
            metadata={},
            created_at=datetime(2026, 6, 26, tzinfo=UTC),
        )


def test_candidate_comparison_reports_change_presence() -> None:
    comparison = CandidateComparison(
        baseline_candidate_id="candidate-1",
        candidate_candidate_id="candidate-2",
        prompt_id_changed=False,
        prompt_version_changed=True,
        model_id_changed=False,
        model_version_changed=False,
        dataset_id_changed=False,
        dataset_version_changed=False,
        evaluation_provider_changed=False,
        temperature_changed=True,
        top_p_changed=False,
        max_tokens_changed=False,
        metadata_changed=False,
    )

    assert comparison.has_changes is True
