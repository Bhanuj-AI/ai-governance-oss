from datetime import UTC, datetime

import pytest

from kavach.decisions import (
    DecisionEvidenceGraph,
    DecisionTargetType,
    DecisionType,
    EvidenceNode,
    GovernancePolicy,
    GovernancePolicyEvaluator,
    GovernanceReasoningEngine,
    GovernanceReasoningRequest,
    InMemoryGovernancePolicyProvider,
    MissingEvidence,
    PolicyCondition,
    PolicyConditionOperator,
    PolicyEffect,
    PolicyEvaluationContext,
    PolicyRule,
    PolicyStatus,
    ReasoningEvidenceSummarizer,
)
from kavach.decisions.enums import DecisionConfidenceLevel, DecisionStatus
from kavach.decisions.exceptions import DecisionValidationError
from kavach.ontology import EntityType


def test_reasoning_request_validation() -> None:
    with pytest.raises(DecisionValidationError):
        GovernanceReasoningRequest(
            target_type=DecisionTargetType.CANDIDATE,
            target_id=" ",
            decision_type=DecisionType.APPROVE,
        )

    with pytest.raises(DecisionValidationError):
        GovernanceReasoningRequest(
            target_type=DecisionTargetType.CANDIDATE,
            target_id="candidate-1",
            decision_type=DecisionType.APPROVE,
            producer_id=" ",
        )


def test_evidence_summarizer_extracts_metric_scores() -> None:
    summary = ReasoningEvidenceSummarizer().summarize(_evidence_graph())

    assert summary.metric_scores == {
        "answer_relevance": 0.87,
        "groundedness": 0.91,
    }


def test_evidence_summarizer_extracts_drift_and_statuses() -> None:
    summary = ReasoningEvidenceSummarizer().summarize(
        _evidence_graph(
            extra_nodes=(
                EvidenceNode(
                    entity_type=EntityType.DRIFT_ANALYSIS.value,
                    entity_id="drift-1",
                    attributes={"severity": "HIGH"},
                ),
                EvidenceNode(
                    entity_type=EntityType.JOB.value,
                    entity_id="job-1",
                    attributes={"status": "SUCCEEDED"},
                ),
                EvidenceNode(
                    entity_type=EntityType.MCP_AUDIT_RECORD.value,
                    entity_id="audit-1",
                    attributes={"status": "SUCCEEDED"},
                ),
            )
        )
    )

    assert summary.drift_severity == "HIGH"
    assert summary.latest_job_status == "SUCCEEDED"
    assert summary.latest_audit_status == "SUCCEEDED"


def test_evidence_summarizer_preserves_missing_evidence() -> None:
    missing = MissingEvidence(
        evidence_type="Metric",
        reason="No metric evidence is connected.",
        severity="WARNING",
    )

    summary = ReasoningEvidenceSummarizer().summarize(
        _evidence_graph(missing=(missing,))
    )

    assert summary.missing_evidence == (missing,)


def test_policy_provider_returns_policies_for_target() -> None:
    candidate_policy = _policy("policy-candidate", PolicyEffect.APPROVE)
    experiment_policy = GovernancePolicy(
        policy_id="policy-experiment",
        version="1",
        name="experiment gate",
        description=None,
        status=PolicyStatus.ACTIVE,
        target_types=(DecisionTargetType.EXPERIMENT,),
        rules=(_rule(PolicyEffect.APPROVE),),
        created_by="tester",
        created_at=datetime(2026, 7, 2, tzinfo=UTC),
    )
    provider = InMemoryGovernancePolicyProvider(
        (experiment_policy, candidate_policy)
    )

    assert provider.get_policies_for_target(
        DecisionTargetType.CANDIDATE
    ) == (candidate_policy,)
    assert provider.get_policies_for_target(
        DecisionTargetType.CANDIDATE,
        ("policy-candidate",),
    ) == (candidate_policy,)


def test_block_policy_maps_to_blocked_decision() -> None:
    outcome = _reason_with_policy(_policy("policy-block", PolicyEffect.BLOCK))

    assert outcome.decision.status == DecisionStatus.BLOCKED


