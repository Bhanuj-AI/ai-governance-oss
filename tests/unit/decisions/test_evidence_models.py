import pytest

from kavach.decisions import (
    DecisionEvidenceGraph,
    DecisionEvidenceSummary,
    DecisionTargetType,
    EvidenceEdge,
    EvidenceNode,
    MissingEvidence,
)
from kavach.decisions.exceptions import DecisionValidationError


def test_evidence_graph_sorts_nodes_edges_and_missing_entries() -> None:
    graph = DecisionEvidenceGraph(
        target_type=DecisionTargetType.CANDIDATE,
        target_id="candidate-1",
        nodes=(
            EvidenceNode(entity_type="Metric", entity_id="metric-2"),
            EvidenceNode(entity_type="Metric", entity_id="metric-1"),
        ),
        edges=(
            EvidenceEdge(
                relationship_type="HAS_METRIC",
                source_type="EvaluationResult",
                source_id="eval-result-1",
                target_type="Metric",
                target_id="metric-2",
            ),
            EvidenceEdge(
                relationship_type="HAS_METRIC",
                source_type="EvaluationResult",
                source_id="eval-result-1",
                target_type="Metric",
                target_id="metric-1",
            ),
        ),
        missing=(
            MissingEvidence(
                evidence_type="Policy",
                reason="No policy reference is connected.",
                severity="INFO",
            ),
        ),
    )

    assert [node.entity_id for node in graph.nodes] == ["metric-1", "metric-2"]
    assert [edge.target_id for edge in graph.edges] == ["metric-1", "metric-2"]
    assert graph.target_type == DecisionTargetType.CANDIDATE


def test_evidence_summary_sorts_ids() -> None:
    summary = DecisionEvidenceSummary(
        target_type=DecisionTargetType.CANDIDATE,
        target_id="candidate-1",
        evaluation_result_ids=("eval-result-2", "eval-result-1"),
        metric_ids=("metric-2", "metric-1"),
    )

    assert summary.evaluation_result_ids == ("eval-result-1", "eval-result-2")
    assert summary.metric_ids == ("metric-1", "metric-2")


def test_missing_evidence_rejects_unknown_severity() -> None:
    with pytest.raises(DecisionValidationError):
        MissingEvidence(
            evidence_type="Metric",
            reason="No metric evidence is connected.",
            severity="SEVERE",
        )
