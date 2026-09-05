import pytest

from ai_governance.domain.causal_audit import (
    CounterfactualReplayLineage,
    EvidenceInterventionStrategy,
    InterventionConfiguration,
    OutcomeScore,
    ToolEvidenceInfluence,
)


def _score(value: float = 0.4) -> OutcomeScore:
    return OutcomeScore(value, "outcome", "test-evaluator", "v1")


def _lineage() -> CounterfactualReplayLineage:
    return CounterfactualReplayLineage(
        replay_id="replay-1",
        replay_execution_id="execution-1",
        replay_status="EXECUTION_COMPLETED",
        policy_id="policy-1",
        policy_version=1,
        provider_id="structured-json",
        provider_version="v1",
        original_evidence_digest="sha256:original",
        counterfactual_evidence_reference="counterfactual:sha256:replacement",
        counterfactual_evidence_digest="sha256:replacement",
        intervention_digest="intervention-digest",
        evaluator_score=_score(),
    )


def test_evidence_influence_requires_complete_counterfactual_lineage() -> None:
    with pytest.raises(ValueError, match="complete counterfactual lineage"):
        ToolEvidenceInfluence(
            tool_call_id="call-1",
            tool_name="lookup",
            position=0,
            intervention=InterventionConfiguration(
                EvidenceInterventionStrategy.REPLACE,
                1,
                intervention_policy_id="policy-1",
                intervention_policy_version=1,
            ),
            counterfactual_count=1,
            baseline_score=_score(0.9),
            counterfactual_score=_score(),
            influence_score=0.5,
            useful=True,
            harmful=False,
            post_saturation=False,
            counterfactual_replay_ids=("replay-1",),
            counterfactual_execution_ids=("execution-1",),
        )


def test_evidence_influence_rejects_mismatched_policy_lineage() -> None:
    with pytest.raises(ValueError, match="match the governed policy version"):
        ToolEvidenceInfluence(
            tool_call_id="call-1",
            tool_name="lookup",
            position=0,
            intervention=InterventionConfiguration(
                EvidenceInterventionStrategy.REPLACE,
                1,
                intervention_policy_id="other-policy",
                intervention_policy_version=1,
            ),
            counterfactual_count=1,
            baseline_score=_score(0.9),
            counterfactual_score=_score(),
            influence_score=0.5,
            useful=True,
            harmful=False,
            post_saturation=False,
            counterfactual_replay_ids=("replay-1",),
            counterfactual_execution_ids=("execution-1",),
            counterfactual_lineage=(_lineage(),),
        )


def test_counterfactual_lineage_rejects_unsuccessful_replay() -> None:
    with pytest.raises(ValueError, match="successful replay status"):
        CounterfactualReplayLineage(
            replay_id="replay-1",
            replay_execution_id="execution-1",
            replay_status="FAILED",
            policy_id="policy-1",
            policy_version=1,
            provider_id="structured-json",
            provider_version="v1",
            original_evidence_digest="sha256:original",
            counterfactual_evidence_reference="counterfactual:sha256:replacement",
            counterfactual_evidence_digest="sha256:replacement",
            intervention_digest="intervention-digest",
            evaluator_score=_score(),
        )