def test_reject_policy_maps_to_rejected_decision() -> None:
    outcome = _reason_with_policy(_policy("policy-reject", PolicyEffect.REJECT))

    assert outcome.decision.status == DecisionStatus.REJECTED


def test_approve_policy_maps_to_approved_decision() -> None:
    outcome = _reason_with_policy(_policy("policy-approve", PolicyEffect.APPROVE))

    assert outcome.decision.status == DecisionStatus.APPROVED


def test_recommend_policy_maps_to_proposed_decision() -> None:
    outcome = _reason_with_policy(
        _policy("policy-recommend", PolicyEffect.RECOMMEND)
    )

    assert outcome.decision.status == DecisionStatus.PROPOSED


def test_block_takes_precedence_over_approve() -> None:
    outcome = _reason_with_policy(
        _policy("policy-approve", PolicyEffect.APPROVE),
        _policy("policy-block", PolicyEffect.BLOCK),
    )

    assert outcome.decision.status == DecisionStatus.BLOCKED


def test_no_policy_match_produces_proposed_decision() -> None:
    outcome = _reason_with_policy(
        _policy(
            "policy-no-match",
            PolicyEffect.APPROVE,
            expected_value=0.99,
            operator=PolicyConditionOperator.GREATER_THAN,
        )
    )

    assert outcome.decision.status == DecisionStatus.PROPOSED
    assert outcome.decision.reason == "No policy produced a final decision."
    assert outcome.decision.confidence == DecisionConfidenceLevel.LOW


def test_critical_missing_evidence_produces_low_confidence() -> None:
    outcome = _reason_with_policy(
        _policy("policy-approve", PolicyEffect.APPROVE),
        missing=(
            MissingEvidence(
                evidence_type="Target",
                reason="Target entity was not found.",
                severity="CRITICAL",
            ),
        ),
    )

    assert outcome.decision.confidence == DecisionConfidenceLevel.LOW


def test_warning_missing_evidence_produces_medium_confidence() -> None:
    outcome = _reason_with_policy(
        _policy("policy-approve", PolicyEffect.APPROVE),
        missing=(
            MissingEvidence(
                evidence_type="Metric",
                reason="No metric evidence is connected.",
                severity="WARNING",
            ),
        ),
    )

    assert outcome.decision.confidence == DecisionConfidenceLevel.MEDIUM


def test_deterministic_decision_id_remains_stable_for_same_inputs() -> None:
    engine = _engine((_policy("policy-approve", PolicyEffect.APPROVE),))
    request = _request()

    first = engine.reason(request)
    second = engine.reason(request)

    assert first.decision.decision_id == second.decision.decision_id


def test_explanation_includes_policy_reason() -> None:
    outcome = _reason_with_policy(_policy("policy-block", PolicyEffect.BLOCK))

    assert "BLOCK reason" in outcome.explanation.reasons
    assert outcome.explanation.summary.startswith("Candidate candidate-1 was")


def test_explanation_includes_critical_missing_evidence() -> None:
    outcome = _reason_with_policy(
        _policy("policy-approve", PolicyEffect.APPROVE),
        missing=(
            MissingEvidence(
                evidence_type="Target",
                reason="Target entity was not found.",
                severity="CRITICAL",
            ),
        ),
    )

    assert any(
        reason.startswith("Critical missing evidence: Target")
        for reason in outcome.explanation.reasons
    )


def test_engine_does_not_mutate_evidence_graph_or_policies() -> None:
    policy = _policy("policy-approve", PolicyEffect.APPROVE)
    graph = _evidence_graph()
    engine = _engine((policy,), evidence_graph=graph)

    before_policy = policy
    before_graph = graph
    engine.reason(_request())

    assert policy == before_policy
    assert graph == before_graph


def _request() -> GovernanceReasoningRequest:
    return GovernanceReasoningRequest(
        target_type=DecisionTargetType.CANDIDATE,
        target_id="candidate-1",
        decision_type=DecisionType.APPROVE,
        correlation_id="correlation-1",
        request_id="request-1",
    )


