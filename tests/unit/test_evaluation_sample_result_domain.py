from __future__ import annotations

import pytest

from ai_governance.domain.evaluation_result import (
    EvaluationMetric,
    EvaluationSampleResult,
)


def test_evaluation_sample_result_requires_a_stable_identity_and_metric() -> None:
    with pytest.raises(ValueError, match="sample_id"):
        EvaluationSampleResult(" ", (EvaluationMetric("pass", 1.0),))
    with pytest.raises(ValueError, match="at least one metric"):
        EvaluationSampleResult("sample-1", ())


def test_evaluation_sample_result_defensively_copies_metadata() -> None:
    metadata = {"sample_status": "success"}
    result = EvaluationSampleResult(
        "sample-1", (EvaluationMetric("pass", 1.0),), metadata=metadata
    )
    metadata["sample_status"] = "changed"

    assert result.metadata == {"sample_status": "success"}