def _reason_with_policy(
    *policies: GovernancePolicy,
    missing: tuple[MissingEvidence, ...] = (),
):
    return _engine(policies, missing=missing).reason(_request())


def _engine(
    policies: tuple[GovernancePolicy, ...],
    *,
    missing: tuple[MissingEvidence, ...] = (),
    evidence_graph: DecisionEvidenceGraph | None = None,
) -> GovernanceReasoningEngine:
    graph = evidence_graph or _evidence_graph(missing=missing)
    return GovernanceReasoningEngine(
        evidence_builder=FakeEvidenceBuilder(graph),
        evidence_summarizer=ReasoningEvidenceSummarizer(),
        policy_evaluator=GovernancePolicyEvaluator(),
        policy_provider=InMemoryGovernancePolicyProvider(policies),
    )


def _policy(
    policy_id: str,
    effect: PolicyEffect,
    *,
    expected_value: float = 0.8,
    operator: PolicyConditionOperator = (
        PolicyConditionOperator.GREATER_THAN_OR_EQUAL
    ),
) -> GovernancePolicy:
    return GovernancePolicy(
        policy_id=policy_id,
        version="1",
        name=f"{effect.value.lower()} gate",
        description=None,
        status=PolicyStatus.ACTIVE,
        target_types=(DecisionTargetType.CANDIDATE,),
        rules=(
            _rule(
                effect,
                expected_value=expected_value,
                operator=operator,
            ),
        ),
        created_by="tester",
        created_at=datetime(2026, 7, 2, tzinfo=UTC),
    )


def _rule(
    effect: PolicyEffect,
    *,
    expected_value: float = 0.8,
    operator: PolicyConditionOperator = (
        PolicyConditionOperator.GREATER_THAN_OR_EQUAL
    ),
) -> PolicyRule:
    return PolicyRule(
        rule_id=f"rule-{effect.value.lower()}",
        name=f"{effect.value.lower()} rule",
        conditions=(
            PolicyCondition(
                field_path="metrics.groundedness.score",
                operator=operator,
                expected_value=expected_value,
            ),
        ),
        effect=effect,
        reason_template=f"{effect.value} reason",
        priority=1,
    )


def _evidence_graph(
    *,
    extra_nodes: tuple[EvidenceNode, ...] = (),
    missing: tuple[MissingEvidence, ...] = (),
) -> DecisionEvidenceGraph:
    return DecisionEvidenceGraph(
        target_type=DecisionTargetType.CANDIDATE,
        target_id="candidate-1",
        nodes=(
            EvidenceNode(
                entity_type=EntityType.CANDIDATE.value,
                entity_id="candidate-1",
            ),
            EvidenceNode(
                entity_type=EntityType.EVALUATION_RESULT.value,
                entity_id="eval-result-1",
            ),
            EvidenceNode(
                entity_type=EntityType.METRIC.value,
                entity_id="metric-groundedness",
                attributes={"metric_name": "groundedness", "score": 0.91},
            ),
            EvidenceNode(
                entity_type=EntityType.METRIC.value,
                entity_id="metric-answer-relevance",
                attributes={"metric_name": "answer relevance", "score": 0.87},
            ),
            EvidenceNode(
                entity_type=EntityType.POLICY.value,
                entity_id="policy-approve",
            ),
            *extra_nodes,
        ),
        missing=missing,
    )


class FakeEvidenceBuilder:
    def __init__(self, evidence_graph: DecisionEvidenceGraph) -> None:
        self._evidence_graph = evidence_graph

    def build_for_target(
        self,
        target_type: DecisionTargetType,
        target_id: str,
        *,
        depth: int = 3,
    ) -> DecisionEvidenceGraph:
        return self._evidence_graph

    def build_policy_context(
        self,
        evidence_graph: DecisionEvidenceGraph,
    ) -> PolicyEvaluationContext:
        return PolicyEvaluationContext(
            target_type=evidence_graph.target_type,
            target_id=evidence_graph.target_id,
            evidence={
                "metrics": {
                    "groundedness": {"score": 0.91},
                    "answer_relevance": {"score": 0.87},
                }
            },
        )
